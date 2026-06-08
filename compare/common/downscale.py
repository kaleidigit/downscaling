"""通用三方案降尺度引擎。

所有无界量指标（TFC、发电量、TES、CO₂等）共享相同的数学结构：
  - Logit: 基年 IEA 份额 × 区域总量
  - Kaya:  能源强度条件收敛
  - DSCALE: NAT + IAMatt 双路径合成

本模块将三方案实现为参数化函数，通过 IndicatorConfig 切换数据源。
"""

import numpy as np
import pandas as pd

from .config import (
    YEARS, IndicatorConfig,
    gdp_country_path, pop_country_path, gdp_region_path, pop_region_path,
)
from .io import (
    read_iea_generic, read_gcam_generic, read_gcam_fossil_tes,
    read_edgar_industry, read_edgar_co2,
    read_iea_other_values,
    read_gdp_country, read_pop_country, read_gdp_region, read_pop_region,
    write_output_for,
)
from .mapping import (
    normalize_name, load_mapping, build_region_members, EXCLUDED_ISO,
)
from .conservation import (
    check_regional_conservation, check_global_conservation, write_log,
)

OTHER_AFRICA = normalize_name("Other non-OECD Africa")
OTHER_AMERICAS = normalize_name("Other non-OECD Americas")
OTHER_ASIA = normalize_name("Other non-OECD Asia Oceania")
AGG_KEYS = {OTHER_AFRICA, OTHER_AMERICAS, OTHER_ASIA}

TC_DEFAULT = {"SSP126": 2070, "SSP245": 2085, "SSP434": 2100, "SSP460": 2100}


# ═══════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════

def load_baseline(cfg: IndicatorConfig) -> dict[str, float]:
    """加载基年基准值 {iso: value}，优先 IEA，其次 EDGAR。"""
    if cfg.edgar_path and cfg.edgar_path.exists():
        if cfg.key == "industry_co2":
            return read_edgar_industry(cfg.edgar_path)
        elif cfg.key == "co2_emissions":
            return read_edgar_co2(cfg.edgar_path)
    result = read_iea_generic(cfg.iea_path, cfg.iea_flow, cfg.iea_product, cfg.iea_year)
    if cfg.iea_unit_factor != 1.0:
        result = {iso: v * cfg.iea_unit_factor for iso, v in result.items()}
    return result


def load_gcam(cfg: IndicatorConfig, scenario: str) -> pd.DataFrame:
    """加载 GCAM 区域数据。"""
    path = cfg.gcam_path(scenario)
    if cfg.key == "fossil_tes":
        return read_gcam_fossil_tes(path)
    return read_gcam_generic(
        path,
        filter_col=cfg.gcam_filter_col,
        filter_value=cfg.gcam_filter_value,
        extra_filters=cfg.gcam_extra_filter,
        unit_factor=cfg.gcam_unit_factor,
    )


def load_iea_other(cfg: IndicatorConfig) -> dict[str, float]:
    """加载 IEA Other 区域聚合值。

    Other 值 = GCAM 区域总量 - 区域内已由 IEA 单列国家覆盖的值。
    这正确处理了 IEA 将这些小国归入 "Other non-OECD *" 聚合区域的情况。
    """
    if cfg.edgar_path and cfg.edgar_path.exists():
        return {}  # EDGAR 无 Other 区域

    mapping = load_mapping()
    members_by_region = build_region_members(mapping)
    iea_single = load_baseline(cfg)
    gcam = load_gcam(cfg, "SSP126")
    gcam_2015 = gcam[gcam["Scenario"] == "SSP126"]

    # GCAM 区域 2015 总量
    region_gcam = {}
    for _, g_row in gcam_2015.iterrows():
        region_gcam[g_row["Region"]] = float(g_row.get(2015, 0) or 0)

    # 区域内 IEA 单列国家值之和
    region_iea = {}
    for region, mlist in members_by_region.items():
        total = 0.0
        for m in mlist:
            iso = m["iso"]
            if iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            total += iea_single.get(iso, 0.0)
        region_iea[region] = total

    # 按 Other 聚合键计算残差
    result: dict[str, float] = {}
    for ak in AGG_KEYS:
        residual = 0.0
        seen_regions = set()
        for region, mlist in members_by_region.items():
            for m in mlist:
                if _agg_key_for_member(m) == ak and region not in seen_regions:
                    seen_regions.add(region)
                    gcam_val = region_gcam.get(region, 0.0)
                    iea_val = region_iea.get(region, 0.0)
                    residual += max(0, gcam_val - iea_val)
                    break
        result[ak] = residual

    return result


