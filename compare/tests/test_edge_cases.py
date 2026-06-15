"""边缘情况单元测试。

覆盖 convergence_gamma、van_vuuren_ei、convergence_weight、_regional_conserve 等关键边缘情况。
"""

import numpy as np
import pandas as pd
import pytest

from compare.common.downscale import (
    convergence_gamma,
    van_vuuren_ei,
    convergence_weight,
    _regional_conserve,
    _region_isos,
    _finalize_df,
    CONVERGENCE_YEAR_DEFAULT,
    RESIDUAL_RATIO,
)
from compare.common.mapping import (
    normalize_name,
    load_mapping,
    build_region_members,
    EXCLUDED_ISO,
)
from compare.common.config import YEARS


# ═══════════════════════════════════════════════════════════
# convergence_gamma
# ═══════════════════════════════════════════════════════════

class TestConvergenceGamma:
    def test_ssp126_gamma_is_negative(self):
        """SSP126 (y_c=2150): gamma = ln(0.01)/(2150-2015) < 0."""
        g = convergence_gamma(2150)
        assert g < 0

    def test_ssp245_abs_less_than_ssp126(self):
        """SSP245 (y_c=2200) converges slower → |gamma| smaller."""
        g126 = convergence_gamma(2150)
        g245 = convergence_gamma(2200)
        assert abs(g126) > abs(g245)

    def test_gamma_formula_exact(self):
        """gamma = ln(0.01) / (y_c - 2015)."""
        g = convergence_gamma(2200)
        expected = np.log(0.01) / (2200 - 2015)
        assert abs(g - expected) < 1e-12

    def test_degenerate_convergence_year(self):
        """y_c = 2015: degenerate, gamma = -1.0."""
        assert convergence_gamma(2015) == -1.0

    def test_y_c_before_base_year(self):
        """y_c < 2015: degenerate, gamma = -1.0."""
        assert convergence_gamma(2000) == -1.0


# ═══════════════════════════════════════════════════════════
# van_vuuren_ei
# ═══════════════════════════════════════════════════════════

class TestVanVuurenEI:
    def test_base_year_returns_base_ei(self):
        """y=2015 returns I_c_2015."""
        I = van_vuuren_ei(2015, 5.0, 2.0, convergence_gamma(2200))
        assert abs(I - 5.0) < 1e-12

    def test_before_base_year_returns_base_ei(self):
        """y<2015 returns I_c_2015."""
        I = van_vuuren_ei(2010, 5.0, 2.0, convergence_gamma(2200))
        assert abs(I - 5.0) < 1e-12

    def test_converging_country_ei_decreases(self):
        """Country with I_c > I_R_target: EI decreases toward target."""
        I_c = 10.0
        I_R_target = 2.0
        gamma = convergence_gamma(2200)
        I_2020 = van_vuuren_ei(2020, I_c, I_R_target, gamma)
        I_2050 = van_vuuren_ei(2050, I_c, I_R_target, gamma)
        I_2100 = van_vuuren_ei(2100, I_c, I_R_target, gamma)
        assert I_2020 > I_2050 > I_2100
        assert I_2100 > I_R_target  # not yet fully converged by 2100

    def test_already_converged_country(self):
        """I_c_2015 = I_R_target: a_c=0, EI = b_c = I_c (constant)."""
        I_c = 2.0
        I_R_target = 2.0
        gamma = convergence_gamma(2200)
        for y in [2020, 2050, 2100]:
            I = van_vuuren_ei(y, I_c, I_R_target, gamma)
            assert abs(I - I_c) < 1e-12

    def test_negative_b_c_floor_at_zero(self):
        """When I_c < I_R_target * d, b_c < 0; EI must not go negative."""
        I_c = 0.001
        I_R_target = 5.0
        gamma = convergence_gamma(2200)
        for y in YEARS:
            I = van_vuuren_ei(y, I_c, I_R_target, gamma)
            assert I >= 0.0, f"EI negative at y={y}: {I}"

    def test_monotonic_convergence(self):
        """For I_c > I_R_target: EI monotonically decreasing."""
        I_c = 8.0
        I_R_target = 2.0
        gamma = convergence_gamma(2200)
        prev = I_c
        for y in YEARS:
            I = van_vuuren_ei(y, I_c, I_R_target, gamma)
            assert I <= prev + 1e-12, f"Non-monotonic at y={y}"
            prev = I

    def test_exact_boundary_conditions(self):
        """a_c + b_c = I_c_2015, a_c*d + b_c = I_R_target."""
        I_c = 6.0
        I_R_target = 2.0
        d = RESIDUAL_RATIO
        a_c = (I_c - I_R_target) / (1 - d)
        b_c = I_c - a_c
        assert abs(a_c + b_c - I_c) < 1e-12
        assert abs(a_c * d + b_c - I_R_target) < 1e-12


# ═══════════════════════════════════════════════════════════
# convergence_weight
# ═══════════════════════════════════════════════════════════

