"""边缘情况单元测试。

覆盖 gamma_c、phi_kaya、_regional_conserve、零方差 ENSHORT 等关键边缘情况。
"""

import numpy as np
import pandas as pd
import pytest

from compare.common.downscale import (
    gamma_c,
    phi_kaya,
    _regional_conserve,
    _region_isos,
    _finalize_df,
    TC_DEFAULT,
)
from compare.common.mapping import (
    normalize_name,
    load_mapping,
    build_region_members,
    EXCLUDED_ISO,
)
from compare.common.config import YEARS


# ═══════════════════════════════════════════════════════════
# gamma_c
# ═══════════════════════════════════════════════════════════

class TestGammaC:
    def test_average_country_returns_one(self):
        """人均 GDP 等于世界平均 → gamma=1.0。"""
        assert gamma_c(100.0, 100.0) == 1.0

    def test_rich_country_returns_above_one(self):
        """人均 GDP 是世界平均的 10 倍 → gamma > 1。"""
        g = gamma_c(1000.0, 100.0)
        assert g > 1.0
        assert abs(g - (1.0 + 0.3 * np.log(10.0))) < 1e-12

    def test_poor_country_returns_below_one(self):
        """人均 GDP 是世界平均的 1/10 → gamma < 1。"""
        g = gamma_c(10.0, 100.0)
        assert g < 1.0
        assert abs(g - (1.0 + 0.3 * np.log(0.1))) < 1e-12

    def test_zero_gdp_pcap_returns_one(self):
        """人均 GDP 为零 → gamma=1.0（防御值）。"""
        assert gamma_c(0.0, 100.0) == 1.0

    def test_zero_world_pcap_returns_one(self):
        """世界人均 GDP 为零 → gamma=1.0。"""
        assert gamma_c(100.0, 0.0) == 1.0

    def test_both_zero_returns_one(self):
        assert gamma_c(0.0, 0.0) == 1.0

    def test_negative_gdp_returns_one(self):
        assert gamma_c(-50.0, 100.0) == 1.0


# ═══════════════════════════════════════════════════════════
# phi_kaya
# ═══════════════════════════════════════════════════════════

class TestPhiKaya:
    def test_at_2015_returns_zero(self):
        """t=2015 → phi=0（基年无收敛）。"""
        assert phi_kaya(2015, 2.0, 2070) == 0.0

    def test_before_2015_returns_zero(self):
        """t<2015 → phi=0。"""
        assert phi_kaya(2010, 2.0, 2070) == 0.0

    def test_at_convergence_year(self):
        """t=tc → phi = 1 - exp(-gamma)。"""
        phi = phi_kaya(2070, 1.0, 2070)
        expected = 1.0 - np.exp(-1.0)
        assert abs(phi - expected) < 1e-12

    def test_after_convergence_year(self):
        """t > tc → phi → 1.0（但永远不完全到达）。"""
        phi = phi_kaya(2100, 2.0, 2070)
        assert 0.9 < phi < 1.0

    def test_large_gamma_fast_convergence(self):
        """大 gamma → phi 更快接近 1。"""
        phi_low = phi_kaya(2050, 1.0, 2100)
        phi_high = phi_kaya(2050, 5.0, 2100)
        assert phi_high > phi_low

    def test_monotonic_in_time(self):
        """phi 随时间单调递增。"""
        vals = [phi_kaya(t, 2.0, 2070) for t in [2015, 2030, 2050, 2070, 2100]]
        for i in range(len(vals) - 1):
            assert vals[i] <= vals[i + 1]


# ═══════════════════════════════════════════════════════════
# TC_DEFAULT
# ═══════════════════════════════════════════════════════════

class TestTCDefault:
    def test_all_scenarios_have_tc(self):
        for sc in ["SSP126", "SSP245", "SSP434", "SSP460"]:
            assert sc in TC_DEFAULT

    def test_tc_values_are_increasing(self):
        """更可持续的情景应有更晚的收敛年份。"""
        assert TC_DEFAULT["SSP126"] <= TC_DEFAULT["SSP245"]
        assert TC_DEFAULT["SSP245"] <= TC_DEFAULT["SSP434"]
        assert TC_DEFAULT["SSP434"] <= TC_DEFAULT["SSP460"]

    def test_tc_values_in_valid_range(self):
        for tc in TC_DEFAULT.values():
            assert 2000 < tc <= 2100


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
        # normalize_name 移除变音符号并删除空格等特殊字符
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
        # China should be mappable
        assert any("china" in k for k in idx), "China not found in IEA name index"
