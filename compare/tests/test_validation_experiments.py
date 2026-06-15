"""验证实验：份额有界性、单国一致性、ENLONG alpha 调和、边缘场景。"""

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


# ═══════════════════════════════════════════════════════════
# 实验 1: 份额有界性（运行时计算，比 test_conservation 的 disk-load 更严格）
# ═══════════════════════════════════════════════════════════

class TestShareBoundedness:
    """所有方法 × 份额 × 情景 输出严格 ∈ [0,1]。"""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    @pytest.mark.parametrize("method", ["logit", "kaya", "dscale"])
    @pytest.mark.parametrize("share_key", ["fossil_share", "renewable_share",
                                             "electrification_rate", "green_elec_share"])
    def test_share_bounded(self, scenario, method, share_key):
        spec = DERIVED_SHARES[share_key]
        cfg_num = INDICATORS[spec["numerator"]]
        cfg_den = INDICATORS[spec["denominator"]]
        if cfg_num is None or cfg_den is None:
            pytest.skip(f"missing config for {share_key}")

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
# 实验 2: 单国区域方法一致性（全情景，比 test_conservation 更全面）
# ═══════════════════════════════════════════════════════════

class TestSingleCountryConsistency:
    """单国区域下三方法结果一致。"""

    @pytest.mark.parametrize("scenario", SCENARIOS)
    def test_all_single_country_regions_consistent(self, scenario, single_region_isos):
        assert len(single_region_isos) >= 14, \
            f"expected >=14 single-country regions, got {len(single_region_isos)}"

        yrs = [y for y in YEARS]
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
# 实验 3: ENLONG alpha 调和
# ═══════════════════════════════════════════════════════════

class TestEnlongAlphaHarmonization:
    """alpha 调和使 ENLONG 回归精确通过基年数据点。"""

    def test_harmonization_passes_through_base_year(self):
        from compare.dscale.dscale_official import fit_enlong_official
        from compare.common.io import read_gcam_tfc, read_gdp_region, read_pop_region
        from compare.common.config import gdp_region_path, pop_region_path

        scenario = "SSP126"
        path = INDICATORS["tfc"].gcam_path(scenario)
        gcam = read_gcam_tfc(path)
        gdp_r = read_gdp_region(gdp_region_path(scenario))
        pop_r = read_pop_region(pop_region_path(scenario))

        tested = 0
        for _, g_row in gcam.iterrows():
            region = g_row["Region"]
            r_gdp = gdp_r[gdp_r["Region"] == region]
            r_pop = pop_r[pop_r["Region"] == region]
            if r_gdp.empty or r_pop.empty:
                continue

            gcam_tfc_s = pd.Series(
                {y: float(g_row.get(y, 0) or 0)
                 for y in [1990, 2005, 2010] + list(range(2015, 2101, 5))}, dtype=float)
            gcam_gdp_s = pd.Series(
                {y: float(r_gdp[y].iloc[0]) if y in r_gdp.columns else 0.0
                 for y in [1990, 2005, 2010] + list(range(2015, 2101, 5))}, dtype=float)
            gcam_pop_s = pd.Series(
                {y: float(r_pop[y].iloc[0]) if y in r_pop.columns else 0.0
                 for y in [1990, 2005, 2010] + list(range(2015, 2101, 5))}, dtype=float)

            ff = fit_enlong_official(gcam_tfc_s, gcam_gdp_s, gcam_pop_s, base_year=2015)
            if ff.r_squared is None or ff.r_squared <= 0:
                continue

            ei_2015_obs = float(gcam_tfc_s[2015]) / max(float(gcam_gdp_s[2015]), 1e-10)
            gdp_pcap_2015 = float(gcam_gdp_s[2015]) / max(float(gcam_pop_s[2015]), 1e-10)
            ei_2015_pred = ff.predict_y(pd.Series([gdp_pcap_2015])).iloc[0]

            rel_err = abs(ei_2015_pred - ei_2015_obs) / max(ei_2015_obs, 1e-10)
            assert rel_err < 1e-10, \
                f"{region}: predicted={ei_2015_pred:.6f} vs observed={ei_2015_obs:.6f}"

            tested += 1
            if tested >= 3:
                break

        assert tested >= 1, "No regions tested for alpha harmonization"

    def test_r_squared_nearly_unchanged_after_harmonization(self):
        """Alpha 调和仅平移截距，对噪声有限数据 R² 变化应 <0.01。"""
        from compare.dscale.dscale_official import fit_enlong_official
        from downscaler.fit_funcs import LogLogFunc

        # Noisy data around a power law
        rng = np.random.RandomState(42)
        years = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y - 2000) for y in years}, dtype=float)
        pop = pd.Series({y: 1.0 + 0.01 * rng.randn() for y in years}, dtype=float)
        tfc_base = pd.Series(
            {y: 5.0 * float((y - 2000) ** 3) for y in years}, dtype=float)
        tfc = pd.Series(
            {y: tfc_base[y] * (1.0 + 0.02 * rng.randn()) for y in years}, dtype=float)

        # Fit WITHOUT harmonization
        gdp_pcap = gdp / pop
        ei = tfc / gdp
        mask = (gdp_pcap > 0) & (ei > 0)
        x = gdp_pcap[mask].values.astype(float)
        y = ei[mask].values.astype(float)
        ff_raw = LogLogFunc()
        ff_raw.fit(pd.Series(x), pd.Series(y))
        r2_raw = ff_raw.r_squared

        # Fit WITH harmonization
        ff_harm = fit_enlong_official(tfc, gdp, pop, base_year=2015)

        # R² should change only slightly (<0.01 for noisy data)
        assert abs(ff_harm.r_squared - r2_raw) < 0.01, \
            f"R² changed too much: {r2_raw:.6f} vs {ff_harm.r_squared:.6f}"