class TestConvergenceWeight:
    def test_base_year_returns_zero(self):
        """y=2015 → w=0."""
        assert convergence_weight(2015, convergence_gamma(2200)) == 0.0

    def test_before_base_year_returns_zero(self):
        """y<2015 → w=0."""
        assert convergence_weight(2010, convergence_gamma(2200)) == 0.0

    def test_increases_over_time(self):
        """w increases with time."""
        gamma = convergence_gamma(2200)
        vals = [convergence_weight(y, gamma) for y in [2020, 2050, 2100]]
        assert vals[0] < vals[1] < vals[2]

    def test_approaches_1_minus_d(self):
        """w(y_c) ≈ 1 - d = 0.99."""
        gamma = convergence_gamma(2200)
        w = convergence_weight(2200, gamma)
        assert abs(w - 0.99) < 1e-6

    def test_never_exceeds_one(self):
        """w < 1 for all finite years."""
        gamma = convergence_gamma(2200)
        for y in YEARS:
            assert convergence_weight(y, gamma) < 1.0


# ═══════════════════════════════════════════════════════════
# CONVERGENCE_YEAR_DEFAULT
# ═══════════════════════════════════════════════════════════

class TestConvergenceYearDefault:
    def test_all_scenarios_have_convergence_year(self):
        for sc in ["SSP126", "SSP245", "SSP434", "SSP460"]:
            assert sc in CONVERGENCE_YEAR_DEFAULT

    def test_convergence_years_increasing(self):
        """More sustainable scenarios converge earlier."""
        assert CONVERGENCE_YEAR_DEFAULT["SSP126"] <= CONVERGENCE_YEAR_DEFAULT["SSP245"]
        assert CONVERGENCE_YEAR_DEFAULT["SSP245"] <= CONVERGENCE_YEAR_DEFAULT["SSP434"]
        assert CONVERGENCE_YEAR_DEFAULT["SSP434"] <= CONVERGENCE_YEAR_DEFAULT["SSP460"]

    def test_convergence_years_beyond_2100(self):
        """All convergence years beyond projection period."""
        for y_c in CONVERGENCE_YEAR_DEFAULT.values():
            assert y_c > 2100

    def test_matches_gutschow_2021(self):
        """Convergence years match Gütschow 2021 ESSD."""
        assert CONVERGENCE_YEAR_DEFAULT["SSP126"] == 2150
        assert CONVERGENCE_YEAR_DEFAULT["SSP245"] == 2200
        assert CONVERGENCE_YEAR_DEFAULT["SSP434"] == 2300
        assert CONVERGENCE_YEAR_DEFAULT["SSP460"] == 2300


# ═══════════════════════════════════════════════════════════
# _regional_conserve
# ═══════════════════════════════════════════════════════════

class TestRegionalConserve:
    def _make_proj(self, iso_vals):
        """构造包含完整 YEARS 的 projections dict。"""
        proj = {}
        for iso, year_vals in iso_vals.items():
            proj[iso] = {y: year_vals.get(y, 0.0) for y in YEARS}
        return proj

    def _make_grow(self, year_vals):
        """构造包含完整 YEARS 的 GCAM 行 Series。"""
        d = {"Region": "X"}
        d.update({y: year_vals.get(y, 0.0) for y in YEARS})
        return pd.Series(d)

    def test_normal_conservation(self):
        """正常情况：按比例缩放使总和等于目标值。"""
        proj = self._make_proj({"a": {2020: 30.0, 2025: 40.0},
                                 "b": {2020: 70.0, 2025: 60.0}})
        g_row = self._make_grow({2020: 200.0, 2025: 150.0})
        _regional_conserve(proj, ["a", "b"], g_row, 2)
        assert abs(proj["a"][2020] - 60.0) < 1e-12
        assert abs(proj["b"][2020] - 140.0) < 1e-12
        assert abs(proj["a"][2025] - 60.0) < 1e-12
        assert abs(proj["b"][2025] - 90.0) < 1e-12

    def test_zero_total_proj_equal_split(self):
        """total_proj=0 → 均分。"""
        proj = self._make_proj({"a": {}, "b": {}})
        g_row = self._make_grow({2020: 100.0})
        _regional_conserve(proj, ["a", "b"], g_row, 2)
        assert abs(proj["a"][2020] - 50.0) < 1e-12
        assert abs(proj["b"][2020] - 50.0) < 1e-12

    def test_zero_total_and_zero_gcam(self):
        """total_proj=0 AND gcam_val=0 → 全部零。"""
        proj = self._make_proj({"a": {}})
        g_row = self._make_grow({2020: 0.0})
        _regional_conserve(proj, ["a"], g_row, 1)
        assert abs(proj["a"][2020] - 0.0) < 1e-12

    def test_single_country_preserves_gcam_value(self):
        """单国区域 → 应该等于 GCAM 值。"""
        proj = self._make_proj({"a": {2020: 42.0}})
        g_row = self._make_grow({2020: 100.0})
        _regional_conserve(proj, ["a"], g_row, 1)
        assert abs(proj["a"][2020] - 100.0) < 1e-12

    def test_empty_region_zero_countries(self):
        """n_r=0 → 不 crash。"""
        proj = {}
        g_row = pd.Series({"Region": "X", 2020: 100.0})
        _regional_conserve(proj, [], g_row, 0)
        assert len(proj) == 0


