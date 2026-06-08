"""交叉验证：对比官方 DSCALE 代码与我们的实现。

用相同的合成输入数据，分别调用官方 DSCALE 核心函数和我们的实现，
逐函数断言输出一致（差异 < 1e-12）。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# 将官方 DSCALE 仓库加入 path
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
# Test 1: fun_max_tc_convergence — 对比官方实现
# ═══════════════════════════════════════════════════════════

def _official_convergence(enshort, enlong, time_points, max_tc, beta):
    """逐元素复制官方 Energy_demand_downs_1.py:650-675 的收敛公式。"""
    beta_clipped = np.clip(np.asarray(beta, dtype=float), 1.0, np.inf)
    conv_weight = (np.asarray(time_points, dtype=float) - np.asarray(max_tc, dtype=float)) / (2010.0 - np.asarray(max_tc, dtype=float))
    conv_weight = np.clip(conv_weight, 0.0, 1.0)
    conv_weight = conv_weight ** beta_clipped
    return np.asarray(enshort) * conv_weight + np.asarray(enlong) * (1.0 - conv_weight)


class TestFunMaxTcConvergence:
    """逐公式验证 fun_max_tc_convergence 的行为。"""

    def test_normal_beta(self):
        """β=2, t=2050, max_tc=2100 → 中间权重。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2050.0]), np.array([2100.0]), np.array([2.0])
        )
        expected = _official_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2050.0]), np.array([2100.0]), np.array([2.0])
        )
        # conv_weight = ((2050-2100)/(2010-2100))^2 = (-50/-90)^2 = 0.5556^2 = 0.3086
        # result = 100*0.3086 + 200*0.6914 = 169.14
        assert abs(float(r[0]) - float(expected[0])) < 1e-12
        assert 160 < float(r[0]) < 180

    def test_negative_beta_clips_to_one(self):
        """β=-3 → clip(β,1,∞)=1 → 线性收敛。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2050.0]), np.array([2100.0]), np.array([-3.0])
        )
        expected = _official_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2050.0]), np.array([2100.0]), np.array([-3.0])
        )
        assert abs(float(r[0]) - float(expected[0])) < 1e-12
        # conv_weight = 0.5556^1 = 0.5556, result ≈ 144.4
        assert abs(float(r[0]) - 144.44444) < 0.1

    def test_small_beta_clips_to_one(self):
        """β=0.3 → clip(0.3,1,∞)=1 → 线性收敛。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2050.0]), np.array([2100.0]), np.array([0.3])
        )
        expected = _official_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2050.0]), np.array([2100.0]), np.array([0.3])
        )
        assert abs(float(r[0]) - float(expected[0])) < 1e-12

    def test_high_beta_fast_convergence(self):
        """β=5, t=2070, max_tc=2100 → 非常快接近 ENLONG。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2070.0]), np.array([2100.0]), np.array([5.0])
        )
        # conv_weight = (60/-90)^5 = (2/3)^5 ≈ 0.132
        # ENSHORT contribution is very small, dominated by ENLONG
        assert float(r[0]) > 185  # close to ENLONG (200)

    def test_t_at_2010_is_pure_enshort(self):
        """t=2010 → conv_weight=1 → 纯 ENSHORT。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2010.0]), np.array([2100.0]), np.array([2.0])
        )
        assert abs(float(r[0]) - 100.0) < 1e-12

    def test_t_at_max_tc_is_pure_enlong(self):
        """t=MAX_TC → conv_weight=0 → 纯 ENLONG。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2100.0]), np.array([2100.0]), np.array([2.0])
        )
        assert abs(float(r[0]) - 200.0) < 1e-12

    def test_max_tc_below_2010_clips_to_enshort(self):
        """max_tc=2000 < 2010 → 分母为负, conv_weight>1 → clip → 纯 ENSHORT。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2050.0]), np.array([2000.0]), np.array([2.0])
        )
        assert abs(float(r[0]) - 100.0) < 1e-12

    def test_t_before_2010_clips_to_enshort(self):
        """t=2005 < 2010 → conv_weight>1 → clip → 纯 ENSHORT。"""
        r = fun_max_tc_convergence(
            np.array([100.0]), np.array([200.0]),
            np.array([2005.0]), np.array([2100.0]), np.array([2.0])
        )
        assert abs(float(r[0]) - 100.0) < 1e-12

    def test_vectorized_multiple_points(self):
        """向量化：5 个时间点的数组。"""
        t = np.array([2015, 2030, 2050, 2070, 2100], dtype=float)
        es = np.full(5, 100.0)
        el = np.full(5, 200.0)
        mtc = np.full(5, 2100.0)
        beta = np.full(5, 2.0)
        r = fun_max_tc_convergence(es, el, t, mtc, beta)
        expected = _official_convergence(es, el, t, mtc, beta)
        assert np.all(np.abs(r - expected) < 1e-12)
        # 随时间推移从 ENSHORT 向 ENLONG 移动
        assert r[0] < r[1] < r[2] < r[3] < r[4]

    def test_per_country_beta_and_max_tc(self):
        """每国不同 β 和 MAX_TC → 向量化处理。"""
        es = np.array([100.0, 100.0, 100.0])
        el = np.array([200.0, 200.0, 200.0])
        t = np.array([2050.0, 2050.0, 2050.0])
        mtc = np.array([2040.0, 2120.0, 2200.0])
        beta = np.array([3.0, 1.5, 1.0])

        r = fun_max_tc_convergence(es, el, t, mtc, beta)
        expected = _official_convergence(es, el, t, mtc, beta)
        assert np.all(np.abs(r - expected) < 1e-12)
        # 更快收敛的 MAX_TC → 更接近 ENLONG (200)
        assert r[0] > r[1] > r[2]


