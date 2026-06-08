"""交叉验证：用官方 DSCALE 代码验证我们的实现。

将官方 Energy_demand_downs_1.py 的 DataFrame 公式与我们向量化实现
在相同合成数据上对比，逐元素断言差异 < 1e-12。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_DSCALE_REPO = Path(__file__).resolve().parents[2] / "DSCALE"
sys.path.insert(0, str(_DSCALE_REPO))

from compare.dscale.dscale_official import (
    fun_max_tc_convergence,
    fun_max_tc,
    fit_enlong_official,
    ENLONG_YEARS,
    MAX_TC_Y_MIN,
    MAX_TC_DEFAULT,
)


# ═══════════════════════════════════════════════════════════
# 官方 DSCALE 的 DataFrame 收敛公式（逐行复制自
# Energy_demand_downs_1.py:650-675，仅去除了 setindex 调用）
# ═══════════════════════════════════════════════════════════

def _official_df_convergence(df):
    """官方 fun_max_tc_convergence 的核心计算逻辑。"""
    df = df.copy()
    conv_weight = (
        (df["TIME"] - df["MAX_TC"].astype(float))
        / (2010.0 - df["MAX_TC"].astype(float))
    ).clip(0, 1)
    conv_weight = conv_weight ** (df["BETA"].clip(1, np.inf))
    df["RESULT"] = (
        df["ENSHORT"] * conv_weight
        + df["ENLONG"] * (1.0 - conv_weight)
    )
    return df


# ═══════════════════════════════════════════════════════════
# Test 1: fun_max_tc_convergence — 对比官方实现
# ═══════════════════════════════════════════════════════════

class TestFunMaxTcConvergence:

    def _compare(self, enshort, enlong, time_points, max_tc, beta):
        """用相同输入分别调用官方公式和我们的实现，断言一致。"""
        es = np.asarray(enshort, dtype=float)
        el = np.asarray(enlong, dtype=float)
        t = np.asarray(time_points, dtype=float)
        mtc = np.asarray(max_tc, dtype=float)
        b = np.asarray(beta, dtype=float)

        # 我们的向量化实现
        our_result = fun_max_tc_convergence(es, el, t, mtc, b)

        # 官方 DataFrame 实现
        df = pd.DataFrame({
            "TIME": t,
            "MAX_TC": mtc,
            "ENSHORT": es,
            "ENLONG": el,
            "BETA": b,
        })
        official_df = _official_df_convergence(df)
        official_result = official_df["RESULT"].values

        assert np.all(np.abs(our_result - official_result) < 1e-12), \
            f"our={our_result} vs official={official_result}"
        return our_result, official_result

    def test_single_point_normal(self):
        """β=2.0, t=2050, max_tc=2100 — 应与官方一致。"""
        r, o = self._compare([100.0], [200.0], [2050.0], [2100.0], [2.0])
        assert 160 < r[0] < 180

    def test_negative_beta(self):
        """β=-3 应被 clip 到 1 — 与官方一致。"""
        r, o = self._compare([100.0], [200.0], [2050.0], [2100.0], [-3.0])
        assert abs(r[0] - 144.44) < 0.1

    def test_small_beta_clips(self):
        """β=0.3 应被 clip 到 1 — 与官方一致。"""
        self._compare([100.0], [200.0], [2050.0], [2100.0], [0.3])

    def test_high_beta_fast_convergence(self):
        """β=5.0 加速收敛 — 结果接近 ENLONG。"""
        r, _ = self._compare([100.0], [200.0], [2070.0], [2100.0], [5.0])
        assert r[0] > 185

    def test_t_at_2010(self):
        """t=2010 → conv_weight=1 → 纯 ENSHORT。"""
        r, _ = self._compare([100.0], [200.0], [2010.0], [2100.0], [2.0])
        assert abs(r[0] - 100.0) < 1e-12

    def test_t_at_max_tc(self):
        """t=MAX_TC → conv_weight=0 → 纯 ENLONG。"""
        r, _ = self._compare([100.0], [200.0], [2100.0], [2100.0], [2.0])
        assert abs(r[0] - 200.0) < 1e-12

    def test_max_tc_below_2010(self):
        """max_tc < 2010 → conv_weight 被 clip → 纯 ENSHORT。"""
        r, _ = self._compare([100.0], [200.0], [2050.0], [2000.0], [2.0])
        assert abs(r[0] - 100.0) < 1e-12

    def test_t_before_2010(self):
        """t < 2010 → conv_weight 被 clip → 纯 ENSHORT。"""
        r, _ = self._compare([100.0], [200.0], [2005.0], [2100.0], [2.0])
        assert abs(r[0] - 100.0) < 1e-12

    def test_vectorized(self):
        """5 时间点向量化 — 单调收敛 + 与官方一致。"""
        t = np.array([2015, 2030, 2050, 2070, 2100], dtype=float)
        r, _ = self._compare(
            np.full(5, 100.0), np.full(5, 200.0),
            t, np.full(5, 2100.0), np.full(5, 2.0)
        )
        for i in range(len(r) - 1):
            assert r[i] <= r[i + 1], f"Not monotonic at i={i}: {r}"

    def test_per_country(self):
        """3 个不同国家的 MAX_TC 和 β — 与官方一致 + 排序正确。"""
        r, _ = self._compare(
            [100.0, 100.0, 100.0],
            [200.0, 200.0, 200.0],
            [2050.0, 2050.0, 2050.0],
            [2040.0, 2120.0, 2200.0],
            [3.0, 1.5, 1.0],
        )
        # 更小的 MAX_TC → 更早收敛 → 更接近 ENLONG(200)
        assert r[0] > r[1] > r[2]


# ═══════════════════════════════════════════════════════════
# Test 2: fun_max_tc — 动态 MAX_TC
# ═══════════════════════════════════════════════════════════

class TestFunMaxTc:
    def test_sign_conflict_returns_y_min(self):
        assert fun_max_tc(2.0, 0.8, 1990, 2015, -1.5) == float(MAX_TC_Y_MIN)

    def test_neg_short_pos_long(self):
        assert fun_max_tc(-1.0, 0.5, 1990, 2015, 2.0) == float(MAX_TC_Y_MIN)

    def test_high_quality_late(self):
        r = fun_max_tc(2.0, 0.9, 1970, 2015, 1.5)
        assert r >= 2100

    def test_low_quality_early(self):
        r = fun_max_tc(1.0, 0.2, 2005, 2015, 0.5)
        assert r == float(MAX_TC_Y_MIN)

    def test_both_zero(self):
        r = fun_max_tc(0.0, 0.5, 1990, 2015, 0.0)
        assert MAX_TC_Y_MIN <= r <= MAX_TC_DEFAULT

    def test_r_squared_zero(self):
        r = fun_max_tc(2.0, 0.0, 1990, 2015, 1.0)
        assert MAX_TC_Y_MIN <= r <= MAX_TC_DEFAULT


# ═══════════════════════════════════════════════════════════
# Test 3: ENLONG 回归 + alpha 调和
# ═══════════════════════════════════════════════════════════

class TestFitEnlongOfficial:
    def test_perfect_power_law(self):
        yrs = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y - 2000) for y in yrs}, dtype=float)
        pop = pd.Series({y: 1.0 for y in yrs}, dtype=float)
        tfc = pd.Series({y: float((y - 2000) ** 3) for y in yrs}, dtype=float)
        ff = fit_enlong_official(tfc, gdp, pop)
        assert ff.r_squared > 0.99
        assert abs(ff.beta - 2.0) < 0.01

    def test_constant_ei(self):
        yrs = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y - 2000) for y in yrs}, dtype=float)
        pop = pd.Series({y: 1.0 for y in yrs}, dtype=float)
        tfc = pd.Series({y: 10.0 * (y - 2000) for y in yrs}, dtype=float)
        ff = fit_enlong_official(tfc, gdp, pop)
        assert abs(ff.beta) < 1e-4

    def test_insufficient_data(self):
        gdp = pd.Series({2015: 10.0, 2020: 20.0}, dtype=float)
        pop = pd.Series({2015: 1.0, 2020: 1.0}, dtype=float)
        tfc = pd.Series({2015: 100.0, 2020: 200.0}, dtype=float)
        ff = fit_enlong_official(tfc, gdp, pop)
        assert ff.r_squared == 0.0
        assert ff.beta == 1.0  # B1 fix

    def test_all_zero(self):
        yrs = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y) for y in yrs}, dtype=float)
        pop = pd.Series({y: 1.0 for y in yrs}, dtype=float)
        tfc = pd.Series({y: 0.0 for y in yrs}, dtype=float)
        ff = fit_enlong_official(tfc, gdp, pop)
        assert ff.r_squared == 0.0

    def test_enlong_years_format(self):
        assert 1990 in ENLONG_YEARS and 2100 in ENLONG_YEARS
        assert len(ENLONG_YEARS) == 21


# ═══════════════════════════════════════════════════════════
# Test 4: predict_enlong
# ═══════════════════════════════════════════════════════════

class TestPredictEnlong:
    def test_matches_formula(self):
        from compare.dscale.dscale_official import predict_enlong
        from downscaler.fit_funcs import LogLogFunc
        ff = LogLogFunc(alpha=1.0, beta=2.0)
        ff.r_squared = 0.99
        result = predict_enlong(ff, 100.0, 10.0, 100.0)
        expected = np.exp(1.0 + 2.0 * np.log(100.0 / 10.0)) * 100.0
        assert abs(result - expected) < 1e-6

    def test_zero_gdp(self):
        from compare.dscale.dscale_official import predict_enlong
        from downscaler.fit_funcs import LogLogFunc
        ff = LogLogFunc(alpha=1.0, beta=2.0)
        ff.r_squared = 0.99
        assert predict_enlong(ff, 0.0, 10.0, 0.0) == 0.0

    def test_zero_pop(self):
        from compare.dscale.dscale_official import predict_enlong
        from downscaler.fit_funcs import LogLogFunc
        ff = LogLogFunc(alpha=1.0, beta=2.0)
        ff.r_squared = 0.99
        assert predict_enlong(ff, 100.0, 0.0, 100.0) == 0.0