# ═══════════════════════════════════════════════════
# Other 区域人口拆分（Logit 用）
# ═══════════════════════════════════════════════════

def _agg_key_for_member(m: dict) -> str | None:
    iea_norm = m.get("iea_ctry", "")
    if iea_norm in AGG_KEYS:
        return iea_norm
    for c in m.get("candidates", []):
        n = normalize_name(c)
        if n in AGG_KEYS:
            return n
    return None


def build_iea_baseline(
    iea_single: dict[str, float],
    iea_other: dict[str, float],
    scenario: str,
) -> dict[str, float]:
    """将 IEA 单列国家 + Other 人口拆分合并为完整基年基准。"""
    mapping = load_mapping()
    members_by_region = build_region_members(mapping)
    pop = read_pop_country(pop_country_path(scenario))

    pop2015: dict[str, float] = {}
    for _, row in pop.iterrows():
        pop2015[str(row["iso"]).lower().strip()] = float(row.get(2015, 0) or 0)

    # 识别 Other 成员
    agg_sets: dict[str, set[str]] = {ak: set() for ak in AGG_KEYS}
    for mlist in members_by_region.values():
        for m in mlist:
            iso = m["iso"]
            if iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            if iso in iea_single:
                continue
            ak = _agg_key_for_member(m)
            if ak and ak in agg_sets:
                agg_sets[ak].add(iso)

    # 人口拆分
    agg_split: dict[str, float] = {}
    for ak, iso_set in agg_sets.items():
        if not iso_set:
            continue
        total = iea_other.get(ak, 0.0)
        iso_list = sorted(iso_set)
        pops = [pop2015.get(iso, 0.0) for iso in iso_list]
        s_pop = sum(pops)
        if s_pop > 0:
            for idx, iso in enumerate(iso_list):
                agg_split[iso] = total * (pops[idx] / s_pop)
        else:
            eq = total / len(iso_list)
            for iso in iso_list:
                agg_split[iso] = eq

    baseline: dict[str, float] = {}
    for iso in set(iea_single.keys()) | set(agg_split.keys()):
        baseline[iso] = iea_single.get(iso, 0.0) + agg_split.get(iso, 0.0)
    return baseline


# ═══════════════════════════════════════════════════
# 方案 A: Kaya 收敛法
# ═══════════════════════════════════════════════════

def gamma_c(gdp_pcap_2015: float, gdp_pcap_world_2015: float) -> float:
    """Kaya 收敛速度参数，基于人均 GDP（非总量 GDP）。

    文献: van Vuuren 2007 提出收敛速度与经济水平相关;
          Gidden 2019 标准化为 CMIP6 排放降尺度方法。
    0.3 系数: 项目校准参数，未在文献中找到确切出处。
    """
    if gdp_pcap_world_2015 <= 0 or gdp_pcap_2015 <= 0:
        return 1.0
    return 1.0 + 0.3 * np.log(gdp_pcap_2015 / gdp_pcap_world_2015)


def phi_kaya(t: int, gamma: float, tc: int) -> float:
    if t <= 2015:
        return 0.0
    return 1.0 - np.exp(-gamma * (t - 2015) / (tc - 2015))


