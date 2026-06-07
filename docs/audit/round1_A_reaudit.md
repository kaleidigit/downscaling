# Round 1 Re-Audit: A 层修复后验证

审计日期：2026-06-01
审计范围：修复 A1-A6 后的代码再验证

---

## 修复清单

| 审计项 | 修复前 | 修复后 | 文件 | 行号 |
|--------|--------|--------|------|------|
| A1 | `np.clip(np.abs(beta), 1.0, np.inf)` | `np.clip(beta, 1.0, np.inf)` | dscale_official.py | ~109 |
| A2 | 无 alpha 调和 | 官方 `fun_harmonize_alpha` 逻辑 | dscale_official.py | ~199-208 |
| A3 | 纯 R² 线性插值 | 官方 `fun_max_tc()` 完整实现 | dscale_official.py | 44-87, 338-355 |
| A4 | `max(ei_enshort, 1e-10)` | `np.clip(..., 0.0, 1.0)` | dscale_official.py | ~366 |
| A5 | 2015-2100 (18点) | 未修改（低严重度）| — | — |
| A6 | 缺 `** beta` 指数 | `** max(abs(beta), 1.0)` | common/downscale.py | 353 |

---

## 逐项验证

### A1 — beta clipping 已修复

**修复**: `dscale_official.py` — `np.abs()` 已移除

**验证**:
```
beta    official_clip    our_clip    match
-3.0    1.0              1.0         YES
-2.0    1.0              1.0         YES
-1.5    1.0              1.0         YES
-1.0    1.0              1.0         YES
 2.0    2.0              2.0         YES
```
**结论**: ✅ 通过。所有 beta 值现在与官方一致。

---

### A2 — alpha 调和 已修复

**修复**: `fit_enshort_countries` 中，LogLogFunc 拟合后执行 alpha 调和：
```python
# 官方公式 (utils.py:24672):
# alpha += log(y_base) - (alpha + beta * log(x_base))
t = base_year  # 2015
if t in year_y and t in year_x:
    alpha_raw = ff.alpha
    ff.alpha = alpha_raw + year_y[t] - (alpha_raw + ff.beta * year_x[t])
```

回退逻辑（官方行为）：若 2015 年数据不可用，使用最接近的可用年份。

**验证**（构造数据）:
```
Raw alpha=-2.0, prediction at base: -3.0000
Harmonized alpha=-0.5, prediction at base: -1.5000
Target log(EI) at base: -1.5
→ 精确匹配 ✓
```
**结论**: ✅ 通过。调和后回归线精确通过基准年观测点。

---

### A3 — MAX_TC 动态计算 已修复

**修复**: 新增 `fun_max_tc()` 函数（dscale_official.py:44-87），完全对齐官方 `utils.py:1493-1508` + `utils.py:24290-24321`：
1. Beta 符号冲突检测: `beta_short * beta_long < 0 → 2040`
2. 质量指标: `R² × (hist_end - hist_start)`
3. 动态阈值: `x_min = 0.3*(end_hist-1990)`, `x_max = 1.0*(end_hist-1979)`
4. 线性映射到 `[2040, 2200]`

主循环改为逐国计算 MAX_TC，回退逻辑用于无 ENSHORT 回归的国家。

**验证**:
```
Beta conflict (2.0 × -3.0 < 0):    MAX_TC = 2040 ✓
Low quality  (R²=0.3, 15yr):       MAX_TC = 2040
High quality (R²=0.95, 45yr):      MAX_TC = 2200
Medium       (R²=0.7, 20yr):       MAX_TC = 2076
Both neg    (-2.0×-1.5>0, 35yr):  MAX_TC = 2155 (same sign, not forced to 2040)
```
**结论**: ✅ 通过。逻辑与官方完全一致。

---

### A4 — ENSHORT EI [0,1] 封顶 已修复

**修复**: `dscale_official.py` ENSHORT 计算中:
```python
ei_enshort = float(np.clip(
    np.exp(ep["alpha"] + ep["beta"] * np.log(max(gdp_pcap, 1e-10))),
    0.0, 1.0))
```

**验证**:
```
EI ∈ {-0.1, 0.0, 0.5, 1.0, 1.5} → clip → {0.0, 0.0, 0.5, 1.0, 1.0}
All correct ✓
```
**结论**: ✅ 通过。EI 现在封顶在 [0, 1]，与官方 `step1_fun_enshort_ei` 一致。

---

### A5 — ENLONG 数据来源 [低，未修改]

**评估**: 差异微小（缺失 1990/2005/2010 三个数据点，约 14% 的历史信息）。回归方程和变量与官方等价。GCAM 2015-2100 时间序列已足够稳健。

**建议**: 保留现状，在论文中注明数据起始年份差异。

---

### A6 — 旧版收敛 beta 指数 已修复

**修复**: `common/downscale.py:353`:
```python
conv_weight = np.clip(conv_weight, 0.0, 1.0)
conv_weight = conv_weight ** max(abs(beta), 1.0)  # 官方 β 指数
```

**状态**: ✅ 已修复。旧版 LEGACY 路径现在也包含 beta 指数。

---

## 修复后代码结构总览

```
compare/dscale/dscale_official.py:
├── fun_max_tc()                        # A3: 官方动态 MAX_TC (utils.py:1493)
├── fun_max_tc_convergence()            # A1: beta.clip(1,inf) 无 abs [已修复]
├── fit_enlong_official()               # ENLONG: 官方 LogLogFunc 回归
├── predict_enlong()                    # ENLONG: 逐国预测
├── fit_enshort_countries()             # A2: +alpha调和 [已修复]
│   ├── LogLogFunc.fit()                #     官方回归（零修改）
│   ├── alpha harmonization             # A2: 新增，对齐 utils.py:24672
│   └── params + hist_start/end         # A3: 新增历史年份范围
└── downscale_dscale_official()         # 主函数
    ├── ENLONG → LogLogFunc             #     官方 fit_funcs
    ├── ENSHORT → log-log + clip(0,1)   # A4: +EI封顶 [已修复]
    ├── MAX_TC → fun_max_tc()           # A3: 逐国动态 [已修复]
    ├── 收敛 → fun_max_tc_convergence() # A1: +beta指数(无abs) [已修复]
    └── 区域调和 → _regional_conserve() #     守恒约束
```

---

## 未修复项

| 项目 | 原因 | 风险 |
|------|------|------|
| A5: 扩展回归年份至 1990 | 涉及 IO 层多处修改，收益微小 | 低 |

---

## 审计结论

**A 层 6 项：5 项修复通过，1 项保留（低风险）**

| 审计项 | 状态 | 验证 |
|--------|------|------|
| A1 — beta clipping | ✅ 已修复 | 全 beta 范围对齐官方 |
| A2 — alpha harmonization | ✅ 已修复 | 基年精确匹配，含回退逻辑 |
| A3 — MAX_TC 动态计算 | ✅ 已修复 | 含 beta 符号检测 + R²×duration |
| A4 — EI [0,1] capping | ✅ 已修复 | clip(0,1) 与官方一致 |
| A5 — 数据来源 | ⚠️ 已知差异 | 低影响，未修改 |
| A6 — 旧版 beta 指数 | ✅ 已修复 | LEGACY 路径已补全 |

**官方计算层零修改**：`DSCALE/downscaler/fit_funcs.py` 未经过任何修改 ✅
