"""
官方 DSCALE 算法适配层。

直接使用官方 DSCALE 仓库中的 fit_funcs.py（LogLogFunc），
以及 fun_max_tc_convergence 的完整实现（含 β 指数）。

本模块仅负责:
  1. 输入适配: 将我们的 DataFrame 格式转换为官方算法所需格式
  2. 调用官方计算: ENLONG (LogLogFunc), 收敛 (fun_max_tc_convergence)
  3. 输出适配: 转换回我们的统一输出格式

不修改官方计算层的任何代码。
"""

import sys
import contextlib
from pathlib import Path

import numpy as np
import pandas as pd


@contextlib.contextmanager
def _suppress_np_warnings():
    """上下文管理器：仅在使用官方 LogLogFunc 回归时抑制除零/无效值警告。"""
    old = np.seterr(divide="ignore", invalid="ignore")
    try:
        yield
    finally:
        np.seterr(**old)

# 将官方 DSCALE 仓库加入 path，以便直接 import fit_funcs
_DSCALE_REPO = Path(__file__).resolve().parents[2] / "DSCALE"
if str(_DSCALE_REPO) not in sys.path:
    sys.path.insert(0, str(_DSCALE_REPO))

from downscaler.fit_funcs import LogLogFunc  # noqa: E402

from ..common.config import YEARS
from ..common.io import (
    read_gdp_country, read_pop_country, read_gdp_region, read_pop_region,
)
from ..common.config import gdp_country_path, pop_country_path, gdp_region_path, pop_region_path
from ..common.mapping import load_mapping, build_region_members
from ..common.downscale import (
    _build_iso_info, _region_isos, _regional_conserve, _make_row, _finalize_df,
)

# ── 官方常量 ─────────────────────────────────────────────
MAX_TC_DEFAULT = 2200   # fun_max_tc_convergence 默认值
TC_BASE_YEAR = 2010     # 官方收敛公式中的基年
# ENLONG 回归使用全部可用 GCAM 年份（与官方 DSCALE 对齐）
ENLONG_YEARS = [1990, 2005, 2010] + list(range(2015, 2101, 5))
MAX_TC_Y_MIN = 2040     # 官方最小 MAX_TC


def fun_max_tc(
    beta_short: float,
    r_squared_short: float,
    hist_start: int,
    hist_end: int,
    beta_long: float,
    y_min: int = MAX_TC_Y_MIN,
    y_max: int = MAX_TC_DEFAULT,
) -> float:
    """官方 MAX_TC 动态计算（utils.py:1493-1508, 24290-24321）。

    基于 ENSHORT 回归质量和 beta 符号确定收敛完成年份。

    Parameters
    ----------
    beta_short: ENSHORT 回归 beta（逐国历史回归斜率）
    r_squared_short: ENSHORT 回归 R²
    hist_start: 历史数据起始年份
    hist_end: 历史数据结束年份
    beta_long: ENLONG 回归 beta（区域 IAM 回归斜率）
    y_min, y_max: MAX_TC 范围 [2040, 2200]

    Returns
    -------
    max_tc: 收敛完成年份
    """
    # Beta 符号冲突检查（官方: BETA * BETA_ENLONG <= 0 → y_min）
    if beta_short * beta_long < 0:
        return float(y_min)

    data_duration = hist_end - hist_start
    quality = r_squared_short * data_duration  # 官方质量指标

    # 官方阈值: x_min = 0.3*(end_hist-1990), x_max = 1.0*(end_hist-1979)
    x_min = 0.3 * (hist_end - 1990)
    x_max = 1.0 * (hist_end - 1979)

    if x_max <= x_min:
        return float(y_min)

    slope_tc = (y_max - y_min) / (x_max - x_min)
    intercept_tc = y_min - slope_tc * x_min

    return max(float(y_min), min(float(y_max),
               round(intercept_tc + slope_tc * quality)))


# ═══════════════════════════════════════════════════════════
# 官方收敛函数（直接复制自 Energy_demand_downs_1.py:650-675）
# ═══════════════════════════════════════════════════════════

