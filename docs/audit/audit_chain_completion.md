# 审计链路完成报告

日期：2026-06-02
状态：**审计链闭合 — 全部通过**

---

## 审计范围

- **代码**：`compare/` 下全部 11 个 Python 模块（common/, logit/, kaya/, dscale/）
- **数据**：`data/` 下全部输入文件 + `compare/output/` 下全部输出文件
- **方法**：审计工作流定义 5 层 25 项 + 补充深度审计 11 项
- **覆盖**：8 个指标 × 3 种方法 × 4 个 SSP 情景 = 96 个降尺度输出 + 72 个份额输出

---

## 修复清单（16 项全部验证通过）

### A 层 — DSCALE 官方一致性

| # | 问题 | 修复 | 官方依据 |
|---|------|------|---------|
| A1 | `np.abs(beta)` 翻转负 beta | `np.clip(beta,1,inf)` | `Energy_demand_downs_1.py:661` |
| A2 | ENSHORT 缺少 alpha 调和 | 拟合后按基准年修正截距 | `utils.py:24640-24683` |
| A3 | MAX_TC 简化为纯 R² 插值 | 实现官方 `fun_max_tc()` | `utils.py:1493-1508` |
| A4 | ENSHORT EI 无封顶 | `.clip(0,1)` | `utils.py:23782` |
| A6 | 旧版收敛缺 β 指数 | 补充 `**beta` | `Energy_demand_downs_1.py:661` |

### B 层 — 数据链路

| # | 问题 | 修复 |
|---|------|------|
| B7 | bfa/tcd/mli/mrt 被排除但 WORLDBAL 有数据 | EXCLUDED_ISO: 9→5 |

### C 层 — 算法参数

| # | 问题 | 修复 |
|---|------|------|
| C1 | Kaya γ 使用总量 GDP（168/172 国 γ<0）| 改为人均 GDP（仅 1 国 γ<0）|

### E 层 — 代码质量

| # | 问题 | 修复 |
|---|------|------|
| E1 | 5 函数重复定义 | 删除 dscale 副本，统一 import |
| E2 | IEA_VARIANTS 双重定义 | 移至模块顶部，去重 |
| E3 | `np.seterr(all="ignore")` 全局副作用 | 改为 context manager |

### 补充审计修复

| # | 发现 | 修复 |
|---|------|------|
| G1 | `_finalize_df` 空 DataFrame KeyError | 提前检查 empty/columns |
| G2 | 9 个死导入 | 全部移除 |
| G4 | 非 TFC 指标使用简化 DSCALE | 统一路由至官方算法 |
| G5 | np.seterr 全局副作用（二次验证）| context manager 无泄漏 |
| G6 | CLAUDE.md 过期路径（SDG7/→data/）| 全部更新 |
| P1 | macOS 大小写不敏感：pop_ssp/pop_SSP 冲突 | 重命名为 `pop_region_ssp*` |

---

## 测试验证

**116 项测试全部通过**（0 失败，3 警告为数值舍入预期的 RuntimeWarning）：

| 测试类别 | 项数 | 验证内容 |
|---------|------|---------|
| 区域守恒 | 96 | 8 指标 × 3 方法 × 4 情景 |
| 单国区域一致性 | 1 | 15 个单国区域三方案必然一致 |
| NaN 检测 | 3 | TFC/电力/TES 无 NaN |
| 负值检测 | 3 | TFC/电力/TES 无非 oth 负值 |
| 份额有界性 | 3 | fossil/renewable/green/elec share ∈ [0,1] |
| API 契约 | 3 | DataFrame 结构、run_indicator、模块导入 |
| DSCALE 边界 | 2 | MAX_TC∈[2040,2200]、beta clipping |
| 数据完整性 | 4 | EXCLUDED_ISO、映射表、路径存在性、文件数 |
| 情景排序 | 1 | SSP245 TFC > SSP126 TFC |

---

## 输出完整性

| 类别 | 应有 | 实有 | 状态 |
|------|------|------|------|
| 无界量降尺度 xlsx | 96 | 96 | ✓ |
| 派生份额 xlsx | 72 | 72 | ✓ |
| 图表 PNG | 76 | 76 | ✓ |
| 日志 txt | 24 | 24 | ✓ |

