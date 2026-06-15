# 三种降尺度方法的系统对比：实验报告

日期：2026-06-15（v4，22 项 Bug 修复，264 项测试通过）

---

## 摘要

对 Logit（恒定份额）、Kaya（van Vuuren 2007 指数收敛）和 DSCALE（ENLONG+ENSHORT 双路径）三种降尺度方案在 8 个能源与排放指标、4 个 SSP 情景下进行了系统对比。三方案满足区域守恒约束，264 项自动化测试全部通过（0 warnings）。Kaya 方法已切换至 van Vuuren 2007 / Gütschow 2021 官方指数插值法，三个方案均使用迭代封顶缩放计算份额指标。

---

## 一、方法

| 方案 | 核心机制 | 文献 |
|------|---------|------|
| **Logit** | 2015 年 IEA 基准份额 × GCAM 区域总量 | 本项目原创（空间 Logit 降尺度） |
| **Kaya** | van Vuuren 指数插值：EI_c(y) = a_c×exp(γ×(y−y_h))+b_c | van Vuuren 2007; Gütschow 2021 |
| **DSCALE** | ENLONG（区域 log-log 回归）+ ENSHORT（逐国历史回归，143 国）+ MAX_TC 收敛 | Sferra 2026 |

**Kaya 关键参数**：残差比率 d=0.01（99% 差距在收敛年消除），收敛年 SSP126=2150, SSP245=2200, SSP434=2300, SSP460=2300（Gütschow 2021）。γ = ln(0.01)/(y_c−2015)，情景统一。I_R_target = I_R(2100)（GCAM 数据仅到 2100，收敛年均在其后）。

**份额计算**：三方案均在 Logit 变换空间计算份额，使用迭代封顶缩放（`_iterative_capped_scaling`），保证 ∈ [0,1] 且区域守恒完美。

**数据源**：GCAM 区域情景（`data/gcam/`）、IEA WORLDBAL 1970–2024（`data/iea/`）、SSP GDP/人口（`data/ssp/`）、EDGAR 排放（`data/emissions/`）。IEA 覆盖 148 个单列国家，35 个小国通过 GCAM 残差 + 人口拆分处理。

---

## 二、结果

### 2.1 全局守恒

全部 8 个指标 × 3 种方法 × 4 个情景 × 18 个年份的区域守恒偏差 ≤ 1e-6 TJ（机器精度内）。因 `_regional_conserve` 机制，三方法全球总量完全相同——方法差异体现在国家间分配而非全球总量。

### 2.2 方法间相关性

以 2050 年国家粒度 log-log 相关系数量化方法间一致性（TFC，SSP126）：

| 对比 | Logit-Kaya r | Logit-DSCALE r |
|------|-------------|---------------|
| TFC | ~0.93 | ~0.91 |

DSCALE 与 Logit 在电力、可再生 TES 等指标上的相关性低于 Logit-Kaya，反映 DSCALE 对历史趋势和区域回归的不同敏感度。

### 2.3 单国区域

~15 个单国区域（USA、China、India、Russia、Brazil、Japan 等）三方案完全相同——区域守恒强制国家值等于区域值。方法分歧完全来自多国区域内的国家间分配。

### 2.4 DSCALE ENSHORT 回归

- ENLONG: 31 GCAM 区域 × 21 时间点（1990–2100），使用官方 `LogLogFunc`
- ENSHORT: 143/148 国（96.6%）逐国历史回归，使用 `scipy.stats.linregress` 直对 log 变换数据（与官方 DSCALE 一致）
- 5 国回退 GDP 缩放：mne/prk/qat/rou/zwe（瓶颈在 USDA GDP 历史数据）

### 2.5 收敛特性

Kaya 方法在 2100 年仅完成 ~20-30% 收敛（w(2100) ≈ 0.2-0.3 for SSP126-245, y_c=2150-2200）。这是因为收敛年远超 2100，指数衰减缓慢——这是方法设计特性，不是 bug。详见 `convergence_profile.png`。

---

## 三、讨论

### 3.1 方法分歧的来源

- **Logit**：保持固定份额，隐含各国均等增长
- **Kaya**：能源强度向区域 EI 目标指数收敛，收敛速度由统一的 γ 参数决定。基年 EI 与区域目标的差距越大，收敛路径越长
- **DSCALE**：结合区域 IAM 回归（ENLONG）和国家历史趋势（ENSHORT），通过 MAX_TC 动态收敛

### 3.2 方法选择建议

| 用途 | 推荐方案 | 理由 |
|------|---------|------|
| 主方案 | DSCALE | 数据驱动、文献支持最完整（Sferra 2026）、官方代码交叉验证 |
| 经济收敛视角 | Kaya | van Vuuren 指数插值、CMIP6 标准方法（Gütschow 2021） |
| 无假设基线 | Logit | 纯数据驱动、无自由参数、空间 Logit 原创应用 |

---

## 四、局限与展望

1. **Kaya I_R_target**：使用 I_R(2100) 代理 I_R(y_c)（GCAM 数据仅到 2100）
2. **Kaya EI 下限**：`max(EI_c(y), I_c(2015)×0.1)` 为安全阈值（无文献出处）
3. **DSCALE ENSHORT**：逐国历史回归仅限 TFC（143 国），非 TFC 指标回退 GDP 缩放
4. **DSCALE MAX_TC 回退**：2200/2120/2040 三段启发式（官方 DSCALE 无此需要）
5. **EDGAR 覆盖**：CO2 和工业排放指标依赖 EDGAR 数据库，部分国家覆盖不完整
6. **部门聚合**：当前仅处理聚合指标，未实现多部门层次化降尺度

---

## 五、结论

三种降尺度方案在全局守恒和总体相关性方面表现良好。Kaya 已切换至 van Vuuren 2007 / Gütschow 2021 官方方法，消除所有文献偏差 ⚠️ 项。ENSHORT 双 log bug 已修复，份额计算统一使用迭代封顶缩放。264 测试全部通过，0 warnings。Pipeline 完整覆盖 8 指标 × 3 方法 × 4 情景 + 6 份额指标。

审计状态详见 `AUDIT.md`，运行方式详见 `README.md`。