# ═══════════════════════════════════════════════════════════
# _finalize_df
# ═══════════════════════════════════════════════════════════

class TestFinalizeDf:
    def test_empty_rows_returns_empty_df(self):
        df = _finalize_df([], pd.DataFrame())
        assert df.empty

    def test_exact_match_no_residual(self):
        """GCAM 总量恰好等于国和 → 无残差行。"""
        row = {"Scenario": "SSP126", "iso": "chn", "Country": "China", "Region": "China"}
        for y in YEARS:
            row[y] = 100.0
        gcam = pd.DataFrame([{"Scenario": "SSP126", "Region": "China", **{y: 100.0 for y in YEARS}}])
        df = _finalize_df([row], gcam)
        assert "oth" not in df["iso"].values

    def test_residual_below_tolerance_no_oth_row(self):
        """残差 < 1e-6 → 不添加 oth 行。"""
        row = {"Scenario": "SSP126", "iso": "chn", "Country": "China", "Region": "China"}
        for y in YEARS:
            row[y] = 99.9999995  # 差 5e-7
        gcam = pd.DataFrame([{"Scenario": "SSP126", "Region": "China", **{y: 100.0 for y in YEARS}}])
        df = _finalize_df([row], gcam)
        assert "oth" not in df["iso"].values


# ═══════════════════════════════════════════════════════════
# mapping
# ═══════════════════════════════════════════════════════════

class TestMapping:
    def test_excluded_iso_count(self):
        assert len(EXCLUDED_ISO) == 5

    def test_taiwan_merged_to_china(self):
        mapping = load_mapping()
        assert "twn" not in mapping["iso"].values
        assert "chn" in mapping["iso"].values

    def test_all_iso_lowercase(self):
        mapping = load_mapping()
        for iso in mapping["iso"]:
            assert iso == iso.lower()

    def test_normalize_name_handles_none(self):
        assert normalize_name(None) == ""

    def test_normalize_name_removes_accents(self):
        result = normalize_name("Côte d'Ivoire")
        assert "cote" in result
        assert "divoire" in result

    def test_normalize_name_lowercases(self):
        assert normalize_name("CHINA") == "china"

    def test_region_members_no_excluded(self):
        mapping = load_mapping()
        members = build_region_members(mapping)
        for mlist in members.values():
            for m in mlist:
                assert m["iso"] not in EXCLUDED_ISO

    def test_every_region_has_countries(self):
        mapping = load_mapping()
        members = build_region_members(mapping)
        for region, mlist in members.items():
            isos = _region_isos(mlist)
            assert len(isos) > 0, f"区域 {region} 无有效国家"


# ═══════════════════════════════════════════════════════════
# IEA name index
# ═══════════════════════════════════════════════════════════

class TestIeaNameIndex:
    def test_no_other_aggregate_in_index(self):
        """_build_iea_name_index 不应包含 Other 聚合区域名称。"""
        from compare.common.io import _build_iea_name_index
        idx = _build_iea_name_index()
        for name in idx:
            assert not name.startswith("other"), f"Other aggregate leaked into index: {name}"

    def test_china_in_index(self):
        from compare.common.io import _build_iea_name_index
        idx = _build_iea_name_index()
        assert any("china" in k for k in idx), "China not found in IEA name index"


# ═══════════════════════════════════════════════════════════
# downscale_logit zero-IEA 分支
# ═══════════════════════════════════════════════════════════

class TestDownscaleLogitZeroIEA:
    """区域内所有国家 IEA 为零时，均分 GCAM 区域值（不 crash）。"""

    def test_zero_iea_region_equal_split(self):
        from compare.common.downscale import downscale_logit
        from compare.common.config import INDICATORS

        cfg = INDICATORS["tfc"]
        # 用真实区域 Africa_Eastern（多国区域），所有国家 IEA 为零
        gcam = pd.DataFrame([{
            "Scenario": "SSP126", "Region": "Africa_Eastern",
            **{y: 200.0 for y in YEARS}
        }])
        iea_baseline = {}  # 全部国家 IEA 为零

        df = downscale_logit(iea_baseline, gcam, "SSP126", cfg)
        # 不应 crash（旧代码 n_r 未定义触发 NameError）
        rows = df[df["Region"] == "Africa_Eastern"]
        assert len(rows) >= 2, f"Africa_Eastern should have ≥2 countries, got {len(rows)}"
        for y in YEARS:
            total = float(rows[y].sum())
            assert abs(total - 200.0) < 1e-4, f"y={y}: sum={total}"
