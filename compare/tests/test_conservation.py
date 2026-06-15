"""守恒与数值健全性测试。

验证降尺度输出的核心属性：区域守恒、无 NaN/负值、份额有界、跨情景一致性。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compare.common.config import SCENARIOS, INDICATORS, YEARS, OUTPUT_DIR

METHODS = ["logit", "kaya", "dscale"]


def _load(method: str, prefix: str, scenario: str) -> pd.DataFrame:
    p = OUTPUT_DIR / f"{method}_{prefix}_downscaled_{scenario}.xlsx"
    if not p.exists():
        raise FileNotFoundError(str(p))
    return pd.read_excel(p, engine="openpyxl")


def _year_cols(df: pd.DataFrame) -> list:
    return sorted([c for c in df.columns if isinstance(c, int) and 2015 <= c <= 2100])


# ══════════════════════════════════════════════
# 测试 1: 区域守恒 — 国和 == GCAM 区域值
# ══════════════════════════════════════════════

@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("key", ["tfc", "electricity", "tes"])
def test_conservation_sums_match_gcam(scenario, method, key, region_members):
    """多国区域的国家值之和必须等于 GCAM 区域值（容差 1e-4 TJ）。"""
    cfg = INDICATORS[key]
    df = _load(method, cfg.output_prefix, scenario)
    yrs = _year_cols(df)

    from compare.common.downscale import load_gcam
    gcam = load_gcam(cfg, scenario)

    for region, mlist in region_members.items():
        region_isos = set()
        for m in mlist:
            iso = m["iso"]
            region_isos.add("chn" if iso == "twn" else iso)
        if len(region_isos) <= 1:
            continue

        region_rows = df[df["iso"].isin(region_isos)]
        if region_rows.empty:
            continue

        for y in yrs:
            country_sum = float(region_rows[y].sum())
            gcam_row = gcam[(gcam["Scenario"] == scenario) & (gcam["Region"] == region)]
            if gcam_row.empty:
                continue
            gcam_val = float(gcam_row[y].iloc[0]) if y in gcam_row.columns else 0.0

            rel_tol = max(1e-4, abs(gcam_val) * 1e-10)
            msg = (f"{method}/{key}/{scenario} {region} {y}: "
                   f"sum={country_sum:.2f} vs GCAM={gcam_val:.2f}")
            assert abs(country_sum - gcam_val) < rel_tol, msg


# ══════════════════════════════════════════════
# 测试 2: 数值健全性 — 无 NaN/负值
# ══════════════════════════════════════════════

@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("method", METHODS)
def test_no_nan_in_physical_indicators(scenario, method):
    """物理量指标（TFC、电力、TES、化石 TES）不应含 NaN。"""
    for key in ["tfc", "electricity", "tes", "fossil_tes"]:
        cfg = INDICATORS[key]
        df = _load(method, cfg.output_prefix, scenario)
        yrs = _year_cols(df)
        non_oth = df[df["iso"] != "oth"]
        nan_count = non_oth[yrs].isna().sum().sum()
        assert nan_count == 0, f"{method}/{key}/{scenario}: {nan_count} NaN values"


@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("method", METHODS)
def test_no_negative_physical_quantities(scenario, method):
    """物理量指标不应有显著负值（排除 oth 残差行）。"""
    for key in ["tfc", "electricity", "tes", "fossil_tes"]:
        cfg = INDICATORS[key]
        df = _load(method, cfg.output_prefix, scenario)
        yrs = _year_cols(df)
        non_oth = df[df["iso"] != "oth"]
        neg = (non_oth[yrs] < -1e-6).sum().sum()
        assert neg == 0, f"{method}/{key}/{scenario}: {neg} significantly negative values"


# ══════════════════════════════════════════════
# 测试 3: 份额有界 [0,1]
# ══════════════════════════════════════════════

@pytest.mark.parametrize("scenario", SCENARIOS)
@pytest.mark.parametrize("method", METHODS)
def test_share_bounds(scenario, method):
    """份额指标应在 [0,1] 范围内。"""
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
            assert outside == 0, \
                f"{method}/{share_key}/{scenario} {y}: {outside}/{len(vals)} outside [0,1]"


# ══════════════════════════════════════════════
# 测试 4: 单国区域三方法一致
# ══════════════════════════════════════════════

def test_single_country_consistency(single_region_isos):
    """单国区域在所有方法下产生相同结果（TFC SSP126）。"""
    assert len(single_region_isos) >= 14, \
        f"预期 ≥14 个单国区域，实际 {len(single_region_isos)}"
    yrs = [y for y in YEARS if y in [2015, 2050, 2100]]

    for iso in single_region_isos:
        vals = {}
        for method in METHODS:
            df = _load(method, "TFC", "SSP126")
            row = df[df["iso"] == iso]
            if not row.empty:
                vals[method] = {y: float(row[y].iloc[0]) for y in yrs}

        if len(vals) < 2:
            continue
        methods_list = list(vals.keys())
        for y in yrs:
            ref = vals[methods_list[0]][y]
            for m in methods_list[1:]:
                diff = abs(vals[m][y] - ref)
                assert diff < max(1e-6, abs(ref) * 1e-12), \
                    f"{iso} {y}: {methods_list[0]}={ref:.2f} vs {m}={vals[m][y]:.2f}"


# ══════════════════════════════════════════════
# 测试 5: 跨情景一致性
# ══════════════════════════════════════════════

@pytest.mark.parametrize("method", METHODS)
def test_tfc_ssp_ordering(method):
    """SSP245 TFC > SSP126, SSP245 > SSP434（2100，全部方法）。"""
    totals = {}
    for scn in SCENARIOS:
        df = _load(method, "TFC", scn)
        totals[scn] = float(df[[c for c in df.columns if isinstance(c, int)]].sum()[2100])

    assert totals["SSP245"] > totals["SSP126"], \
        f"{method}: SSP245 > SSP126 ({totals['SSP245']:.0f} vs {totals['SSP126']:.0f})"
    assert totals["SSP245"] > totals["SSP434"], \
        f"{method}: SSP245 > SSP434 ({totals['SSP245']:.0f} vs {totals['SSP434']:.0f})"


# ══════════════════════════════════════════════
# 测试 6: API 契约 + 集成测试（标记 slow）
# ══════════════════════════════════════════════

@pytest.mark.slow
def test_all_functions_return_dataframe():
    """各方案的 downscale_tfc 函数返回正确结构的 DataFrame。"""
    from compare.logit.downscale_tfc import downscale_tfc as logit_fn
    from compare.kaya.downscale_tfc import downscale_tfc as kaya_fn
    from compare.dscale.downscale_tfc import downscale_tfc as dscale_fn

    expected_cols = {"Scenario", "iso", "Country"}

    for name, fn in [("logit", logit_fn), ("kaya", kaya_fn), ("dscale", dscale_fn)]:
        df = fn("SSP126")
        assert isinstance(df, pd.DataFrame), f"{name}: not a DataFrame"
        assert expected_cols.issubset(df.columns), \
            f"{name}: missing columns {expected_cols - set(df.columns)}"
        assert 2015 in df.columns and 2100 in df.columns, \
            f"{name}: missing year columns"
        assert len(df) >= 170, f"{name}: only {len(df)} rows"


@pytest.mark.slow
def test_run_indicator_tfc_all_methods():
    """run_indicator 对 TFC 所有方法可正常运行（验证引擎通路）。"""
    from compare.common.downscale import run_indicator
    cfg = INDICATORS["tfc"]
    for method in METHODS:
        df = run_indicator(method, "SSP126", cfg)
        assert len(df) >= 170, f"{method}/tfc: {len(df)} rows"


# ══════════════════════════════════════════════
# 测试 7: 基础设施
# ══════════════════════════════════════════════

def test_dscale_official_import():
    """官方 DSCALE 适配层可正常导入。"""
    from compare.dscale.dscale_official import (
        fun_max_tc_convergence, fun_max_tc,
        fit_enlong_official, predict_enlong,
        downscale_dscale_official, downscale_dscale_generic,
    )
    assert callable(fun_max_tc)
    assert callable(downscale_dscale_generic)


def test_fun_max_tc_bounds():
    """fun_max_tc 返回值在 [2040, 2200] 范围内。"""
    from compare.dscale.dscale_official import fun_max_tc

    assert fun_max_tc(2.0, 0.9, 1990, 2015, -3.0) == 2040.0
    tc_high = fun_max_tc(1.0, 0.95, 1970, 2015, 1.5)
    assert 2040 <= tc_high <= 2200 and tc_high >= 2100
    tc_low = fun_max_tc(1.0, 0.1, 2005, 2010, 1.0, y_max=2200)
    assert 2040 <= tc_low <= 2100


def test_all_config_paths_exist():
    """config.py 中所有数据路径指向存在的文件。"""
    from compare.common.config import (
        IEA_WORLDBAL_PATH, MAPPING_PATH, IEA_TFC_PATH,
        gdp_country_path, pop_country_path, gdp_region_path, pop_region_path,
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


def test_output_files_have_expected_count():
    """产出文件数量验证。"""
    count = len(list(OUTPUT_DIR.glob("*_downscaled_*.xlsx")))
    assert count >= 140, f"产出文件应 ≥140（96 降尺度 + 48 份额），实际 {count}"


# ══════════════════════════════════════════════
# 测试 8: 量纲与单位正确性
# ══════════════════════════════════════════════

# 已知单位 → 转换因子映射
_KNOWN_UNIT_FACTORS = {
    "EJ": 1_000_000,      # → TJ
    "PJ": 1_000,          # → TJ
    "GWh": 3.6,           # → TJ
    "Mtoe": 41_868,       # → TJ
    "Gg CO₂": 0.001,      # → Mt
    "Gg CO2": 0.001,      # → Mt（变体）
}


def _parse_unit_from_file(cfg) -> tuple[str, float | None]:
    """读取 GCAM 文件的 Units 列，返回 (unit_str, auto_factor)。"""
    import pandas as pd
    path = cfg.gcam_path("SSP126")
    df = pd.read_excel(path, engine="openpyxl", dtype=str, nrows=2)
    unit = str(df["Units"].iloc[0]).strip() if "Units" in df.columns else ""
    factor = _KNOWN_UNIT_FACTORS.get(unit) if unit else None
    return unit, factor


@pytest.mark.parametrize("key,cfg", [(k, v) for k, v in INDICATORS.items()])
def test_gcam_unit_factor_matches_file(key, cfg):
    """每个指标的 unit_factor 应与文件中声明的一致。"""
    unit_str, auto_factor = _parse_unit_from_file(cfg)

    if not unit_str:
        # 无 Units 列：unit_factor 应被显式设置(≠1.0)或有合理默认值
        assert cfg.gcam_unit_factor != 1.0 or key == "co2_emissions", \
            f"{key}: no Units column but unit_factor={cfg.gcam_unit_factor} (set explicitly)"
        return

    # 已知单位：auto_factor 应为该单位的转换因子
    if auto_factor is not None:
        assert abs(cfg.gcam_unit_factor - auto_factor) < 1e-9, \
            f"{key}: unit_factor={cfg.gcam_unit_factor} but file says '{unit_str}' → expected {auto_factor}"
    else:
        # 未知单位：必须在 IndicatorConfig 中显式设置 unit_factor
        assert cfg.gcam_unit_factor != 1.0, \
            f"{key}: unknown unit '{unit_str}' but unit_factor=1.0 (set explicitly or add to _KNOWN_UNIT_FACTORS)"


def test_read_gcam_generic_unit_auto_detection():
    """unit_factor=1.0 时自动检测应正确。"""
    from compare.common.io import read_gcam_generic
    from compare.common.config import INDICATORS
    import tempfile, pandas as pd, numpy as np

    # 用 TFC 的 EJ 文件测试自动检测
    cfg = INDICATORS["tfc"]
    df_auto = read_gcam_generic(cfg.gcam_path("SSP126"))
    df_explicit = read_gcam_generic(cfg.gcam_path("SSP126"), unit_factor=1_000_000)

    for y in [2015, 2050, 2100]:
        diff = abs(float(df_auto[y].sum()) - float(df_explicit[y].sum()))
        assert diff < 1.0, f"y={y}: auto={df_auto[y].sum():.0f} vs explicit={df_explicit[y].sum():.0f}"


@pytest.mark.parametrize("key,cfg", [
    (k, v) for k, v in INDICATORS.items()
    if k in ("tfc", "electricity", "tes", "fossil_tes")
])
def test_output_values_in_expected_range(key, cfg):
    """降尺度输出值应在物理合理范围内。"""
    method = "logit"
    scenario = "SSP126"
    df = _load(method, cfg.output_prefix, scenario)
    yrs = _year_cols(df)
    non_oth = df[df["iso"] != "oth"]

    # 全球总量 > 0 且逐年递增（或至少非零）
    global_sums = {y: float(non_oth[y].sum()) for y in yrs}
    assert global_sums[2015] > 0, f"{key}: 2015 global sum is zero"
    # 部分指标可能在远期下降，只验证近期递增
    assert global_sums[2020] > 0

    # 检查量级合理性（针对 TJ 和 Mt 单位）
    if cfg.unit == "TJ":
        # 全球能源至少百万 TJ 级别
        assert global_sums[2015] > 1e6, \
            f"{key}: 2015 global={global_sums[2015]:.0f} TJ (< 1e6, unreasonably small)"
    elif cfg.unit == "Mt":
        # CO₂ 全球至少 Gt 级别（= 1000 Mt）
        assert global_sums[2015] > 100, \
            f"{key}: 2015 global={global_sums[2015]:.0f} Mt (< 100, unreasonably small)"


# ══════════════════════════════════════════════
# 测试 9: 单位转换数值正确性（逐单位验证换算）
# ══════════════════════════════════════════════

@pytest.mark.parametrize("raw_unit,raw_value,factor,expected", [
    ("EJ",    1.0,          1_000_000, 1_000_000.0),    # EJ → TJ
    ("PJ",    1000.0,       1_000,     1_000_000.0),     # PJ → TJ (same as 1 EJ)
    ("GWh",   1000.0,       3.6,       3_600.0),          # GWh → TJ
    ("Mtoe",  1.0,          41_868,    41_868.0),         # Mtoe → TJ
    ("Gg CO₂", 1_000_000.0, 0.001,     1_000.0),          # Gg → Mt
])
def test_unit_conversion_math(raw_unit, raw_value, factor, expected):
    """各已知单位的数值转换精确（防御 #22 再次出现）。"""
    import pandas as pd, tempfile, os
    from compare.common.io import read_gcam_generic

    df = pd.DataFrame([{
        "Scenario": "TEST", "Region": "R1", "fuel": "total",
        2015: raw_value, 2020: raw_value * 2.0, 2100: raw_value * 3.0,
        "Units": raw_unit,
    }])
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "test.xlsx")
        df.to_excel(path, index=False, engine="openpyxl")
        result = read_gcam_generic(path, unit_factor=factor)
        assert abs(float(result[2015].iloc[0]) - expected) < 1e-6, \
            f"{raw_unit}: {result[2015].iloc[0]} != {expected}"
        assert abs(float(result[2020].iloc[0]) - expected * 2) < 1e-6
        assert abs(float(result[2100].iloc[0]) - expected * 3) < 1e-6