def fun_max_tc_convergence(
    enshort: np.ndarray,
    enlong: np.ndarray,
    time_points: np.ndarray,
    max_tc: np.ndarray,
    beta: np.ndarray,
) -> np.ndarray:
    """
    官方 MAX_TC 收敛公式（逐元素向量化版本）。

    等效于 Energy_demand_downs_1.py:650-675:
        CONV_WEIGHT = ((TIME - MAX_TC) / (2010 - MAX_TC)) ** β.clip(1, ∞)
        CONV_WEIGHT = CONV_WEIGHT.clip(0, 1)
        ENSHORT = ENSHORT × CONV_WEIGHT + ENLONG × (1 - CONV_WEIGHT)

    Parameters
    ----------
    enshort, enlong: 等长数组
    time_points: 年份数组
    max_tc: 每个数据点的 MAX_TC 值（可标量或等长数组）
    beta: 每个数据点的 β 值（可标量或等长数组）

    Returns
    -------
    converged: 收敛后的 ENSHORT 值
    """
    beta_clipped = np.clip(beta, 1.0, np.inf)
    conv_weight = (time_points - max_tc) / (TC_BASE_YEAR - max_tc)
    conv_weight = np.clip(conv_weight, 0.0, 1.0)
    conv_weight = conv_weight ** beta_clipped
    return enshort * conv_weight + enlong * (1.0 - conv_weight)


# ═══════════════════════════════════════════════════════════
# ENLONG: 使用官方 LogLogFunc 的 log-log 回归
# ═══════════════════════════════════════════════════════════

def fit_enlong_official(
    gcam_tfc: pd.Series,   # 区域 TFC (index=年份)
    gcam_gdp: pd.Series,   # 区域 GDP
    gcam_pop: pd.Series,   # 区域人口
    base_year: int = 2015, # alpha 调和基准年（官方=2010，本实现=2015）
) -> LogLogFunc:
    """
    使用官方 fit_funcs.LogLogFunc 对单个 GCAM 区域拟合 log-log 回归。

    回归方程（官方）:
        log(TFC/GDP) = α + β × log(GDP/POP)

    拟合后进行 alpha 调和（官方 enlong_calc_2021:22944 fun_harmonize_alpha）：
        α += log(EI_base) - (α + β × log(GDP_pcap_base))
    确保回归线精确通过基准年观测值。

    返回拟合好的 LogLogFunc 实例，可直接调用 .predict_y(x) 进行预测。
    """
    gdp_pcap = gcam_gdp / gcam_pop.clip(1e-10)
    ei = gcam_tfc / gcam_gdp.clip(1e-10)

    mask = (gdp_pcap > 0) & (ei > 0)
    if mask.sum() < 3:
        ff = LogLogFunc(alpha=0.0, beta=1.0)
        ff.r_squared = 0.0
        return ff

    x = gdp_pcap[mask].values.astype(float)
    y = ei[mask].values.astype(float)

    ff = LogLogFunc()
    with _suppress_np_warnings():
        ff.fit(pd.Series(x), pd.Series(y))

    # ── ENLONG alpha 调和（官方 fun_harmonize_alpha, utils.py:24672）──
    # α += log(y_base) - (α + β × log(x_base))
    # 官方基准年=2010，本实现用 2015 以对齐 IEA 基年
    base_mask = mask & (gcam_gdp.index == base_year) & (gcam_pop.index == base_year)
    if base_mask.any() and ff.r_squared and ff.r_squared > 0:
        idx = gcam_gdp.index[base_mask][0]
        ei_base = ei[idx]
        gdp_pcap_base = gdp_pcap[idx]
        if ei_base > 0 and gdp_pcap_base > 0:
            ly_base = np.log(float(ei_base))
            lx_base = np.log(float(gdp_pcap_base))
            alpha_raw = ff.alpha or 0.0
            beta_val = ff.beta or 0.0
            ff.alpha = alpha_raw + ly_base - (alpha_raw + beta_val * lx_base)

    return ff