# ═══════════════════════════════════════════════════════════
# 补充边缘测试
# ═══════════════════════════════════════════════════════════

class TestConvergenceGammaGuards:
    """convergence_gamma edge case guards."""

    def test_large_convergence_year(self):
        from compare.common.downscale import convergence_gamma
        g = convergence_gamma(3000)
        assert g < 0 and abs(g) < 0.1

    def test_residual_ratio_property(self):
        from compare.common.downscale import convergence_gamma, RESIDUAL_RATIO
        g = convergence_gamma(2200)
        assert abs(g * (2200 - 2015) - np.log(RESIDUAL_RATIO)) < 1e-12


class TestFinalizeDfResidual:
    """_finalize_df 残差行测试。"""

    def test_positive_residual_adds_oth_row(self):
        from compare.common.downscale import _finalize_df, YEARS
        row = {"Scenario": "SSP126", "iso": "chn", "Country": "China", "Region": "China"}
        for y in YEARS:
            row[y] = 50.0
        gcam = pd.DataFrame([{"Scenario": "SSP126", "Region": "China",
                              **{y: 100.0 for y in YEARS}}])
        df = _finalize_df([row], gcam)
        oth = df[df["iso"] == "oth"]
        assert not oth.empty
        assert abs(float(oth[2100].iloc[0]) - 50.0) < 1e-6

    def test_negative_residual_adds_oth_row(self):
        from compare.common.downscale import _finalize_df, YEARS
        row = {"Scenario": "SSP126", "iso": "chn", "Country": "China", "Region": "China"}
        for y in YEARS:
            row[y] = 150.0
        gcam = pd.DataFrame([{"Scenario": "SSP126", "Region": "China",
                              **{y: 100.0 for y in YEARS}}])
        df = _finalize_df([row], gcam)
        oth = df[df["iso"] == "oth"]
        assert not oth.empty
        assert abs(float(oth[2100].iloc[0]) + 50.0) < 1e-6

    def test_tiny_residual_no_oth_row(self):
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
        from compare.dscale.dscale_official import fit_enshort_countries

        tfc = {"XXX": {y: 100.0 for y in range(1970, 2016)}}
        gdp = {"XXX": {y: 50.0 for y in range(1970, 2016)}}
        pop = {"XXX": {y: 1.0 for y in range(1970, 2016)}}

        params = fit_enshort_countries(tfc, gdp, pop)
        if "XXX" in params:
            for k in ["alpha", "beta", "r_squared"]:
                v = params["XXX"].get(k)
                if v is not None:
                    assert np.isfinite(v), f"Non-finite value in {k}: {v}"


# ═══════════════════════════════════════════════════════════
# ENSHORT 回归正确性（防止双 log 回归）
# ═══════════════════════════════════════════════════════════

