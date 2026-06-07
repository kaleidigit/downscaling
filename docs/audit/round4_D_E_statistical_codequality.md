# Round 4+5 Audit: D 层（统计严谨性）+ E 层（代码质量）

审计日期：2026-06-01

---

## D 层：统计严谨性

### D1 — 区域守恒 [高] ✅

所有输出文件的全球总量：
```
logit/SSP126: 560,736,060 TJ (2100)
kaya/SSP126:  560,736,060 TJ (2100)
dscale/SSP126: 560,736,060 TJ (2100)
```
三方案完全一致（期望值——它们都受同一 GCAM 区域总量约束）。

DSCALE 日志记录：最大偏差 = 0.000002 TJ < 1e-6 阈值 ✅

**结论**: ✅ 通过。

---

### D2 — 全局守恒 [高] ✅

日志中逐年全局偏差：
```
2015: 偏差=0.000000 TJ
2020: 偏差=0.000000 TJ
...
2100: 偏差=0.000000 TJ
```
所有年份×情景×方法的全局偏差均为 0（机器精度内）。

**结论**: ✅ 通过。

---

### D3 — 负值检查 / 份额有界性 [高] ⚠️

| 方法 | 国家数 | 负值数 | 来源 |
|------|--------|--------|------|
| logit | 175 | 0 | ✅ |
| kaya | 176 | 9 | oth 行，~1e-6 TJ |
| dscale | 176 | 6 | oth 行，~1e-6 TJ |

所有负值均在 `iso="oth"`（Other Residual Global）行，数量级 ~1e-6 TJ，属于浮点舍入误差，非真实负 TFC。

份额指标有界性（化石/可再生/电气化率 ∈ [0,1]）：**未在此轮验证**（需要份额指标输出文件）。

**结论**: ⚠️ 通过（负值为可忽略的舍入误差）。建议在 `_finalize_df` 中对 oth 行做 `clip(0, None)`。

---

### D4 — 单国区域一致性 [高] ✅

15 个单国区域（Argentina, Brazil, Canada, China, Colombia, India, Indonesia, Japan, Mexico, Pakistan, Russia, South Africa, South Korea, Taiwan→China, USA）。

SSP126 2100 年抽样验证（三方案值完全一致）:
```
USA:  logit=76,414,781 | kaya=76,414,781 | dscale=76,414,781 ✓
Brazil: logit=12,805,647 | kaya=12,805,647 | dscale=12,805,647 ✓
China: logit=72,714,013 | kaya=72,714,013 | dscale=72,714,013 ✓
India: logit=52,495,577 | kaya=52,495,577 | dscale=52,495,577 ✓
```
单国区域因守恒约束，三方案结果必然一致 ✅。

---

### D5 — DSCALE 回归质量 [中] ⚠️

ENSHORT 历史回归（1970-2015 log-log）:
- 140 国完成回归
- 其余国家回退至 GDP 缩放或 EI 趋势外推

**未获得 R² 分布的具体数值**（需要从 `fit_enshort_countries` 输出中提取）。日志文件未记录 R² 分布统计。

**建议**: 在 `fit_enshort_countries` 函数或日志中添加 R² 分布（min/Q25/median/Q75/max），并标记 R²<0.3 的国家。

---

### D6 — Kaya 极端值检测 [高] ⚠️

| 情景 | CAGR > 20%/年 | CAGR < -10%/年 | 备注 |
|------|-------------|-------------|------|
| SSP126 | 0 | **73** | 多国 TFC→0 |
| SSP245 | 0 | **64** | 多国 TFC→0 |
| SSP434 | 0 | **36** | 改善但仍严重 |
| SSP460 | 0 | **27** | 相对最好 |

极端案例（SSP126）:
- bdi: -100%/yr (203→0 TJ)
- eth: -100%/yr (1,990,172→0 TJ)
- ken: -100%/yr (895,908→0 TJ)

**根因**: Kaya 收敛公式对低人均 GDP 国家，当 gamma 为负（修复前）或能量强度趋势不收敛时，TFC 被驱至 0。

**C1 修复（人均 GDP）预期会改善此问题**，但需要重新运行 Kaya 方案验证。当前输出使用修复前的参数。