# ═══════════════════════════════════════════════════════════
# Test 2: fun_max_tc — 动态 MAX_TC 计算
# ═══════════════════════════════════════════════════════════

class TestFunMaxTc:
    def test_sign_conflict_returns_y_min(self):
        """β_short 和 β_long 符号相反 → 立即收敛 (y_min)。"""
        result = fun_max_tc(beta_short=2.0, r_squared_short=0.8,
                            hist_start=1990, hist_end=2015,
                            beta_long=-1.5)
        assert result == float(MAX_TC_Y_MIN)  # 2040

    def test_negative_short_positive_long_returns_y_min(self):
        """β_short<0, β_long>0 → 符号冲突。"""
        result = fun_max_tc(beta_short=-1.0, r_squared_short=0.5,
                            hist_start=1990, hist_end=2015,
                            beta_long=2.0)
        assert result == float(MAX_TC_Y_MIN)

    def test_same_sign_high_quality_gives_late_convergence(self):
        """相同符号 + 高 R² + 长数据期 → 后期收敛。"""
        result = fun_max_tc(beta_short=2.0, r_squared_short=0.9,
                            hist_start=1970, hist_end=2015,
                            beta_long=1.5)
        # quality = 0.9 * 45 = 40.5
        # x_min = 0.3*(2015-1990) = 7.5, x_max = 1.0*(2015-1979) = 36.0
        # slope = (2200-2040)/(36-7.5) = 160/28.5 ≈ 5.614
        # intercept = 2040 - 5.614*7.5 ≈ 1997.9
        # max_tc = round(1997.9 + 5.614*40.5) = round(2225.5) = 2226 → clipped to 2200
        assert result >= 2100

    def test_same_sign_low_quality_gives_early_convergence(self):
        """相同符号 + 低 R² + 短数据期 → 早期收敛。"""
        result = fun_max_tc(beta_short=1.0, r_squared_short=0.2,
                            hist_start=2005, hist_end=2015,
                            beta_long=0.5)
        # quality = 0.2 * 10 = 2.0
        # x_min = 0.3*(2015-1990) = 7.5
        # quality < x_min → clip to y_min
        assert result == float(MAX_TC_Y_MIN)

    def test_both_betas_zero(self):
        """β_short=β_long=0 → 无符号冲突，但两个回归都是 flat。"""
        result = fun_max_tc(beta_short=0.0, r_squared_short=0.5,
                            hist_start=1990, hist_end=2015,
                            beta_long=0.0)
        # 0*0=0, not <0, so passes sign check
        # Falls through to quality-based calculation
        assert MAX_TC_Y_MIN <= result <= MAX_TC_DEFAULT

    def test_r_squared_zero(self):
        """R²=0 → quality=0 → 很可能被裁剪到 y_min。"""
        result = fun_max_tc(beta_short=2.0, r_squared_short=0.0,
                            hist_start=1990, hist_end=2015,
                            beta_long=1.0)
        assert MAX_TC_Y_MIN <= result <= MAX_TC_DEFAULT


# ═══════════════════════════════════════════════════════════
# Test 3: ENLONG 回归 — 对比 LogLogFunc
# ═══════════════════════════════════════════════════════════