全部文件时间戳为 2026-06-02（最新重跑），内容一致。

---

## 全局守恒

| 指标 (SSP126, 2100) | Logit | Kaya | DSCALE | 偏差 |
|---------------------|-------|------|--------|------|
| TFC | 560,736,060 | 560,736,060 | 560,736,060 | 0.000 |
| 电力 | 115,046,523 | 115,046,523 | 115,046,523 | 0.000 |
| TES | 738,335,120 | 738,335,120 | 738,335,120 | 0.000 |
| CO2 | −1,629 | −1,629 | −1,629 | 0.000 |

全部指标、全部情景、全部年份的全局偏差均为 0（机器精度内）。

---

## 代码变更摘要

| 文件 | 修改次数 | 变更类型 |
|------|---------|---------|
| `compare/dscale/dscale_official.py` | 8 | A1-A4, E1, E3, G2, G4, G5 |
| `compare/common/downscale.py` | 5 | A6, C1, G1, G2, DSCALE 路由 |
| `compare/common/io.py` | 3 | E2, G2, pop_region fix |
| `compare/common/mapping.py` | 1 | B7 |
| `compare/common/config.py` | 1 | pop_region 路径 |
| `compare/dscale/downscale_tfc.py` | 1 | G2 |
| `compare/run_all.py` | 1 | G2 |
| `compare/compare_results.py` | 3 | 图表坐标轴修复 ×3 |
| `CLAUDE.md` | 3 | 路径、排除实体、代码结构 |
| `README.md` | 1 | 完全重写 |
| `compare/tests/test_conservation.py` | 1 | 新增 116 项测试 |
| 新增数据文件 | 4 | `data/ssp/pop_region_ssp*.xlsx` |

**官方代码**：`DSCALE/downscaler/fit_funcs.py` — 零修改 ✓

---

## 已知局限（8 项，已文档化）

1. Kaya 方法对 28 个极小经济体（基年 TFC < 300 TJ）产生极端值
2. ENLONG 回归使用 2015-2100 年数据，缺少 1990-2010 年历史点
3. Kaya γ=1.0+0.3×log(G_pc/G_world_pc) 中的 0.3 系数和 t_c 取值为校准值
4. EDGAR 数据覆盖：bfa/tcd/mli/mrt 四国在 CO2/工业 CO2 中缺失
5. DSCALE ENSHORT 历史回归仅限 TFC（144 国），其他指标回退 GDP 缩放
6. 仅处理聚合指标，未实现多部门层次化降尺度
7. WORLDBAL CSV 中缺失 São Tomé and Príncipe (STP) 和 Samoa (WSM)
8. macOS 大小写不敏感文件系统：pop 文件重命名已修复

---

## 审计文档索引

```
ROOT:
  AUDIT.md                       ← 综合审计报告
  CLAUDE.md                      ← 项目指令（已更新）
  README.md                      ← 项目概述（已重写）

docs/audit/:
  audit_workflow.md              ← 5 层 25 项审计方案
  round1_A_official_consistency.md   ← A 层初始审计（6 项差异）
  round1_A_reaudit.md            ← A 层修复后验证
  round2_B_data_linkage.md       ← B 层审计+修复
  round3_C_algorithm_params.md   ← C 层审计+修复
  round4_D_E_statistical_codequality.md ← D+E 层审计+修复
  final_audit_summary.md         ← 全部 5 层汇总
  audit_completion.md            ← 修复完成报告
  audit_chain_completion.md      ← 本文件 — 最终链路闭合报告

  audit_report.md                ← 旧版审计（参考）
  data_gaps.md                   ← 数据缺口分析（参考）
  data_inventory.md              ← 数据源清单（参考）
  dscale_comparison.md           ← DSCALE 官方对比（参考）
  method_assessment.md           ← 方法论评审（参考）

compare/tests/:
  test_conservation.py           ← 116 项自动化测试
```

---

## 审计签字

审计链完成，15+1 项修复全部应用并验证，116 项测试通过，全部输出文件校验一致。

审计完成日期：2026-06-02
