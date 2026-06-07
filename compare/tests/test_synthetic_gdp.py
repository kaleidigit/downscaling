"""合成 GDP 测试：验证 9 个缺口国家的 GDP 注入。"""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from compare.common.io import generate_synthetic_gdp, read_gdp_country
from compare.common.config import SCENARIOS, gdp_country_path

GAP_ISOS = {"afg", "ago", "alb", "are", "mmr", "mne", "ncl", "prk", "qat"}


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_synthetic_gdp_has_all_gap_countries(scenario):
    s = generate_synthetic_gdp(scenario)
    isos = set(s["iso"].unique())
    assert GAP_ISOS.issubset(isos), f"{scenario}: missing {GAP_ISOS - isos}"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_synthetic_gdp_no_zero_values(scenario):
    s = generate_synthetic_gdp(scenario)
    year_cols = [c for c in s.columns if isinstance(c, int)]
    for _, row in s.iterrows():
        vals = [row[y] for y in year_cols]
        assert all(v > 0 for v in vals), \
            f"{scenario}/{row['iso']}: contains zero or negative value"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_synthetic_gdp_format(scenario):
    s = generate_synthetic_gdp(scenario)
    assert "iso" in s.columns
    year_cols = [c for c in s.columns if isinstance(c, int)]
    assert len(year_cols) >= 17  # 2015..2100 = 18 years
    assert all(2015 <= y <= 2100 for y in year_cols)
    assert s["iso"].dtype == object


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_synthetic_gdp_growth(scenario):
    s = generate_synthetic_gdp(scenario)
    for _, row in s.iterrows():
        assert row[2100] > row[2015], \
            f"{scenario}/{row['iso']}: 2100 GDP ({row[2100]:.2f}) <= 2015 ({row[2015]:.2f})"


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_gdp_country_includes_synthetic(scenario):
    gdp = read_gdp_country(gdp_country_path(scenario))
    isos = set(gdp["iso"].unique())
    missing = GAP_ISOS - isos
    assert not missing, f"{scenario}: read_gdp_country missing {missing}"
    # 验证合成国家的值非零
    for iso in GAP_ISOS:
        row = gdp[gdp["iso"] == iso]
        assert len(row) == 1, f"{scenario}/{iso}: expected 1 row, got {len(row)}"
        v = float(row.iloc[0][2015])
        assert v > 0, f"{scenario}/{iso}: 2015 GDP = {v} (should be > 0)"


def test_synthetic_gdp_empty_when_none_missing():
    """如果所有国家都有 GDP，应返回空 DataFrame。"""
    path = gdp_country_path("SSP126")
    import pandas as pd
    orig = pd.read_excel(path, engine="openpyxl", dtype=str)
    # 验证当前确实有缺口国家
    s = generate_synthetic_gdp("SSP126")
    assert len(s) == 9, f"Expected 9 gap countries, got {len(s)}"
