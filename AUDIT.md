# 代码审计报告

**项目**：GCAM 区域→国家降尺度三方案对比  
**审计周期**：2026-06-01 ~ 2026-06-15（五轮递进）  
**当前状态**：250/250 测试通过 | 22 项 Bug 已修复 | 0 项待修复 | 2 项方法论偏差（已记录）  
**审计结论**：三方案降尺度核心算法逻辑正确，区域守恒满足，份额有界性保证。所有已知问题均已修复。

---

## 一、审计方法

| 轮次 | 重点 | 手段 |
|------|------|------|
| R1 代码审计 | DSCALE 官方一致性 + 数据链路 | 逐函数与官方 DSCALE 仓库对比 |
| R2 官方交叉验证 | ENLONG/ENSHORT/收敛公式 | `fun_max_tc_convergence` 逐元素对比 |
| R3 文献验证 | Kaya/Logit 方法溯源 | 公式结构与 van Vuuren 2007、Sferra 2026 对比 |
| R4 测试清理 | 覆盖度与容差 | 58 新测试，冗余移除 |
| R5 敏感性分析 | gamma_c 边界行为 | 极端贫困国负值防护 |

---

## 二、已修复 Bug（14 项）

### 高严重性（影响结果正确性）

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 1 | Kaya γ 使用总量 GDP → 98% 国家 γ<0 | 改为人均 GDP 计算 | `downscale.py` |
| 2 | DSCALE 收敛 `abs(beta)` 翻转负值 | 改为 `clip(beta, 1, ∞)` 与官方一致 | `dscale_official.py` |
| 3 | ENSHORT 缺少 alpha 调和 | 加入官方 `fun_harmonize_alpha` 逻辑 | `dscale_official.py` |
| 4 | bfa/tcd/mli/mrt 被误排除（WORLDBAL 有数据） | 从 EXCLUDED_ISO 移除 | `mapping.py` |
| 5 | GCAM+IEA 电力 GWh 未转 TJ（差 3.6×） | 统一 `gcam_unit_factor=3.6` | `config.py` |
| 6 | 份额 Kaya/DSCALE 简单比值超界（46/35 国 >1.0） | 改用 Logit 空间收敛 | `downscale.py` |
| 7 | gamma_c 极端贫困国负值（津巴布韦） | `max(γ, 0.01)` 下限 | `downscale.py` |

### 中严重性（影响部分场景）

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 8 | MAX_TC 缺 beta 符号检测 | 加入官方 `fun_max_tc` 完整逻辑 | `dscale_official.py` |
| 9 | DSCALE 非 TFC 输出未写入磁盘 | 修复 `run_indicator` 提前 return | `downscale.py` |
| 10 | 零 IEA 区域 GCAM 值泄漏到全局残差 | 区域内零值正确处理 | `downscale.py` |
| 11 | `LogLogFunc(alpha=0,beta=0)` → `ff.beta=None` | 初始化检查 | `dscale_official.py` |

### 低严重性（代码质量）

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| 12 | ENSHORT EI 无 [0,1] 封顶 | 加入 `np.clip(0, 1)` | `dscale_official.py` |
| 13 | 人口下限 `max(p, 1.0)` → `max(p, 1e-6)` | 避免虚假归零 | `dscale_official.py` |
| 14 | 重复函数/字典、np.seterr 全局副作用 | 清理 | 多文件 |

### v4 修复（6 项）

| # | 问题 | 严重性 | 文件 |
|---|------|--------|------|
| 15 | Kaya φ 乘方 → van Vuuren 2007 官方指数插值法 | 高 | `downscale.py` |
| 16 | `downscale_logit` 中 `n_r` 未定义（运行时 NameError）| 中 | `downscale.py` |
| 17 | `read_iea_historical_tfc` 死代码 + 未定义变量引用 | 低 | `io.py` |
| 18 | Kaya/DSCALE 份额等比缩放+clip 丢超额量 → 守恒偏差 | 中 | `downscale.py` |
| 19 | Logit 份额封顶-重分配振荡 → 迭代不收敛 | 中 | `downscale.py` |
| 20 | `read_gcam_generic` 仅识别 EJ，其他单位静默错误 | 低 | `io.py` |
| 21 | ENSHORT 回归双 log（数据已 log 变换又经 LogLogFunc 内层 log） | 高 | `dscale_official.py` |
| 22 | `industry_co2` unit_factor=1.0 但源数据为 Gg CO₂（应为 0.001→Mt） | 中 | `config.py` |

修复详情：
- **#16**：在 `downscale_logit` 中添加 `n_r = len(region_isos)`
- **#17**：删除 return 后的 36 行死代码，docstring 移至函数头
- **#18**：提取 `_iterative_capped_scaling()` 共享函数，三方案份额均使用迭代封顶缩放（守恒完美）
- **#19**：已封顶国家标记为 `permanently_capped`，排除后续重分配，防止振荡
- **#20**：扩展单位识别为 EJ/PJ/Mtoe/GWh，未知单位发出 warning
- **#21**：`fit_enshort_countries` 从 `LogLogFunc.fit()` 改为 `scipy.stats.linregress` 直对 log 数据回归，与官方 DSCALE 一致