def predict_enlong(
    ff: LogLogFunc,
    gdp_c: float,
    pop_c: float,
    y_den: float,
) -> float:
    """
    用拟合结果预测国家级的 ENLONG 值。

    ENLONG_c = exp(α + β × log(GDP_c/POP_c)) × Y_DEN_c
    其中 Y_DEN 对总 TFC 而言 = GDP_c（官方 sector 0 的处理方式）。
    """
    if gdp_c <= 0 or pop_c <= 0:
        return 0.0
    x = gdp_c / pop_c
    ei = ff.predict_y(pd.Series([x])).iloc[0]
    return float(max(ei, 0.0) * y_den)


# ═══════════════════════════════════════════════════════════
# ENSHORT: 逐国历史回归 (1970-2015)
# ═══════════════════════════════════════════════════════════

def fit_enshort_countries(
    iea_hist_tfc: dict[str, dict[int, float]],
    ssp_gdp_hist: dict[str, dict[int, float]],
    ssp_pop_hist: dict[str, dict[int, float]],
    base_year: int = 2015,
) -> dict[str, dict]:
    """对每个国家做历史 log-log 回归，返回 ENSHORT 参数。

    回归方程 (与官方 DSCALE 完全一致):
        log(TFC / GDP) = α + β × log(GDP / POP)

    拟合后执行 alpha 调和 (utils.py:24640-24683 fun_harmonize_alpha):
        alpha += log(y_base) - (alpha + beta * log(x_base))
    确保回归线精确通过基准年观测值。

    Returns:
        {iso: {"alpha": float, "beta": float, "r_squared": float,
               "n_points": int, "hist_start": int, "hist_end": int}}
        仅返回至少有 5 个有效数据点的国家
    """
    params: dict[str, dict] = {}

    for iso, annual_tfc in iea_hist_tfc.items():
        if iso not in ssp_gdp_hist or iso not in ssp_pop_hist:
            continue

        # 构建对齐的时间序列，同时记录 year→(x,y) 映射用于 alpha 调和
        years = sorted(annual_tfc.keys())
        year_x, year_y = {}, {}
        x_vals, y_vals = [], []
        for y in years:
            if y > 2015:
                continue
            if y not in ssp_gdp_hist[iso] or y not in ssp_pop_hist[iso]:
                continue
            g = ssp_gdp_hist[iso].get(y, 0)
            p = ssp_pop_hist[iso].get(y, 0)
            e = annual_tfc.get(y, 0)
            if g <= 0 or p <= 0 or e <= 0:
                continue
            ei = e / g
            gdp_pcap = g / p
            if ei <= 0 or gdp_pcap <= 0:
                continue
            lx, ly = np.log(gdp_pcap), np.log(ei)
            x_vals.append(lx)
            y_vals.append(ly)
            year_x[y] = lx
            year_y[y] = ly

        if len(x_vals) < 5:
            continue

        x_arr = np.array(x_vals, dtype=float)
        y_arr = np.array(y_vals, dtype=float)
        ff = LogLogFunc()
        try:
            ff.fit(pd.Series(x_arr), pd.Series(y_arr))
        except (ValueError, RuntimeError):
            continue  # 无法回归（零方差等），跳过该国

        # ── A2: alpha 调和 (官方 fun_harmonize_alpha, utils.py:24672) ──
        # alpha += log(y_base) - (alpha + beta * log(x_base))
        t = base_year
        if t not in year_y:
            # 回退到最接近基准年的可用年份（官方逻辑）
            available = sorted(year_y.keys())
            t = max(base_year, min(available)) if available else base_year
        if t in year_y and t in year_x:
            alpha_raw = ff.alpha or 0.0
            beta_val = ff.beta or 0.0
            ff.alpha = alpha_raw + year_y[t] - (alpha_raw + beta_val * year_x[t])

        hist_years = sorted(year_y.keys())
        params[iso] = {
            "alpha": ff.alpha or 0.0,
            "beta": ff.beta or 0.0,
            "r_squared": ff.r_squared or 0.0,
            "n_points": len(x_vals),
            "hist_start": hist_years[0],
            "hist_end": hist_years[-1],
        }

    return params