class TestEnshortCorrectness:
    """ENSHORT 回归应产生正确的 log-log 系数（非 double-log）。"""

    def test_recovered_beta_matches_known_relationship(self):
        """已知 log(EI) = ln(3) + 2×log(GDP_pcap)，验证 β≈2, α≈ln(3)。"""
        from compare.dscale.dscale_official import fit_enshort_countries
        import numpy as np

        rng = np.random.RandomState(123)
        iso = "TST"
        tfc_hist: dict[str, dict[int, float]] = {iso: {}}
        gdp_hist: dict[str, dict[int, float]] = {iso: {}}
        pop_hist: dict[str, dict[int, float]] = {iso: {}}

        for y in range(1970, 2016):
            gdp_pcap = 2.0 + 0.1 * (y - 1970) + 0.05 * rng.randn()
            pop_hist[iso][y] = 1.0
            gdp_hist[iso][y] = gdp_pcap
            ei = 3.0 * (gdp_pcap ** 2.0) * (1.0 + 0.03 * rng.randn())
            tfc_hist[iso][y] = ei * gdp_pcap

        params = fit_enshort_countries(tfc_hist, gdp_hist, pop_hist)

        assert iso in params, "ENSHORT 应成功拟合测试国"
        beta = params[iso]["beta"]
        alpha = params[iso]["alpha"]
        r2 = params[iso]["r_squared"]

        # β 应在 2.0 附近（允许噪声导致的误差）
        assert 1.5 < beta < 2.5, f"beta={beta:.3f}, 预期 ≈2.0"
        # α 应在 ln(3)≈1.099 附近
        assert 0.5 < alpha < 1.8, f"alpha={alpha:.3f}, 预期 ≈1.1"
        assert r2 > 0.8, f"R²={r2:.3f}, 预期 >0.8"

    def test_no_runtime_warning_with_sub_one_values(self):
        """gdp_pcap < 1 的 log 为负值，不应触发 RuntimeWarning（非 double-log）。"""
        import warnings
        from compare.dscale.dscale_official import fit_enshort_countries

        iso = "TST"
        tfc: dict[str, dict[int, float]] = {iso: {}}
        gdp: dict[str, dict[int, float]] = {iso: {}}
        pop: dict[str, dict[int, float]] = {iso: {}}

        for y in range(1970, 2016):
            gdp_pcap = 0.5 + 0.01 * (y - 1970)  # < 1, log is negative
            pop[iso][y] = 1.0
            gdp[iso][y] = gdp_pcap
            ei = 2.0 * (gdp_pcap ** 1.5)
            tfc[iso][y] = ei * gdp_pcap

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            params = fit_enshort_countries(tfc, gdp, pop)
            # 不应产生 RuntimeWarning（旧 double-log 代码会）
            runtime_warnings = [x for x in w
                               if issubclass(x.category, RuntimeWarning)
                               and "log" in str(x.message).lower()]
            assert len(runtime_warnings) == 0, \
                f"产生了 {len(runtime_warnings)} 个 log RuntimeWarning"

        assert iso in params
        assert np.isfinite(params[iso]["beta"])


# ═══════════════════════════════════════════════════════════
# 迭代封顶缩放回归测试
# ═══════════════════════════════════════════════════════════

class TestIterativeCappedScaling:
    """_iterative_capped_scaling 应保证守恒完美且无振荡。"""

    def test_exact_conservation_with_capping(self):
        """封顶场景：部分国家 R>E_c，封顶后守恒仍精确。"""
        from compare.common.downscale import _iterative_capped_scaling

        region_isos = ["a", "b", "c"]
        S_proj = {"a": {2050: 0.1}, "b": {2050: 0.3}, "c": {2050: 0.6}}
        E_c = {"a": 100.0, "b": 200.0, "c": 1000.0}  # b capped (0.3*200=60, but may grow)
        target = 300.0

        _iterative_capped_scaling(region_isos, S_proj, E_c, target, 2050)

        # 验证守恒
        allocated = sum(E_c[iso] * S_proj[iso][2050] for iso in region_isos)
        assert abs(allocated - target) < 1e-6, \
            f"守恒偏差: allocated={allocated:.6f} vs target={target}"

        # 验证份额有界
        for iso in region_isos:
            assert 0.0 <= S_proj[iso][2050] <= 1.0, \
                f"{iso}: share={S_proj[iso][2050]} outside [0,1]"

    def test_all_countries_at_boundary(self):
        """全部国家 R>E_c 的边缘场景。"""
        from compare.common.downscale import _iterative_capped_scaling

        region_isos = ["a", "b"]
        S_proj = {"a": {2100: 0.9}, "b": {2100: 0.9}}
        E_c = {"a": 10.0, "b": 10.0}
        target = 25.0  # > sum(E_c) = 20, impossible to match

        _iterative_capped_scaling(region_isos, S_proj, E_c, target, 2100)

        for iso in region_isos:
            assert 0.0 <= S_proj[iso][2100] <= 1.0

    def test_single_country_trivial(self):
        from compare.common.downscale import _iterative_capped_scaling

        region_isos = ["x"]
        S_proj = {"x": {2020: 0.5}}
        E_c = {"x": 100.0}
        _iterative_capped_scaling(region_isos, S_proj, E_c, 50.0, 2020)
        assert abs(S_proj["x"][2020] - 0.5) < 1e-6