def downscale_kaya(
    iea_baseline: dict[str, float],
    gcam: pd.DataFrame,
    scenario: str,
    cfg: IndicatorConfig,
) -> pd.DataFrame:
    mapping = load_mapping()
    members_by_region = build_region_members(mapping)
    gdp_c = read_gdp_country(gdp_country_path(scenario)).set_index("iso")
    pop_c = read_pop_country(pop_country_path(scenario)).set_index("iso")
    gdp_r = read_gdp_region(gdp_region_path(scenario))
    tc = TC_DEFAULT.get(scenario, 2100)

    # C1 修复: 使用人均 GDP（非总量 GDP）计算 γ
    pop_world_2015 = float(pop_c[2015].sum())
    gdp_world_2015 = float(gdp_c[2015].sum())
    gdp_pcap_world = gdp_world_2015 / pop_world_2015 if pop_world_2015 > 0 else 1.0

    iso_info = _build_iso_info(mapping)
    gcam_scen = gcam[gcam["Scenario"] == scenario]
    rows_out = []

    for _, g_row in gcam_scen.iterrows():
        region = g_row["Region"]
        mlist = members_by_region.get(region, [])
        region_isos = _region_isos(mlist)
        n_r = len(region_isos)
        r_gdp = gdp_r[gdp_r["Region"] == region]
        if r_gdp.empty:
            continue

        # I_R(t)
        I_R: dict[int, float] = {}
        for y in YEARS:
            gcam_val = float(g_row.get(y, 0) or 0)
            gdp_val = float(r_gdp[y].iloc[0]) if y in r_gdp.columns else 0.0
            I_R[y] = gcam_val / gdp_val if gdp_val > 0 else 0.0

        projections: dict[str, dict[int, float]] = {iso: {} for iso in region_isos}
        for iso in region_isos:
            e_base = iea_baseline.get(iso, 0.0)
            g_2015 = float(gdp_c.loc[iso, 2015]) if iso in gdp_c.index else 0.0
            p_2015 = float(pop_c.loc[iso, 2015]) if iso in pop_c.index else 1.0
            I_c_2015 = e_base / g_2015 if g_2015 > 0 else 0.0
            gdp_pcap_2015 = g_2015 / p_2015 if p_2015 > 0 else 0.0
            gam = gamma_c(gdp_pcap_2015, gdp_pcap_world)

            for y in YEARS:
                g_c_y = float(gdp_c.loc[iso, y]) if iso in gdp_c.index and y in gdp_c.columns else 0.0
                if y == 2015:
                    I_c_t = I_c_2015 if I_c_2015 > 0 else I_R.get(y, 0.0)
                elif I_c_2015 > 0:
                    phi_t = phi_kaya(y, gam, tc)
                    ratio = I_R.get(y, 0.0) / I_R.get(2015, 1.0) if I_R.get(2015, 0) > 0 else 1.0
                    I_c_t = I_c_2015 * (ratio ** phi_t)
                    # L1: 有 IEA 基准的小国 EI 不低于基年 EI 的 10%
                    if I_c_t < I_c_2015 * 0.1:
                        I_c_t = I_c_2015 * 0.1
                else:
                    # L1 fix: 无 IEA 基准的国家，始终使用区域 EI（与 2015 年一致）
                    I_c_t = I_R.get(y, 0.0)
                projections[iso][y] = I_c_t * g_c_y

        _regional_conserve(projections, region_isos, g_row, n_r)

        for iso in region_isos:
            rows_out.append(_make_row(scenario, iso, region, iso_info, projections[iso]))

    return _finalize_df(rows_out, gcam_scen)


# ═══════════════════════════════════════════════════
# 方案 B: DSCALE — 官方算法 (Sferra et al. 2026)
# ═══════════════════════════════════════════════════
#
# 与 https://github.com/fabiosferra/DSCALE 一致：
#
# ENLONG（长期投影）：
#   对每个 GCAM 区域做 log-log 回归：
#     log(TFC_region/GDP_region) = α + β × log(GDP_region/POP_region)
#   使用 GCAM 时间序列 (2015-2100) 作为回归数据。
#   然后应用到该区域每个国家：
#     ENLONG_c(t) = exp(α + β × log(GDP_c(t)/POP_c(t))) × GDP_c(t)
#
# ENSHORT（短期投影）：
#   由于缺乏逐国历史 IEA 时序数据，使用 GDP 缩放近似：
#     ENSHORT_c(t) = IEA_c × (GDP_c(t) / GDP_c(2015))
#   （保持 2015 年能源强度不变）
#
# 收敛 (fun_max_tc_convergence)：
#   CONV_WEIGHT = ((t - MAX_TC) / (2010 - MAX_TC)).clip(0, 1)
#   E_c(t) = ENSHORT × CONV_WEIGHT + ENLONG × (1 - CONV_WEIGHT)
#
# 调和：缩放以匹配 GCAM 区域总量。

# MAX_TC: 收敛完成年份（官方默认 2200 = 期内几乎不收敛）
MAX_TC_DEFAULT = 2200