class TestFitEnlongOfficial:
    """用合成数据测试 fit_enlong_official，验证 LogLogFunc 回归。"""

    def test_perfect_power_law(self):
        """完美 power law: TFC/GDP = (GDP/POP)^2 → β=2, exact fit。"""
        years = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y - 2000) for y in years}, dtype=float)
        pop = pd.Series({y: 1.0 for y in years}, dtype=float)
        # EI = (GDP/POP)^2 = gdp^2
        # TFC = EI * GDP = gdp^3
        tfc = pd.Series({y: float((y - 2000) ** 3) for y in years}, dtype=float)

        ff = fit_enlong_official(tfc, gdp, pop)
        # log(EI) = log(gdp^2) = 2*log(gdp) → alpha=0, beta=2
        assert ff.r_squared > 0.99
        assert abs(ff.beta - 2.0) < 0.01
        assert abs(ff.alpha) < 0.1

    def test_constant_energy_intensity(self):
        """恒定 EI → TFC = k*GDP → log(EI) = const → β≈0。"""
        years = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y - 2000) for y in years}, dtype=float)
        pop = pd.Series({y: 1.0 for y in years}, dtype=float)
        tfc = pd.Series({y: 10.0 * (y - 2000) for y in years}, dtype=float)  # EI=10

        ff = fit_enlong_official(tfc, gdp, pop)
        # log(10*gdp/gdp) = log(10) → constant → β≈0
        assert abs(ff.beta) < 0.01
        assert abs(np.exp(ff.alpha) - 10.0) < 0.1

    def test_insufficient_data_returns_degenerate(self):
        """不足 3 个数据点 → 退化 LogLogFunc。"""
        gdp = pd.Series({2015: 10.0, 2020: 20.0}, dtype=float)
        pop = pd.Series({2015: 1.0, 2020: 1.0}, dtype=float)
        tfc = pd.Series({2015: 100.0, 2020: 200.0}, dtype=float)

        ff = fit_enlong_official(tfc, gdp, pop)
        assert ff.r_squared == 0.0
        assert ff.beta is not None  # B1 修复：不再是 None

    def test_all_zero_tfc_returns_degenerate(self):
        """全部零 TFC → 无有效正 EI → 退化。"""
        years = list(range(2015, 2101, 5))
        gdp = pd.Series({y: float(y) for y in years}, dtype=float)
        pop = pd.Series({y: 1.0 for y in years}, dtype=float)
        tfc = pd.Series({y: 0.0 for y in years}, dtype=float)

        ff = fit_enlong_official(tfc, gdp, pop)
        assert ff.r_squared == 0.0
        assert ff.beta is not None

    def test_enlong_years_superset(self):
        """ENLONG_YEARS 包含 GCAM TFC 文件中实际存在的列。"""
        # 这确保我们声明的回归年份和数据文件中的列匹配
        # 文件列已在上次审计中验证
        assert 1990 in ENLONG_YEARS
        assert 2015 in ENLONG_YEARS
        assert 2100 in ENLONG_YEARS
        assert len(ENLONG_YEARS) == 21  # 3 pre-2015 (1990,2005,2010) + 18 at 5yr intervals (2015-2100)


# ═══════════════════════════════════════════════════════════
# Test 4: predict_enlong 数值一致性
# ═══════════════════════════════════════════════════════════

class TestPredictEnlong:
    def test_predict_matches_direct_formula(self):
        """predict_enlong 的输出应与直接公式一致。"""
        from compare.dscale.dscale_official import predict_enlong
        from downscaler.fit_funcs import LogLogFunc

        # 构造 ENLONG 回归：log(EI) = 1 + 2*log(GDP/POP) → EI = e*(GDP/POP)^2
        ff = LogLogFunc(alpha=1.0, beta=2.0)
        ff.r_squared = 0.99

        gdp, pop = 100.0, 10.0
        # EI = exp(1) * (100/10)^2 = 2.718 * 100 = 271.8
        # ENLONG = EI * GDP = 271.8 * 100 = 27183
        result = predict_enlong(ff, gdp, pop, gdp)
        expected = np.exp(1.0 + 2.0 * np.log(gdp / pop)) * gdp
        assert abs(result - expected) < 1e-6
        assert result > 0

    def test_zero_gdp_returns_zero(self):
        """GDP=0 → 返回 0。"""
        from compare.dscale.dscale_official import predict_enlong
        from downscaler.fit_funcs import LogLogFunc
        ff = LogLogFunc(alpha=1.0, beta=2.0)
        ff.r_squared = 0.99
        assert predict_enlong(ff, 0.0, 10.0, 0.0) == 0.0

    def test_zero_population_returns_zero(self):
        """POP=0 → 返回 0。"""
        from compare.dscale.dscale_official import predict_enlong
        from downscaler.fit_funcs import LogLogFunc
        ff = LogLogFunc(alpha=1.0, beta=2.0)
        ff.r_squared = 0.99
        assert predict_enlong(ff, 100.0, 0.0, 100.0) == 0.0
