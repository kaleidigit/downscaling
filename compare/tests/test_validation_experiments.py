"""验证实验：提供数值证据证明各修复有效。

三个实验：
1. 份额有界性回归测试 — 证明 Kaya/DSCALE 份额 ∈ [0,1]
2. 单国区域方法一致性 — 证明三方法在单国区域产生一致结果
3. ENLONG alpha 调和影响 — 证明调和使回归线通过基年数据点
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
_DSCALE_REPO = Path(__file__).resolve().parents[2] / "DSCALE"
sys.path.insert(0, str(_DSCALE_REPO))

from compare.common.config import SCENARIOS, INDICATORS, DERIVED_SHARES, YEARS, OUTPUT_DIR
from compare.common.downscale import (
    compute_logit_share, compute_kaya_share, compute_dscale_share,
    load_gcam, _regional_conserve, _finalize_df,
)
from compare.common.mapping import load_mapping, build_region_members, EXCLUDED_ISO


# ═══════════════════════════════════════════════════════════
# 实验 1: 份额有界性回归测试
# ═══════════════════════════════════════════════════════════

class TestShareBoundedness:
    """证明：所有方法在所有份额指标中，输出严格 ∈ [0,1]。"""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    @pytest.mark.parametrize("method", ["logit", "kaya", "dscale"])
    @pytest.mark.parametrize("share_key", ["fossil_share", "renewable_share",
                                             "electrification_rate", "green_elec_share"])
    def test_share_bounded(self, scenario, method, share_key):
        """每个份额指标的 18 个年份值全部 ∈ [0,1]。"""
        spec = DERIVED_SHARES[share_key]
        cfg_num = INDICATORS[spec["numerator"]]
        cfg_den = INDICATORS[spec["denominator"]]
        if cfg_num is None or cfg_den is None:
            pytest.skip(f"missing config for {share_key}")

        # Load pre-computed numerator/denominator
        from compare.run_all import _load_output
        df_num = _load_output(method, spec["numerator"], scenario)
        df_den = _load_output(method, spec["denominator"], scenario)
        gcam_num = load_gcam(cfg_num, scenario)
        gcam_den = load_gcam(cfg_den, scenario)

        if method == "logit":
            df = compute_logit_share(df_num, df_den, gcam_num, gcam_den, scenario)
        elif method == "kaya":
            df = compute_kaya_share(df_num, df_den, gcam_num, gcam_den, scenario)
        else:
            df = compute_dscale_share(df_num, df_den, gcam_num, gcam_den, scenario)

        yrs = [y for y in YEARS]
        non_oth = df[df["iso"] != "oth"]
        violations = (non_oth[yrs] < -1e-9).any(axis=1).sum() + \
                     (non_oth[yrs] > 1.0 + 1e-9).any(axis=1).sum()
        assert violations == 0, \
            f"{method}/{share_key}/{scenario}: {violations} countries outside [0,1]"

# ═══════════════════════════════════════════════════════════
# 实验 2: 单国区域方法一致性
# ═══════════════════════════════════════════════════════════

class TestSingleCountryConsistency:
    """证明：单国区域下三方法结果一致。"""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_all_single_country_regions_consistent(self, scenario):
        """所有 14+ 个单国区域，18 个年份，三方法结果一致（rel < 1e-10）。"""
        mapping = load_mapping()
        members = build_region_members(mapping)
        single_region_isos = []
        for r, mlist in members.items():
            valid = [m for m in mlist if m["iso"] not in EXCLUDED_ISO]
            if len(valid) == 1:
                single_region_isos.append(valid[0]["iso"])

        assert len(single_region_isos) >= 14, f"expected >=14 single-country regions, got {len(single_region_isos)}"

        yrs = [y for y in YEARS]
        # Test TFC (primary indicator)
        for iso in single_region_isos:
            vals = {}
            for method in ["logit", "kaya", "dscale"]:
                path = OUTPUT_DIR / f"{method}_TFC_downscaled_{scenario}.xlsx"
                if not path.exists():
                    continue
                df = pd.read_excel(path)
                row = df[df["iso"] == iso]
                if row.empty:
                    continue
                vals[method] = {y: float(row[y].iloc[0]) for y in yrs}

            if len(vals) < 2:
                continue

            methods_list = list(vals.keys())
            ref = vals[methods_list[0]]
            for m in methods_list[1:]:
                for y in yrs:
                    diff = abs(vals[m][y] - ref[y])
                    rel = diff / max(abs(ref[y]), 1e-10) if abs(ref[y]) > 1e-10 else diff
                    msg = (f"{scenario}/{iso} {y}: {methods_list[0]}={ref[y]:.6f} vs "
                           f"{m}={vals[m][y]:.6f}, diff={diff:.6f} rel={rel:.2e}")
                    assert rel < 1e-10 or diff < 1e-6, msg


# ═══════════════════════════════════════════════════════════
# 实验 3: ENLONG alpha 调和影响
# ═══════════════════════════════════════════════════════════

class TestEnlongAlphaHarmonization:
    """证明：alpha 调和使 ENLONG 回归精确通过基年数据点，且不改变 R²。"""

    def test_harmonization_passes_through_base_year(self):
        """调和后，ENLONG 对基年的预测值应精确等于基年观测值。"""
        from compare.dscale.dscale_official import fit_enlong_official
        from compare.common.io import read_gcam_tfc
        from compare.common.config import gdp_region_path, pop_region_path
        from compare.common.io import read_gdp_region, read_pop_region

        scenario = "SSP126"
        path = INDICATORS["tfc"].gcam_path(scenario)
        gcam = read_gcam_tfc(path)
        gdp_r = read_gdp_region(gdp_region_path(scenario))
        pop_r = read_pop_region(pop_region_path(scenario))

        # Test on 3 representative regions
        tested = 0
        for _, g_row in gcam.iterrows():
            region = g_row["Region"]
            r_gdp = gdp_r[gdp_r["Region"] == region]
            r_pop = pop_r[pop_r["Region"] == region]
            if r_gdp.empty or r_pop.empty:
                continue

            gcam_tfc_s = pd.Series(
                {y: float(g_row.get(y, 0) or 0)
                 for y in [1990, 2005, 2010] + list(range(2015, 2101, 5))}, dtype=float
            )
            gcam_gdp_s = pd.Series(
                {y: float(r_gdp[y].iloc[0]) if y in r_gdp.columns else 0.0
                 for y in [1990, 2005, 2010] + list(range(2015, 2101, 5))}, dtype=float
            )
            gcam_pop_s = pd.Series(
                {y: float(r_pop[y].iloc[0]) if y in r_pop.columns else 0.0
                 for y in [1990, 2005, 2010] + list(range(2015, 2101, 5))}, dtype=float
            )

            ff = fit_enlong_official(gcam_tfc_s, gcam_gdp_s, gcam_pop_s, base_year=2015)

            # Skip if no valid fit
            if ff.r_squared is None or ff.r_squared <= 0:
                continue

            # Verify: predicted EI at base year matches observed EI
            ei_2015_obs = float(gcam_tfc_s[2015]) / max(float(gcam_gdp_s[2015]), 1e-10)
            gdp_pcap_2015 = float(gcam_gdp_s[2015]) / max(float(gcam_pop_s[2015]), 1e-10)
            ei_2015_pred = ff.predict_y(pd.Series([gdp_pcap_2015])).iloc[0]

            rel_err = abs(ei_2015_pred - ei_2015_obs) / max(ei_2015_obs, 1e-10)
            assert rel_err < 1e-10, \
                f"{region}: predicted EI={ei_2015_pred:.6f} vs observed={ei_2015_obs:.6f}, rel_err={rel_err:.2e}"

            tested += 1
            if tested >= 3:  # Test 3 regions
                break

        assert tested >= 1, "No regions tested for alpha harmonization"

    def test_r_squared_unchanged_after_harmonization(self):
        """Alpha 调和不应改变 R²（R² 由残差决定，alpha 是整体平移）。"""
        from compare.dscale.dscale_official import fit_enlong_official
        from downscaler.fit_funcs import LogLogFunc

        # Synthetic data: perfect power law with a known offset
        years = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y - 2000) for y in years}, dtype=float)
        pop = pd.Series({y: 1.0 for y in years}, dtype=float)
        tfc = pd.Series({y: 5.0 * float((y - 2000) ** 3) for y in years}, dtype=float)

        # Fit WITHOUT harmonization
        gdp_pcap = gdp / pop
        ei = tfc / gdp
        x = gdp_pcap.values.astype(float)
        y = ei.values.astype(float)
        ff_raw = LogLogFunc()
        ff_raw.fit(pd.Series(x), pd.Series(y))
        r2_raw = ff_raw.r_squared

        # Fit WITH harmonization (our implementation)
        ff_harm = fit_enlong_official(tfc, gdp, pop, base_year=2015)

        # R² 理论上不变（仅 alpha 平移），允许 < 1e-6 浮点误差
        msg = f"R² changed: {r2_raw:.10f} vs {ff_harm.r_squared:.10f}"
        assert abs(ff_harm.r_squared - r2_raw) < 1e-6, msg


# ═══════════════════════════════════════════════════════════
# 补充边缘测试（从 test_cross_validate.py 缺口补全）
# ═══════════════════════════════════════════════════════════

class TestGammaCGuards:
    """gamma_c 的 inf/nan 防护。"""

    def test_inf_gdp_pcap_returns_one(self):
        from compare.common.downscale import gamma_c
        assert gamma_c(float("inf"), 100.0) == 1.0

    def test_nan_gdp_pcap_returns_one(self):
        from compare.common.downscale import gamma_c
        assert gamma_c(float("nan"), 100.0) == 1.0

    def test_inf_world_pcap_returns_one(self):
        from compare.common.downscale import gamma_c
        assert gamma_c(100.0, float("inf")) == 1.0


class TestFinalizeDfResidual:
    """_finalize_df 残差行测试。"""

    def test_positive_residual_adds_oth_row(self):
        """分配值 < GCAM 值 → 应添加正残差 oth 行。"""
        from compare.common.downscale import _finalize_df, YEARS
        row = {"Scenario": "SSP126", "iso": "chn", "Country": "China", "Region": "China"}
        for y in YEARS:
            row[y] = 50.0  # allocate 50, GCAM has 100
        gcam = pd.DataFrame([{"Scenario": "SSP126", "Region": "China",
                              **{y: 100.0 for y in YEARS}}])
        df = _finalize_df([row], gcam)
        oth = df[df["iso"] == "oth"]
        assert not oth.empty, "Should have oth residual row"
        assert abs(float(oth[2100].iloc[0]) - 50.0) < 1e-6

    def test_negative_residual_adds_oth_row(self):
        """分配值 > GCAM 值 → 应添加负残差 oth 行（过度分配检测）。"""
        from compare.common.downscale import _finalize_df, YEARS
        row = {"Scenario": "SSP126", "iso": "chn", "Country": "China", "Region": "China"}
        for y in YEARS:
            row[y] = 150.0  # over-allocate
        gcam = pd.DataFrame([{"Scenario": "SSP126", "Region": "China",
                              **{y: 100.0 for y in YEARS}}])
        df = _finalize_df([row], gcam)
        oth = df[df["iso"] == "oth"]
        assert not oth.empty
        assert abs(float(oth[2100].iloc[0]) + 50.0) < 1e-6  # residual = -50

    def test_tiny_residual_no_oth_row(self):
        """残差 < 1e-6 → 无 oth 行。"""
        from compare.common.downscale import _finalize_df, YEARS
        row = {"Scenario": "SSP126", "iso": "chn", "Country": "China", "Region": "China"}
        for y in YEARS:
            row[y] = 99.9999995
        gcam = pd.DataFrame([{"Scenario": "SSP126", "Region": "China",
                              **{y: 100.0 for y in YEARS}}])
        df = _finalize_df([row], gcam)
        assert "oth" not in df["iso"].values


class TestEnshortDegenerate:
    """ENSHORT 回归退化场景。"""

    def test_zero_variance_data_produces_no_nan(self):
        """全同数据（零方差）→ scipy linregress 可能返回 nan 或 R²=1.0。
        无论哪种情况，params 中不应包含 NaN 值（要么过滤掉，要么值有限）。"""
        from compare.dscale.dscale_official import fit_enshort_countries
        import numpy as np

        tfc = {"XXX": {y: 100.0 for y in range(1970, 2016)}}
        gdp = {"XXX": {y: 50.0 for y in range(1970, 2016)}}
        pop = {"XXX": {y: 1.0 for y in range(1970, 2016)}}

        params = fit_enshort_countries(tfc, gdp, pop)
        if "XXX" in params:
            for k in ["alpha", "beta", "r_squared"]:
                v = params["XXX"].get(k)
                if v is not None:
                    assert np.isfinite(v), f"Non-finite value in {k}: {v}"