def _simple_linregress(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """numpy 实现的简单线性回归，返回 (r_squared, slope, intercept)。"""
    n = len(x)
    sx, sy = x.sum(), y.sum()
    sxx = (x * x).sum()
    sxy = (x * y).sum()
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-15:
        return 0.0, 0.0, 0.0
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n
    y_pred = intercept + slope * x
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return r2, slope, intercept


def _fit_enlong_region(
    gcam_tfc: pd.Series,
    gcam_gdp: pd.Series,
    gcam_pop: pd.Series,
) -> tuple[float, float, float]:
    """对单个 GCAM 区域拟合 log-log 回归，返回 (r_squared, beta, alpha)。

    回归方程: log(TFC/GDP) = α + β × log(GDP/POP)
    使用 GCAM 时间序列 (2015-2100) 作为数据。
    """
    gdp_pcap = gcam_gdp / gcam_pop.clip(1e-10)
    ei = gcam_tfc / gcam_gdp.clip(1e-10)

    mask = (gdp_pcap > 0) & (ei > 0)
    if mask.sum() < 3:
        return 0.0, 0.0, 0.0

    x = np.log(gdp_pcap[mask].values)
    y = np.log(ei[mask].values)

    valid = np.isfinite(x) & np.isfinite(y)
    if valid.sum() < 3:
        return 0.0, 0.0, 0.0

    return _simple_linregress(x[valid], y[valid])


def downscale_dscale(
    iea_baseline: dict[str, float],
    gcam: pd.DataFrame,
    scenario: str,
    cfg: IndicatorConfig,
) -> pd.DataFrame:
    """官方 DSCALE 算法：ENLONG (区域回归) + ENSHORT (GDP 缩放) + MAX_TC 收敛。"""
    mapping = load_mapping()
    members_by_region = build_region_members(mapping)
    gdp_c = read_gdp_country(gdp_country_path(scenario)).set_index("iso")
    pop_c = read_pop_country(pop_country_path(scenario)).set_index("iso")
    gdp_r = read_gdp_region(gdp_region_path(scenario))
    pop_r_df = read_pop_region(pop_region_path(scenario))

    max_tc = MAX_TC_DEFAULT

    iso_info = _build_iso_info(mapping)
    gcam_scen = gcam[gcam["Scenario"] == scenario]
    rows_out = []

    for _, g_row in gcam_scen.iterrows():
        region = g_row["Region"]
        mlist = members_by_region.get(region, [])
        region_isos = _region_isos(mlist)
        n_r = len(region_isos)

        r_gdp_row = gdp_r[gdp_r["Region"] == region]
        r_pop_row = pop_r_df[pop_r_df["Region"] == region]
        if r_gdp_row.empty:
            continue

        # ---- 拟合区域 log-log 回归 (ENLONG) ----
        gcam_tfc_series = pd.Series({y: float(g_row.get(y, 0) or 0) for y in YEARS})
        gcam_gdp_series = pd.Series({y: float(r_gdp_row[y].iloc[0]) if y in r_gdp_row.columns else 0.0 for y in YEARS})
        gcam_pop_series = pd.Series({y: float(r_pop_row[y].iloc[0]) if y in r_pop_row.columns else 0.0 for y in YEARS})

        r2, beta, alpha = _fit_enlong_region(gcam_tfc_series, gcam_gdp_series, gcam_pop_series)

        # ---- 计算 ENLONG 和 ENSHORT 并收敛 ----
        projections: dict[str, dict[int, float]] = {iso: {} for iso in region_isos}

        for iso in region_isos:
            e_iea = iea_baseline.get(iso, 0.0)
            g_2015 = float(gdp_c.loc[iso, 2015]) if iso in gdp_c.index else 0.0
            I_c_2015 = e_iea / g_2015 if g_2015 > 0 else 0.0

            for y in YEARS:
                g_c_y = float(gdp_c.loc[iso, y]) if iso in gdp_c.index and y in gdp_c.columns else 0.0
                p_c_y = float(pop_c.loc[iso, y]) if iso in pop_c.index and y in pop_c.columns else 0.0

                # ENSHORT: GDP 缩放基年 TFC（保持能源强度不变）
                enshort = I_c_2015 * g_c_y if I_c_2015 > 0 else 0.0

                # ENLONG: exp(α + β × log(GDP/POP)) × GDP
                if g_c_y > 0 and p_c_y > 0 and r2 > 0:
                    gdp_pcap = g_c_y / p_c_y
                    enlong = np.exp(alpha + beta * np.log(gdp_pcap)) * g_c_y
                    enlong = max(enlong, 0.0)
                else:
                    enlong = enshort

                # MAX_TC 收敛 (A6: +beta 指数, 官方 Energy_demand_downs_1.py:661)
                conv_weight = (y - max_tc) / (2010 - max_tc)
                conv_weight = np.clip(conv_weight, 0.0, 1.0)
                conv_weight = conv_weight ** max(abs(beta), 1.0)

                projections[iso][y] = enshort * conv_weight + enlong * (1.0 - conv_weight)

        # ---- 区域调和 ----
        _regional_conserve(projections, region_isos, g_row, n_r)

        for iso in region_isos:
            rows_out.append(_make_row(scenario, iso, region, iso_info, projections[iso]))

    return _finalize_df(rows_out, gcam_scen)


# ═══════════════════════════════════════════════════
# 方案 C: Logit 比例分配法
# ═══════════════════════════════════════════════════

def downscale_logit(
    iea_baseline: dict[str, float],
    gcam: pd.DataFrame,
    scenario: str,
    cfg: IndicatorConfig,
) -> pd.DataFrame:
    mapping = load_mapping()
    members_by_region = build_region_members(mapping)
    iso_info = _build_iso_info(mapping)

    gcam_scen = gcam[gcam["Scenario"] == scenario]
    rows_out = []

    for _, g_row in gcam_scen.iterrows():
        region = g_row["Region"]
        mlist = members_by_region.get(region, [])
        region_isos = _region_isos(mlist)

        region_iea_sum = sum(iea_baseline.get(iso, 0.0) for iso in region_isos)

        if region_iea_sum <= 0:
            # 区域内所有国家 IEA 基准均为零：均分 GCAM 区域值
            equal_share = 1.0 / n_r if n_r > 0 else 0.0
            for iso in region_isos:
                row = {"Scenario": scenario, "iso": iso,
                       "Country": iso_info.get(iso, {}).get("Country", ""),
                       "Region": region}
                for y in YEARS:
                    row[y] = equal_share * float(g_row.get(y, 0) or 0)
                rows_out.append(row)
        else:
            for iso in region_isos:
                base_val = iea_baseline.get(iso, 0.0)
                share = base_val / region_iea_sum
                row = {"Scenario": scenario, "iso": iso,
                       "Country": iso_info.get(iso, {}).get("Country", ""),
                       "Region": region}
                for y in YEARS:
                    row[y] = share * float(g_row.get(y, 0) or 0)
                rows_out.append(row)

    return _finalize_df(rows_out, gcam_scen)


# ═══════════════════════════════════════════════════
# 共享工具
# ═══════════════════════════════════════════════════

def _build_iso_info(mapping: pd.DataFrame) -> dict[str, dict]:
    info: dict[str, dict] = {}
    for _, row in mapping.iterrows():
        iso = str(row.get("iso", "")).lower().strip()
        if iso in EXCLUDED_ISO:
            continue
        iso = "chn" if iso == "twn" else iso
        display = (row.get("GCAM Country", "") or row.get("IEA_ctry", "")
                   or row.get("iso_ctry", "") or str(row.get("iso", "")))
        if iso not in info:
            info[iso] = {"Country": display, "Region": row["Region"]}
    return info


def _region_isos(mlist: list[dict]) -> list[str]:
    isos = []
    for m in mlist:
        iso = m["iso"]
        if iso in EXCLUDED_ISO:
            continue
        iso = "chn" if iso == "twn" else iso
        if iso not in isos:
            isos.append(iso)
    return isos


def _regional_conserve(projections, region_isos, g_row, n_r):
    for y in YEARS:
        total_proj = sum(projections[iso][y] for iso in region_isos)
        gcam_val = float(g_row.get(y, 0) or 0)
        if total_proj > 0:
            for iso in region_isos:
                projections[iso][y] = projections[iso][y] / total_proj * gcam_val
        else:
            for iso in region_isos:
                projections[iso][y] = gcam_val / n_r if n_r > 0 else 0.0


def _make_row(scenario, iso, region, iso_info, proj):
    row = {"Scenario": scenario, "iso": iso,
           "Country": iso_info.get(iso, {}).get("Country", ""),
           "Region": region}
    for y in YEARS:
        row[y] = round(proj[y], 6)
    return row


def _finalize_df(rows_out, gcam_scen):
    df_out = pd.DataFrame(rows_out)
    if df_out.empty or len(df_out.columns) == 0:
        return df_out
    residual_row = {"Scenario": df_out["Scenario"].iloc[0],
                    "iso": "oth", "Country": "Other Residual Global",
                    "Region": "Other Residual Global"}
    has_residual = False
    for y in YEARS:
        gcam_total = float(gcam_scen[y].sum())
        allocated = float(df_out[y].sum()) if y in df_out.columns else 0.0
        residual = gcam_total - allocated
        residual_row[y] = residual
        if abs(residual) > 1e-6:
            has_residual = True
    if has_residual:
        df_out = pd.concat([df_out, pd.DataFrame([residual_row])], ignore_index=True)
    for y in YEARS:
        if y in df_out.columns:
            df_out[y] = df_out[y].round(6)
    return df_out


# ═══════════════════════════════════════════════════
# 统一入口
# ═══════════════════════════════════════════════════

METHOD_FUNCTIONS = {
    "logit": downscale_logit,
    "kaya": downscale_kaya,
    "dscale": downscale_dscale,
}


def run_indicator(
    method: str,
    scenario: str,
    cfg: IndicatorConfig,
) -> pd.DataFrame:
    """对指定指标运行指定方案，返回降尺度 DataFrame。"""
    iea_single = load_baseline(cfg)

    iea_other = load_iea_other(cfg)
    iea_baseline = build_iea_baseline(iea_single, iea_other, scenario)

    gcam = load_gcam(cfg, scenario)

    if method == "dscale":
        from ..dscale.dscale_official import downscale_dscale_generic
        df = downscale_dscale_generic(iea_baseline, gcam, scenario)
    else:
        fn = METHOD_FUNCTIONS[method]
        df = fn(iea_baseline, gcam, scenario, cfg)

    # 校验和输出（所有方法统一）
    gcam_scen = gcam[gcam["Scenario"] == scenario]
    reports = [
        check_regional_conservation(df, gcam_scen),
        check_global_conservation(df, gcam_scen),
    ]

    n_single = len(iea_single)
    n_baseline = len(iea_baseline)
    log_lines = [f"IEA 匹配统计: 单列国家 {n_single} 个, 合并后基准 {n_baseline} 个"]

    write_output_for(df, method, scenario, cfg.output_prefix)
    log_path = write_log(f"{method}_{cfg.key}", log_lines + reports)
    from .config import OUTPUT_DIR
    log_path.rename(OUTPUT_DIR / f"{method}_{cfg.key}_log.txt")

    return df


# ═══════════════════════════════════════════════════
# Logit 份额计算（logit降尺度方案.md 阶段 1–3）
# ═══════════════════════════════════════════════════

def compute_logit_share(
    df_num: pd.DataFrame,       # 已降尺度的分子（如可再生 TES），含 iso, Region, [YEARS]
    df_den: pd.DataFrame,       # 已降尺度的分母（如总 TES）
    gcam_num: pd.DataFrame,     # GCAM 区域分子值 [Scenario, Region, YEARS]
    gcam_den: pd.DataFrame,     # GCAM 区域分母值
    scenario: str,
    eps: float = 1e-4,
    max_iter: int = 50,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """
    按 logit降尺度方案.md 计算份额指标。

    阶段 1: Logit 变换 S → L = ln(S/(1-S))
    阶段 2: Logit 空间叠加区域趋势 L_c,t = L_c,2015 + ΔL_R,t
    阶段 3: 逆 Logit → 迭代缩放封顶校准
    """
    mapping = load_mapping()
    members_by_region = build_region_members(mapping)

    gcam_num_scen = gcam_num[gcam_num["Scenario"] == scenario]
    gcam_den_scen = gcam_den[gcam_den["Scenario"] == scenario]

    rows_out = []
    for _, g_row_num in gcam_num_scen.iterrows():
        region = g_row_num["Region"]
        g_row_den = gcam_den_scen[gcam_den_scen["Region"] == region]
        if g_row_den.empty:
            continue
        g_row_den = g_row_den.iloc[0]

        # 区域内国家的 ISO 列表
        mlist = members_by_region.get(region, [])
        region_isos = _region_isos(mlist)

        # 阶段 1：计算基年份额并 Logit 变换
        L_c_2015: dict[str, float] = {}
        S_c_2015: dict[str, float] = {}
        for iso in region_isos:
            num_2015 = float(df_num[df_num["iso"] == iso][2015].values[0]) if len(df_num[df_num["iso"] == iso]) > 0 else 0.0
            den_2015 = float(df_den[df_den["iso"] == iso][2015].values[0]) if len(df_den[df_den["iso"] == iso]) > 0 else 0.0
            s = num_2015 / den_2015 if den_2015 > 0 else 0.0
            s = np.clip(s, eps, 1 - eps)  # 边界裁剪
            S_c_2015[iso] = s
            L_c_2015[iso] = np.log(s / (1 - s))

        # GCAM 区域份额 → Logit
        S_R: dict[int, float] = {}
        L_R: dict[int, float] = {}
        for y in YEARS:
            nr = float(g_row_num.get(y, 0) or 0)
            dr = float(g_row_den.get(y, 0) or 0)
            s_r = nr / dr if dr > 0 else 0.0
            s_r = np.clip(s_r, eps, 1 - eps)
            S_R[y] = s_r
            L_R[y] = np.log(s_r / (1 - s_r))

        L_R_2015 = L_R.get(2015, 0.0)
        delta_L_R: dict[int, float] = {y: L_R[y] - L_R_2015 for y in YEARS}

        # 阶段 2：Logit 空间叠加区域趋势 → 逆变换
        S_proj: dict[str, dict[int, float]] = {}
        for iso in region_isos:
            S_proj[iso] = {}
            L_c = L_c_2015.get(iso, 0.0)
            for y in YEARS:
                L_proj = L_c + delta_L_R.get(y, 0.0)
                S_proj[iso][y] = 1.0 / (1.0 + np.exp(-L_proj))  # sigmoid

        # 阶段 3：迭代缩放封顶校准
        for y in YEARS:
            target = float(g_row_num.get(y, 0) or 0)
            E_c: dict[str, float] = {}
            for iso in region_isos:
                E_c[iso] = float(df_den[df_den["iso"] == iso][y].values[0]) if len(df_den[df_den["iso"] == iso]) > 0 else 0.0

            # 初始 R
            R_current = {iso: E_c.get(iso, 0.0) * S_proj[iso][y] for iso in region_isos}

            for _ in range(max_iter):
                sum_R = sum(R_current.values())
                if sum_R < 1e-12:
                    break
                error = target - sum_R
                if abs(error) < tol:
                    break

                # 缩放因子
                k = target / sum_R if sum_R > 0 else 1.0

                # 初步缩放 + 封顶
                capped_isos: set[str] = set()
                freed_amount = 0.0
                for iso in region_isos:
                    R_temp = R_current[iso] * k
                    e = E_c.get(iso, 0.0)
                    if e > 0 and R_temp > e:
                        R_current[iso] = e
                        capped_isos.add(iso)
                        freed_amount += (R_temp - e)
                    else:
                        R_current[iso] = R_temp

                # 将封顶释放的量重新分配给未封顶国家
                if capped_isos and freed_amount > 0:
                    uncapped = [iso for iso in region_isos if iso not in capped_isos]
                    uncapped_sum = sum(R_current[iso] for iso in uncapped)
                    if uncapped_sum > 0 and len(uncapped) > 0:
                        for iso in uncapped:
                            R_current[iso] += freed_amount * (R_current[iso] / uncapped_sum)

            # 最终份额（强制 [0,1] 封顶）
            for iso in region_isos:
                e = E_c.get(iso, 0.0)
                if e > 0:
                    R_current[iso] = min(R_current[iso], e)
                    S_proj[iso][y] = R_current[iso] / e
                else:
                    S_proj[iso][y] = 0.0

        for iso in region_isos:
            row = {"Scenario": scenario, "iso": iso,
                   "Country": "", "Region": region}
            for y in YEARS:
                row[y] = round(S_proj[iso][y], 6)
            rows_out.append(row)

    df_out = pd.DataFrame(rows_out)
    # Fill Country from numerator data
    iso_country = df_num.set_index("iso")["Country"].to_dict()
    df_out["Country"] = df_out["iso"].map(iso_country).fillna("")
    return df_out