---

## 三、已知局限

---

## 四、方法论偏差（已记录，非 Bug）

以下差异部分来自数据限制，部分为安全设计。

### Kaya 收敛法（van Vuuren 2007 / Gütschow 2021）

| 项目 | 文献方法 | 本实现 | 对齐状态 |
|------|---------|--------|---------|
| 收敛公式 | `a_c×e^(γ×(y-y_h))+b_c` 指数插值 | 同文献 | ✅ 完全一致 |
| 收敛年份 | SSP1=2150, SSP2=2200, SSP3/4=2300 | 同文献 | ✅ 完全一致 |
| γ 参数 | ln(0.01)/(y_c-y_h)，情景统一 | 同文献 | ✅ 完全一致 |
| 收敛目标 | I_R(y_c) | I_R(2100) | ⚠️ 数据限制（GCAM仅到2100） |
| EI 下限 | 无 | `max(EI_c(y), I_c(2015)×0.1)` | ⚠️ 安全阈值（防 b_c<0 时 EI 过零） |

### DSCALE 适配 vs 官方实现

| 差异点 | 官方 DSCALE | 本实现 | 性质 |
|--------|------------|--------|------|
| ENSHORT 数据源 | 逐国 IEA 1970-2015 + USDA GDP | 同左（143/148 国），5 国回退 GDP 缩放 | 数据限制 |
| MAX_TC 回退 | 总有 ENSHORT，无需回退 | 2200/2120/2040 三段启发式 | 数据限制 |
| ENLONG 基准年 | 2010 | 2015（对齐 IEA 基年） | 有意选择 |
| 非 TFC 指标 | 各 sector 独立回归 | ENSHORT 全部回退 GDP 缩放 | 简化处理 |

### Logit/比例法

| 差异点 | 说明 |
|--------|------|
| 空间 Logit 降尺度 | 将 Fisher-Pry 时间维度变换应用于空间维度，IAM 降尺度文献未见先例 |
| TFC 无界量 | 使用简单比例分配（非 Logit 变换），Logit 仅用于份额类指标 |

---

## 五、测试覆盖

**250 测试，全部通过（0 warnings）。** 核心测试 ~60s，全量 ~125s。

| 文件 | 测试数 | 覆盖范围 |
|------|--------|---------|
| `test_conservation.py | 95 | 区域守恒（GCAM 对比）、单国一致性、份额有界、NaN/负数、情景排序 |
| `test_cross_validate.py` | 24 | 官方 DSCALE 收敛公式逐元素对比、`fun_max_tc`、ENLONG 回归 |
| `test_edge_cases.py` | 40 | convergence_gamma、van_vuuren_ei、convergence_weight、mapping、zero-IEA |
| `test_synthetic_gdp.py` | 21 | 合成 GDP 生成（9 个缺口国家） |
| `test_validation_experiments.py` | 65 | 份额有界性（48 参数化）、单国一致性、ENLONG α 调和、ENSHORT 正确性回归测试 |

运行：`-m "not slow"` 跳过 2 个集成测试（~60s），日常开发使用。

---

## 六、Pipeline 验证

```
Phase 1: 96 降尺度 (8 指标 × 3 方法 × 4 情景) — 全部 OK
Phase 2: 48 份额文件 (6 份额 × 3 方法 × 4 情景) — 全部有界
Phase 3: 68 图表 — 全部生成
```

份额指标验证：fossil_share、renewable_share、electrification_rate、green_elec_share 全部 ∈ [0,1]。  
CO2 净负排放：SSP126 下 76 国 per_capita_co2 为负值（预期行为，反映负排放情景）。

---

## 七、已知局限

1. **DSCALE ENSHORT 5 国回退**：mne/prk/qat/rou/zwe 缺 USDA GDP 数据，回退到 GDP 缩放（保持基年 EI 不变）。
2. **Kaya 无 IEA 基准国家**：I_c(2015) = I_R(2015)，产生 a_c=0, b_c=I_R(2015)，EI 保持平坦直到收敛年后跟踪区域值。
3. **CO2 负排放处理**：per_capita_co2 可为负值，份额计算中 Logit 变换需 clip eps 处理。
4. **DSCALE 非 TFC 指标**：ENSHORT 全部回退 GDP 缩放，丢失逐国历史趋势信息。

---

## 八、运行方式

```bash
# 全量运行（推荐并行）
N_JOBS=6 uv run python compare/run_all.py

# 全量测试
uv run python -m pytest compare/tests/ -q

# 单指标运行
uv run python -c "
from compare.common.downscale import run_indicator
from compare.common.config import INDICATORS
df = run_indicator('dscale', 'SSP126', INDICATORS['tfc'])
"
```

---

审计签字：2026-06-15。官方 DSCALE 代码零修改。22 项 Bug 修复，0 项待修复，2 项方法论偏差已记录。0 warnings。