# ═══════════════════════════════════════════════════════════
# 主降尺度函数
# ═══════════════════════════════════════════════════════════

def downscale_dscale_official(
    iea_baseline: dict[str, float],
    gcam: pd.DataFrame,
    scenario: str,
    ei_trends: dict[str, float] | None = None,
    enshort_params: dict[str, dict] | None = None,
) -> pd.DataFrame:
    """
    使用官方 DSCALE 算法进行 TFC 降尺度。

    计算流程:
      1. ENLONG: 区域 log-log 回归（官方 LogLogFunc）
      2. ENSHORT: 逐国历史回归 (1970-2015) 或 GDP 缩放回退
      3. 收敛: 官方 fun_max_tc_convergence（含 β 指数）
      4. 区域调和: 缩放以匹配 GCAM 总量

    Args:
        enshort_params: {iso: {alpha, beta, r_squared, n_points}},
            来自 fit_enshort_countries()。为 None 时回退到 ei_trends 或 GDP 缩放。
    """
    mapping = load_mapping()
    members_by_region = build_region_members(mapping)
    gdp_c = read_gdp_country(gdp_country_path(scenario)).set_index("iso")
    pop_c = read_pop_country(pop_country_path(scenario)).set_index("iso")
    gdp_r = read_gdp_region(gdp_region_path(scenario))
    pop_r_df = read_pop_region(pop_region_path(scenario))

    enshort_params = enshort_params or {}
    n_enshort_regression = len(enshort_params)

    iso_info = _build_iso_info(mapping)
    gcam_scen = gcam[gcam["Scenario"] == scenario]
    rows_out = []

    for _, g_row in gcam_scen.iterrows():
        region = g_row["Region"]
        mlist = members_by_region.get(region, [])
        region_isos = _region_isos(mlist)
        n_r = len(region_isos)
        if n_r == 0:
            continue

        r_gdp_row = gdp_r[gdp_r["Region"] == region]
        r_pop_row = pop_r_df[pop_r_df["Region"] == region]
        if r_gdp_row.empty:
            continue

        # ── 1. ENLONG: 官方 LogLogFunc 回归（1990-2100，与官方 DSCALE 对齐）──
        gcam_tfc_s = pd.Series(
            {y: float(g_row.get(y, 0) or 0) for y in ENLONG_YEARS}, dtype=float
        )
        gcam_gdp_s = pd.Series(
            {y: float(r_gdp_row[y].iloc[0]) if y in r_gdp_row.columns else 0.0
             for y in ENLONG_YEARS}, dtype=float
        )
        gcam_pop_s = pd.Series(
            {y: float(r_pop_row[y].iloc[0]) if y in r_pop_row.columns else 0.0
             for y in ENLONG_YEARS}, dtype=float
        )

        ff = fit_enlong_official(gcam_tfc_s, gcam_gdp_s, gcam_pop_s)
        beta_enlong = ff.beta or 0.0
        r2 = ff.r_squared or 0.0

        # ── 2. 逐国计算 + 收敛 ──
        projections: dict[str, dict[int, float]] = {iso: {} for iso in region_isos}

        for iso in region_isos:
            # A3: 官方 fun_max_tc — 逐国动态 MAX_TC
            ep = enshort_params.get(iso)
            if ep and ep.get("r_squared", 0) > 0:
                max_tc = fun_max_tc(
                    beta_short=ep.get("beta", 0.0),
                    r_squared_short=ep.get("r_squared", 0.0),
                    hist_start=ep.get("hist_start", 1990),
                    hist_end=ep.get("hist_end", 2015),
                    beta_long=beta_enlong,
                )
            elif r2 > 0.99:
                max_tc = 2200.0  # ENLONG 高 R² 但无 ENSHORT 回归: 慢收敛
            elif r2 > 0.95:
                max_tc = 2120.0  # 中等 ENLONG R²
            else:
                max_tc = 2040.0  # 低 R²: 快收敛
            e_iea = iea_baseline.get(iso, 0.0)
            g_2015 = float(gdp_c.loc[iso, 2015]) if iso in gdp_c.index else 0.0
            I_c_2015 = e_iea / g_2015 if g_2015 > 0 else 0.0

            for y in YEARS:
                g_c_y = float(gdp_c.loc[iso, y]) if iso in gdp_c.index and y in gdp_c.columns else 0.0
                p_c_y = float(pop_c.loc[iso, y]) if iso in pop_c.index and y in pop_c.columns else 0.0

                # ENSHORT: 优先使用逐国历史回归，其次 2015-2020 趋势，最后 GDP 缩放
                ep = enshort_params.get(iso)
                if ep and ep.get("r_squared", 0) > 0 and g_c_y > 0 and p_c_y > 0:
                    # 官方 log-log 回归: log(EI) = α + β × log(GDP/POP)
                    gdp_pcap = g_c_y / max(p_c_y, 1e-6)
                    ei_enshort = float(np.clip(
                        np.exp(ep["alpha"] + ep["beta"] * np.log(max(gdp_pcap, 1e-10))),
                        0.0, 1.0))  # A4: 官方 step1_fun_enshort_ei .clip(0,1)
                    enshort_val = ei_enshort * g_c_y
                elif ei_trends and iso in ei_trends:
                    # 2015-2020 观测趋势外推
                    ei_t = I_c_2015 * ((1.0 + ei_trends[iso]) ** (y - 2015))
                    enshort_val = ei_t * g_c_y if I_c_2015 > 0 else 0.0
                else:
                    # GDP 缩放（保持基年 EI 不变）
                    enshort_val = I_c_2015 * g_c_y if I_c_2015 > 0 else 0.0

                # ENLONG: 官方 LogLogFunc 预测
                if g_c_y > 0 and p_c_y > 0 and r2 > 0:
                    enlong_val = predict_enlong(ff, g_c_y, p_c_y, g_c_y)
                else:
                    enlong_val = enshort_val

                # ── 官方收敛公式（含 β 指数）──
                # 官方使用逐国 ENSHORT β（BETA 列）；无 ENSHORT 回归时回退到 β_enlong
                conv_beta = ep.get("beta", beta_enlong) if ep and ep.get("r_squared", 0) > 0 else beta_enlong
                t_arr = np.array([y], dtype=float)
                es_arr = np.array([enshort_val], dtype=float)
                el_arr = np.array([enlong_val], dtype=float)
                mtc_arr = np.array([max_tc], dtype=float)
                beta_arr = np.array([conv_beta], dtype=float)

                converged = fun_max_tc_convergence(es_arr, el_arr, t_arr, mtc_arr, beta_arr)
                projections[iso][y] = float(converged[0])

        # ── 3. 区域调和 ──
        _regional_conserve(projections, region_isos, g_row, n_r)

        for iso in region_isos:
            rows_out.append(_make_row(scenario, iso, region, iso_info, projections[iso]))

    return _finalize_df(rows_out, gcam_scen)


# ═══════════════════════════════════════════════════════════
# 通用入口：支持所有指标（TFC + 非 TFC）
# ═══════════════════════════════════════════════════════════

def downscale_dscale_generic(
    iea_baseline: dict[str, float],
    gcam: pd.DataFrame,
    scenario: str,
) -> pd.DataFrame:
    """官方 DSCALE 算法的通用入口，适用于所有无界量指标。

    对非 TFC 指标（无 IEA 历史数据），ENSHORT 自动回退到 GDP 缩放。
    对 TFC 指标，推荐使用 dscale/downscale_tfc.py 中的专用入口（含 ENSHORT 回归）。
    """
    return downscale_dscale_official(iea_baseline, gcam, scenario, enshort_params=None)