**建议**: 用 C1 修复后的参数重新运行 Kaya，重新评估极端值。

---

## E 层：代码质量

### E1 — 重复函数合并 [高] ✅ 已修复

5 个函数在 `common/downscale.py` 和 `dscale/dscale_official.py` 中重复定义：

| 函数 | 修复 |
|------|------|
| `_build_iso_info` | 从 dscale_official 删除，改为 import |
| `_region_isos` | 同上 |
| `_regional_conserve` | 同上 |
| `_make_row` | 同上 |
| `_finalize_df` | 同上 |

**修复**: `dscale_official.py` 新增导入：
```python
from ..common.downscale import (
    _build_iso_info, _region_isos, _regional_conserve, _make_row, _finalize_df,
)
```

删除了 ~50 行重复代码 ✅

---

### E2 — IEA_VARIANTS 重复 [中] ✅ 已修复

- `io.py:39` (旧): `read_iea_tfc` 中的内联 `variants` 字典
- `io.py:165` (旧): 模块级 `IEA_VARIANTS` 字典

两字典内容完全相同。

**修复**:
1. `IEA_VARIANTS` 移至文件顶部（`io.py:11-17`）
2. `read_iea_tfc` 中的内联 dict 替换为 `variants = IEA_VARIANTS`
3. 删除旧位置的重复定义

---

### E3 — np.seterr 审查 [中] ✅ 已修复

**修复前** (`dscale_official.py:22`):
```python
np.seterr(all="ignore")  # 抑制所有 numpy 警告
```

**修复后**:
```python
np.seterr(divide="ignore", invalid="ignore")  # 仅抑制除零/无效值
```

保留对 overflow 和 underflow 的警告能力（这些可能指示真实的数值问题）。

---

## 汇总

### D 层 6 项

| 审计项 | 状态 | 行动 |
|--------|------|------|
| D1 — 区域守恒 | ✅ 通过 | — |
| D2 — 全局守恒 | ✅ 通过 | — |
| D3 — 负值/有界性 | ⚠️ 通过 | oth 行舍入误差，可忽略 |
| D4 — 单国区域 | ✅ 通过 | — |
| D5 — 回归质量 | ⚠️ 未验证 | 需在日志中添加 R² 分布 |
| D6 — Kaya 极端值 | ⚠️ 严重 | C1 修复后重跑验证 |

### E 层 3 项

| 审计项 | 状态 |
|--------|------|
| E1 — 重复函数 | ✅ 已修复 |
| E2 — 重复字典 | ✅ 已修复 |
| E3 — np.seterr | ✅ 已修复 |

---

## 全审计汇总 (5 层 25 项)

| 层级 | 通过 | 需关注 | 已修复 | 总计 |
|------|------|--------|--------|------|
| A — 官方一致性 | 0 | 1 (A5) | 5 | 6 |
| B — 数据链路 | 3 | 3 | 1 | 7 |
| C — 算法参数 | 2 | 2 | 1 | 5 |
| D — 统计严谨 | 3 | 3 | 0 | 6 |
| E — 代码质量 | 0 | 0 | 3 | 3 |
| **总计** | **8** | **9** | **10** | **27** |

注：部分项目跨类别（如 A5 在 D 层深入验证），总计大于 25。

### 需要用户行动的高优先级项目

1. **C1+Kaya 重跑**: 用修复后的人均 GDP 参数重新运行 Kaya 方案
2. **DSCALE 重跑**: 用 A1-A4 修复后的代码重新运行 DSCALE 方案
3. **D5 增强**: 在 DSCALE 日志中添加 ENSHORT 回归 R² 分布
4. **CLAUDE.md 更新**: 排除实体列表从 9 个更新为 5 个

### 已创建的审计报告

| 文件 | 轮次 |
|------|------|
| `docs/audit/round1_A_official_consistency.md` | A 层初始审计 |
| `docs/audit/round1_A_reaudit.md` | A 层修复后再审计 |
| `docs/audit/round2_B_data_linkage.md` | B 层审计+修复 |
| `docs/audit/round3_C_algorithm_params.md` | C 层审计+修复 |
| `docs/audit/round4_D_E_statistical_codequality.md` | D+E 层审计+修复 |
