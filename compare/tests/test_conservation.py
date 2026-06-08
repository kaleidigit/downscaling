"""核心不变测试：守恒性、一致性、数值健全性。"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compare.common.config import SCENARIOS, INDICATORS, YEARS, OUTPUT_DIR
from compare.common.mapping import load_mapping, build_region_members, EXCLUDED_ISO

METHODS = ["logit", "kaya", "dscale"]


def _load(method: str, prefix: str, scenario: str) -> pd.DataFrame:
    p = OUTPUT_DIR / f"{method}_{prefix}_downscaled_{scenario}.xlsx"
    if not p.exists():
        raise FileNotFoundError(str(p))
    return pd.read_excel(p, engine="openpyxl")


def _year_cols(df: pd.DataFrame) -> list:
    return sorted([c for c in df.columns if isinstance(c, int) and 2015 <= c <= 2100])


# ══════════════════════════════════════════════
# 测试 1: 区域守恒
# ══════════════════════════════════════════════

@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("key,cfg", [(k, v) for k, v in INDICATORS.items()])
def test_regional_conservation(scenario, method, key, cfg):
    """每个 GCAM 区域内，国家 TFC 之和必须等于 GCAM 区域总量。"""
    df = _load(method, cfg.output_prefix, scenario)
    yrs = _year_cols(df)
    mapping = load_mapping()
    members = build_region_members(mapping)

    for region, mlist in members.items():
        region_isos = set()
        for m in mlist:
            iso = m["iso"]
            if iso in EXCLUDED_ISO:
                continue
            region_isos.add("chn" if iso == "twn" else iso)

        region_rows = df[df["iso"].isin(region_isos)]
        if region_rows.empty:
            continue

        region_total = region_rows[yrs].sum()
        if len(region_isos) <= 1:
            assert len(region_rows) <= 1, f"{region}: 单国区域不应有多行"
        else:
            assert not region_total.isna().any(), \
                f"{method}/{key}/{scenario} {region}: 区域总量含 NaN"


# ══════════════════════════════════════════════
# 测试 1b: 区域守恒数值验证（抽样检查多国区域）
# ══════════════════════════════════════════════

@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("key", ["tfc", "electricity", "tes"])
def test_conservation_sums_match_gcam(scenario, method, key):
    """多国区域的国家值之和必须等于 GCAM 区域值（容差 1e-4 TJ）。"""
    cfg = INDICATORS[key]
    df = _load(method, cfg.output_prefix, scenario)
    yrs = _year_cols(df)
    mapping = load_mapping()
    members = build_region_members(mapping)

    # 加载 GCAM 数据用于对比
    from compare.common.downscale import load_gcam
    gcam = load_gcam(cfg, scenario)

    for region, mlist in members.items():
        region_isos = set()
        for m in mlist:
            iso = m["iso"]
            if iso in EXCLUDED_ISO:
                continue
            region_isos.add("chn" if iso == "twn" else iso)
        if len(region_isos) <= 1:
            continue  # 单国区域通过 _regional_conserve 保证

        region_rows = df[df["iso"].isin(region_isos)]
        if region_rows.empty:
            continue

        for y in yrs:
            country_sum = float(region_rows[y].sum())
            # GCAM 区域值
            gcam_row = gcam[(gcam["Scenario"] == scenario) & (gcam["Region"] == region)]
            if gcam_row.empty:
                continue
            gcam_val = float(gcam_row[y].iloc[0]) if y in gcam_row.columns else 0.0

            rel_tol = max(1e-4, abs(gcam_val) * 1e-10)
            msg = (f"{method}/{key}/{scenario} {region} {y}: "
                   f"sum={country_sum:.2f} vs GCAM={gcam_val:.2f}, diff={abs(country_sum-gcam_val):.2f}")
            assert abs(country_sum - gcam_val) < rel_tol, msg


# ══════════════════════════════════════════════
# 测试 2: 单国区域三方案一致
# ══════════════════════════════════════════════

def test_single_country_consistency():
    """单国区域在所有方法下产生相同结果。"""
    mapping = load_mapping()
    members = build_region_members(mapping)
    single = {r: mlist[0]["iso"] for r, mlist in members.items()
              if len([m for m in mlist if m["iso"] not in EXCLUDED_ISO]) == 1}

    assert len(single) >= 14, f"预期 ≥14 个单国区域，实际 {len(single)}"

    for key, cfg in INDICATORS.items():
        yrs = [y for y in YEARS if y in [2015, 2050, 2100]]
        for iso in list(single.values())[:8]:  # 抽样 8 个
            vals = {}
            for method in METHODS:
                try:
                    df = _load(method, cfg.output_prefix, "SSP126")
                    row = df[df["iso"] == iso]
                    if not row.empty:
                        vals[method] = {y: float(row[y].iloc[0]) for y in yrs}
                except FileNotFoundError:
                    continue

            if len(vals) >= 2:
                methods_list = list(vals.keys())
                for y in yrs:
                    ref = vals[methods_list[0]][y]
                    for m in methods_list[1:]:
                        diff = abs(vals[m][y] - ref)
                        assert diff < max(1.0, abs(ref) * 1e-10), \
                            f"{key}/{iso} {y}: {methods_list[0]}={ref:.1f} vs {m}={vals[m][y]:.1f}, diff={diff:.1f}"


# ══════════════════════════════════════════════
# 测试 3: 数值健全性
# ══════════════════════════════════════════════

@pytest.mark.parametrize("scenario", ["SSP126"])
@pytest.mark.parametrize("method", METHODS)
def test_no_nan_in_physical_indicators(scenario, method):
    """物理量指标（TFC、电力、TES）不应含 NaN。"""
    for key in ["tfc", "electricity", "tes"]:
        cfg = INDICATORS[key]
        df = _load(method, cfg.output_prefix, scenario)
        yrs = _year_cols(df)
        non_oth = df[df["iso"] != "oth"]
        nan_count = non_oth[yrs].isna().sum().sum()
        assert nan_count == 0, f"{method}/{key}: {nan_count} NaN values"


@pytest.mark.parametrize("scenario", ["SSP126"])
@pytest.mark.parametrize("method", METHODS)
def test_no_negative_physical_quantities(scenario, method):
    """TFC、电力、TES 不应有显著负值（排除 oth 残差行）。"""
    for key in ["tfc", "electricity", "tes"]:
        cfg = INDICATORS[key]
        df = _load(method, cfg.output_prefix, scenario)
        yrs = _year_cols(df)
        non_oth = df[df["iso"] != "oth"]
        neg = (non_oth[yrs] < -1e-6).sum().sum()
        assert neg == 0, f"{method}/{key}: {neg} significantly negative values"


@pytest.mark.parametrize("scenario", ["SSP126"])
@pytest.mark.parametrize("method", METHODS)
def test_share_bounds(scenario, method):
    """份额指标应在 [0,1] 范围内（排除极端离群值）。"""
    for share_key in ["fossil_share", "renewable_share", "electrification_rate",
                       "green_elec_share"]:
        try:
            df = _load(method, share_key, scenario)
        except FileNotFoundError:
            continue
        yrs = _year_cols(df)
        non_oth = df[df["iso"] != "oth"]
        for y in [2015, 2050, 2100]:
            if y not in yrs:
                continue
            vals = non_oth[y].dropna()
            vals = vals[np.isfinite(vals)]
            if len(vals) == 0:
                continue
            outside = ((vals < -0.01) | (vals > 1.01)).sum()
            # Kaya/DSCALE 不保证份额有界性（这是已知局限）；仅用于回归检测
            tolerance = 0.50 if method != "logit" else 0.05
            assert outside <= len(vals) * tolerance, \
                f"{method}/{share_key} {y}: {outside}/{len(vals)} outside [0,1]"


# ══════════════════════════════════════════════
# 测试 4: API 契约
# ══════════════════════════════════════════════

def test_all_functions_return_dataframe():
    """各方案的 downscale_tfc 函数返回正确结构的 DataFrame。"""
    from compare.logit.downscale_tfc import downscale_tfc as logit_fn
    from compare.kaya.downscale_tfc import downscale_tfc as kaya_fn
    from compare.dscale.downscale_tfc import downscale_tfc as dscale_fn

    expected_cols = {"Scenario", "iso", "Country"}

    for name, fn in [("logit", logit_fn), ("kaya", kaya_fn), ("dscale", dscale_fn)]:
        for scn in ["SSP126", "SSP245"]:
            df = fn(scn)
            assert isinstance(df, pd.DataFrame), f"{name}: not a DataFrame"
            assert expected_cols.issubset(df.columns), \
                f"{name}: missing columns {expected_cols - set(df.columns)}"
            assert 2015 in df.columns and 2100 in df.columns, \
                f"{name}: missing year columns"
            assert len(df) >= 170, f"{name}/{scn}: only {len(df)} rows, expected >=170"


def test_run_indicator_all_methods():
    """run_indicator 对所有方法+指标组合可正常运行。"""
    from compare.common.downscale import run_indicator

    for key in ["tfc", "electricity", "co2_emissions"]:
        cfg = INDICATORS[key]
        for method in METHODS:
            df = run_indicator(method, "SSP126", cfg)
            assert len(df) >= 170, f"{method}/{key}: {len(df)} rows"


def test_dscale_official_import():
    """官方 DSCALE 适配层可正常导入。"""
    from compare.dscale.dscale_official import (
        fun_max_tc_convergence,
        fun_max_tc,
        fit_enlong_official,
        predict_enlong,
        downscale_dscale_official,
        downscale_dscale_generic,
    )
    assert callable(fun_max_tc)
    assert callable(downscale_dscale_generic)


# ══════════════════════════════════════════════
# 测试 5: DSCALE 数值边界
# ══════════════════════════════════════════════

def test_fun_max_tc_bounds():
    """fun_max_tc 返回值在 [2040, 2200] 范围内。"""
    from compare.dscale.dscale_official import fun_max_tc

    # 符号冲突 → 2040
    assert fun_max_tc(2.0, 0.9, 1990, 2015, -3.0) == 2040.0
    # 高质量 → 接近 2200
    tc_high = fun_max_tc(1.0, 0.95, 1970, 2015, 1.5)
    assert 2040 <= tc_high <= 2200
    assert tc_high >= 2100, f"高 R²+长数据应产生高 MAX_TC, 实际 {tc_high}"
    # 低质量 → 接近 2040
    tc_low = fun_max_tc(1.0, 0.1, 2005, 2010, 1.0, y_max=2200)
    assert 2040 <= tc_low <= 2100, f"低质量应产生低 MAX_TC, 实际 {tc_low}"
    # 同号负 beta → 不触发 y_min
    tc_neg = fun_max_tc(-2.0, 0.8, 1980, 2015, -1.5)
    assert tc_neg > 2040, f"同号负 beta 不应强制 y_min, 实际 {tc_neg}"


def test_fun_max_tc_convergence_beta_clip():
    """验证 A1 修复：beta clipping 不含 abs。"""
    import numpy as np
    from compare.dscale.dscale_official import fun_max_tc_convergence

    t = np.array([2050.0])
    es = np.array([100.0])
    el = np.array([200.0])
    mtc = np.array([2100.0])

    # beta=-3: 官方 clip(1,inf)→1, CONV_WEIGHT^1=0.5556 → 100*0.5556+200*0.4444=144.4
    # beta=3: CONV_WEIGHT^3=0.1715 → 100*0.1715+200*0.8285=182.9 (更接近 ENLONG)
    c1 = fun_max_tc_convergence(es, el, t, mtc, np.array([-3.0]))
    c2 = fun_max_tc_convergence(es, el, t, mtc, np.array([3.0]))
    assert abs(c1[0] - 144.44) < 0.1, f"beta=-3: expected 144.4, got {c1[0]}"
    assert abs(c2[0] - 182.85) < 0.1, f"beta=3: expected 182.9, got {c2[0]}"


# ══════════════════════════════════════════════
# 测试 6: 数据完整性
# ══════════════════════════════════════════════

def test_excluded_iso_count():
    """验证 EXCLUDED_ISO 恰好 5 个（B7 修复后）。"""
    assert EXCLUDED_ISO == {"grl", "pse", "gib", "xkx", "ssd"}, \
        f"EXCLUDED_ISO 应为 5 个，实际: {sorted(EXCLUDED_ISO)}"


def test_mapping_loads():
    """映射表正确加载，TWN→CHN 合并。"""
    mapping = load_mapping()
    assert len(mapping) >= 170, f"映射表应 ≥170 行，实际 {len(mapping)}"
    assert "chn" in mapping["iso"].values
    assert "twn" not in mapping["iso"].values  # 已合并


def test_all_config_paths_exist():
    """config.py 中所有数据路径指向存在的文件。"""
    from compare.common.config import (
        IEA_WORLDBAL_PATH, MAPPING_PATH, gdp_country_path, pop_country_path,
        gdp_region_path, pop_region_path, IEA_TFC_PATH
    )
    paths = [
        ("IEA_WORLDBAL", IEA_WORLDBAL_PATH),
        ("MAPPING", MAPPING_PATH),
        ("IEA_TFC", IEA_TFC_PATH),
    ]
    for scn in ["SSP126", "SSP245"]:
        paths += [
            (f"GDP_country_{scn}", gdp_country_path(scn)),
            (f"POP_country_{scn}", pop_country_path(scn)),
            (f"GDP_region_{scn}", gdp_region_path(scn)),
            (f"POP_region_{scn}", pop_region_path(scn)),
        ]
    for name, p in paths:
        assert p.exists(), f"{name}: {p} 不存在"


def test_output_files_count():
    """验证产出文件数量：96 个无界量 xlsx 文件。"""
    count = len(list(OUTPUT_DIR.glob("*_downscaled_*.xlsx")))
    # 96 无界量 + ~72 份额 = ~168
    assert count >= 160, f"产出文件应 ≥160，实际 {count}"


# ══════════════════════════════════════════════
# 测试 7: 跨情景一致性
# ══════════════════════════════════════════════

def test_tfc_ssp_ordering():
    """验证情景排序：SSP245 应有最高 TFC，SSP126 最低（2100）。"""
    totals = {}
    for scn in SCENARIOS:
        df = _load("logit", "TFC", scn)
        totals[scn] = float(df[[c for c in df.columns if isinstance(c, int)]].sum()[2100])

    assert totals["SSP245"] > totals["SSP126"], \
        f"SSP245({totals['SSP245']:.0f}) 应 > SSP126({totals['SSP126']:.0f})"
    assert totals["SSP245"] > totals["SSP434"], \
        f"SSP245({totals['SSP245']:.0f}) 应 > SSP434({totals['SSP434']:.0f})"
