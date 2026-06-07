# 代码审计工作流

> 用于指导 AI 对降尺度项目进行系统性、可追溯、可复现的审计。
> 按 5 层 25 项检查点执行，每轮完成后输出审计报告。

## 审计原则

1. **追溯性**：每个数字、参数、公式必须能追溯到文献或官方代码的具体行号
2. **最小修改**：官方代码计算层零修改；适配仅限输入输出
3. **可复现**：任何断言必须附带具体的验证命令
4. **差异透明**：任何与官方的偏差必须显式标记、量化影响、记录原因

---

## A 层：官方代码一致性（DSCALE）— 6 项

审计对象：`compare/dscale/dscale_official.py` vs `DSCALE/downscaler/`

### A1 — fun_max_tc_convergence beta 处理 [高]

- 官方 `Energy_demand_downs_1.py:661`: `BETA.clip(1, np.inf)` — 负 beta 直接变 1
- 我们 `dscale_official.py:73`: `np.clip(np.abs(beta), 1.0, np.inf)` — 负 beta 翻正
- **差异**: beta < -1 时收敛速度不同
- **验证**: 构造 beta ∈ {-2, -0.5, 0, 0.5, 2}，对比两版本 conv_weight 输出
- **修复**: 移除 `np.abs()`

### A2 — ENSHORT alpha 调和 [高]

- 官方 `fun_harmonize_alpha` (utils.py:24640) 将截距调整至基准年匹配
- 我们 `fit_enshort_countries` 未做此调整
- **修复**: 拟合后按 2015 年实际 EI 修正 alpha

### A3 — MAX_TC 动态计算 [中]

- 官方: beta 符号 × beta_enlong 符号 + R² + HIST_START_YEAR 插值
- 我们: 纯 R² 线性插值 (0.95-0.99 → 2040-2200)
- **修复**: 对齐官方逻辑

### A4 — ENSHORT EI [0,1] 封顶 [中]

- 官方 `step1_fun_enshort_ei`: `.clip(0, 1)`
- 我们: 无封顶
- **修复**: ENSHORT 计算后 clip

### A5 — ENLONG 回归数据来源 [低]

- 验证 GCAM 时间序列 (2015-2100) 与官方 IAM snapshot 数据等价性

### A6 — common/downscale.py 旧 DSCALE 收敛 [高]

- `common/downscale.py:351`: 收敛缺少 `** beta` 指数
- **修复**: 添加指数或标记 deprecated

---

## B 层：数据链路 — 7 项

审计对象：`compare/common/io.py`, `config.py`, `mapping.py`

### B1 — 国家名→ISO 匹配完整率 [高]

对 WORLDBAL 158 个 Country/Region 逐一追踪匹配链：
`normalize_name → IEA_VARIANTS → name_to_iso`
输出未命中列表。预期 ≤5 个未命中（聚合区域 + 排除实体）。

### B2 — Chinese Taipei 合并验证 [高]

```python
assert abs(China_2015_TFC_before_merge + Taiwan_2015_TFC - China_2015_TFC_after_merge) < 1.0
```

### B3 — Former Soviet Union / Yugoslavia 排除 [中]

验证两个实体在 1990+ 年份的值为 0，且未出现在任何降尺度输出中。

### B4 — Other non-OECD Americas 处理 [中]

追踪该聚合区域通过人口拆分的完整路径。

### B5 — 单位换算 [高]

- EJ→TJ: ×1,000,000
- thous→million: ÷1,000
- ktoe→TJ: ×41.868
抽样 10 国验证。

### B6 — IEA 新旧数据逐国比对 [高]

2015 年 WORLDBAL CSV vs TFC_IEA.xlsx，列出偏差 >1% 的国家。

### B7 — EXCLUDED_ISO 合理性 [中]

验证 Burkina Faso, Chad, Mali, Mauritania 的排除原因（数据缺失 vs 主动排除）。

---

## C 层：算法参数 — 5 项

审计对象：`compare/common/downscale.py`

### C1 — Kaya γ_c 系数 [高]

`1.0 + 0.3 × log(G_c/G_world)` 中的 0.3。
在 van Vuuren 2007 / Gidden 2019 中溯源。若未找到，标注"校准参数"。
**敏感性分析**: multiplier ∈ {0.1, 0.2, 0.3, 0.5}，对比 Top 20 国 2100 年 TFC。

### C2 — Kaya 收敛年份 [高]

SSP126=2070, SSP245=2085, SSP434=2100, SSP460=2100。
**敏感性分析**: ±10 年。

### C3 — Logit 份额迭代参数 [中]

ε=1e-4, tol=1e-6, max_iter=50。验证收敛行为。

### C4 — DSCALE 动态 MAX_TC 阈值 [中]

R² < 0.95 → 2040, R² > 0.99 → 2200。验证 31 个区域的 MAX_TC 分布。

### C5 — EI 趋势截断 [低]

[-5%, +2%] 年变化率截断。验证实际分布，检查是否有国家被不合理截断。

---

## D 层：统计严谨性 — 6 项

审计对象：全部三方案输出

### D1 — 区域守恒 [高]

所有区域 × 年份 × 情景 × 方法：`|Σ国家 - GCAM区域| < 1e-6 TJ`

### D2 — 全局守恒 [高]

所有年份 × 情景 × 方法：全球偏差 = 0（机器精度内）

### D3 — 份额指标有界性 [高]

所有份额指标（化石、可再生、电气化率、绿电）∈ [0, 1]。

### D4 — 单国区域一致性 [中]

15 个单国区域（China, USA, India...）的三方案结果必须一致。

### D5 — DSCALE 回归质量 [中]

140 国 ENSHORT 回归 R² 分布：min / Q25 / median / Q75 / max。
标记 R² < 0.3 的国家（建议回退 GDP 缩放）。

### D6 — Kaya 极端值检测 [中]

对 Kaya 输出做异常值检测：TFC 增长率 > 20%/年 或 < -10%/年的国家。

---

## E 层：代码质量 — 3 项

### E1 — 重复函数合并 [高]

`_build_iso_info`, `_region_isos`, `_regional_conserve`, `_make_row`, `_finalize_df`
在 `common/downscale.py` 和 `dscale/dscale_official.py` 中重复定义。
→ 从 dscale_official.py 中删除，改为 import。

### E2 — IEA_VARIANTS 重复 [中]

`io.py:39` 和 `io.py:165` 两处定义相同字典。→ 删除旧定义，统一使用 IEA_VARIANTS。

### E3 — np.seterr 审查 [中]

`dscale_official.py:32` 的 `np.seterr(all="ignore")` 可能掩盖真实数值错误。
→ 移除，改为在回归函数中显式处理无效值。

---

## 执行顺序

```
第1轮: A层 (官方一致性) → 修复所有差异
第2轮: B层 (数据链路)   → 逐项验证
第3轮: C层 (算法参数)   → 文献溯源 + 敏感性分析
第4轮: D层 (统计验证)   → 自动化全量检查
第5轮: E层 (代码质量)   → 去重和清理
```

每轮完成输出 `audit/round{N}_{name}.md`，含：
- 通过的检查项（附验证命令和输出）
- 发现的问题（代码位置、根因、修复方案）
- 修复后验证
- 剩余风险

最终 `audit/README.md` 汇总全部审计结论。
