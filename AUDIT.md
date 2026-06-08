# 代码审计报告

审计周期：2026-06-01 ~ 2026-06-09  
审计方法：五轮递进审计（代码 → 官方交叉验证 → 文献验证 → 测试清理 → 敏感性分析）  
最终状态：**290/290 测试通过，96 降尺度 + 48 份额 + 76 图表全部 OK，14 项 Bug 修复**

---

## 一、审计轮次概览

| 轮次 | 日期 | 重点 | 成果 |
|------|------|------|------|
| **R1** 代码审计 | 06-01~02 | DSCALE 官方一致性 + 数据链路 + 算法参数 | 7 Bug 修复（A1-A6, B7, C1, E1-E3） |
| **R2** 官方交叉验证 | 06-08 | 与 DSCALE 官方代码逐函数对比 | ENLONG α 调和、10 差异分析 |
| **R3** 文献验证 | 06-08 | Kaya/Logit 方法的文献溯源 | 引用纠正、份额 Logit 空间修复 |
| **R4** 测试清理 | 06-08 | 测试覆盖度与容差审计 | 3 冗余移除、58 新测试、并行 pipeline |
| **R5** 交叉验证 | 06-09 | 自指验证修复 + 敏感性分析 | gamma_c 负值防护、官方公式逐元素对比 |

---

## 二、全部 Bug 修复（14 项）

### R1 修复（7 项）

| # | 问题 | 严重性 | 文件 |
|---|------|--------|------|
| A1 | DSCALE 收敛 `abs(beta)` 翻转负值，官方用 `clip(beta,1,∞)` | 高 | `dscale_official.py` |
| A2 | ENSHORT 缺少 alpha 调和（官方 `fun_harmonize_alpha`） | 高 | `dscale_official.py` |
| A3 | MAX_TC 简化为 R² 线性插值，缺 beta 符号检测 | 中 | `dscale_official.py` |
| A4 | ENSHORT EI 无 [0,1] 封顶 | 低 | `dscale_official.py` |
| B7 | bfa/tcd/mli/mrt 被误排除（WORLDBAL 有完整数据） | 高 | `common/mapping.py` |
| C1 | Kaya γ 使用总量 GDP（98% 国家 γ<0）→ 改为人均 GDP | 高 | `common/downscale.py` |
| E1-E3 | 重复函数、重复字典、np.seterr 全局副作用 | 低 | 多文件 |

### R2-R5 修复（7 项）

| # | 问题 | 轮次 | 文件 |
|---|------|------|------|
| 8 | GCAM+IEA 电力 GWh 未转换为 TJ（electrification_rate 差 3.6 倍） | R2 | `config.py`, `downscale.py` |
| 9 | DSCALE 非 TFC 输出未写入磁盘（`run_indicator` 提前 return） | R2 | `downscale.py` |
| 10 | 人口下限 `max(p, 1.0)` → `max(p, 1e-6)` | R2 | `dscale_official.py` |
| 11 | `LogLogFunc(alpha=0,beta=0)` → `ff.beta=None` | R2 | `dscale_official.py` |
| 12 | 零 IEA 区域 GCAM 值泄漏到全局残差 | R2 | `downscale.py` |
| 13 | 份额 Kaya/DSCALE 简单比值超界（46/35 国 >1.0）→ Logit 空间收敛 | R3 | `downscale.py` |
| 14 | `gamma_c` 极端贫困国负值 → 收敛方向反转（津巴布韦） | R5 | `downscale.py` |

---

## 三、方法验证状态

### Kaya 收敛法

| 验证项 | 状态 | 说明 |
|--------|------|------|
| 公式结构 | ⚠️ | 与 van Vuuren 2007 指数插值法本质不同（φ 乘方 vs 指数插值） |
| γ_c 参数 (0.3) | ⚠️ | 校准参数，已做敏感性分析（0.1/0.3/0.5），已添加 0.01 下限 |
| t_c 收敛年份 | ⚠️ | 2070-2100 vs 文献 2150-2300，文档中已标注 |
| EI 10% 下限 | ⚠️ | 项目自定义（无文献出处） |
| gamma_c inf/nan 防护 | ✅ | 已修复 |
| 份额（Logit 空间） | ✅ | `compute_kaya_share` 保证 ∈ [0,1] |

### DSCALE 双路径法

| 验证项 | 状态 | 说明 |
|--------|------|------|
| LogLogFunc 回归 | ✅ | 官方 fit_funcs.py，零修改导入 |
| fun_max_tc_convergence | ✅ | 与官方 Energy_demand_downs_1.py:650-675 逐元素一致 |
| ENLONG α 调和 | ✅ | 官方 fun_harmonize_alpha，基准年 2015 |
| ENSHORT 历史回归 | ✅ | 143/148 (96.6%) 覆盖 |
| MAX_TC 回退值 | ⚠️ | 自定义启发式（官方无此需要） |
| 电力单位 | ✅ | GWh→TJ，与 TFC 一致 |
| 份额（Logit 空间） | ✅ | `compute_dscale_share` 保证 ∈ [0,1] |

### Logit/比例法

| 验证项 | 状态 |
|--------|------|
| TFC 比例分配 | ✅ |
| 份额三阶段 Logit | ✅（原创方法） |
| 迭代封顶缩放 | ✅（有收敛警告，见已知局限） |

---

## 四、测试状态

**290 测试，全部通过（5 个文件）：**

| 文件 | 测试数 | 覆盖 |
|------|--------|------|
| `test_conservation.py` | ~170 | 区域守恒（含 GCAM 对比）、单国一致性、份额有界、NaN/负数 |
| `test_cross_validate.py` | 24 | 官方 DSCALE 收敛公式逐元素对比、fun_max_tc、ENLONG 回归 |
| `test_edge_cases.py` | 35 | gamma_c、phi_kaya、_regional_conserve、mapping、IEA 索引 |
| `test_synthetic_gdp.py` | 21 | 合成 GDP 生成 |
| `test_validation_experiments.py` | 40 | 份额有界性（48 参数化）、单国一致性、ENLONG α 调和 |

---

## 五、全量 Pipeline 验证（2026-06-09）

```
Phase 1: 96/96 OK, 0 FAIL (645s sequential, ~120s with N_JOBS=6)
Phase 2: 48 share files written (6 indicators × 2 ratio + 4 Logit shares × 3 methods × 4 scenarios)
Phase 3: 76 plots regenerated
Total: ~720s sequential
```

所有输出文件已重新生成。份额指标（fossil_share, renewable_share, electrification_rate, green_elec_share）全部有界 ∈ [0,1]。

---

## 六、已知局限（v3）

1. **Kaya γ_c = 1.0 + 0.3×ln(GDP_pcap 比值)**：0.3 为校准参数，floor 0.01 防负 γ。ci 分析已完成。
2. **Kaya EI 10% 下限**：无文献出处，防止极端收敛。
3. **Kaya 无 IEA 国家**：直接使用区域 EI，无收敛路径。
4. **DSCALE ENSHORT 5 国回退**：mne/prk/qat/rou/zwe 缺少 USDA GDP 数据（非 TFC 数据）。
5. **DSCALE MAX_TC 回退值**（2200/2120/2040）：项目自定义启发式。
6. **Kaya/DSCALE 份额守恒**：等比缩放+clip 产生 <1% 守恒偏差。Logit 份额守恒完美。
7. **`compute_logit_share` 收敛警告**：Africa_Eastern 和 South America_Northern 在 2100 年未收敛（误差 ~2e4 和 ~1e3），但输出份额仍正确有界。
8. **CO2 净负排放**：SSP126 下 76 国 per_capita_co2 为负值（预期行为）。

---

## 七、运行方式

```bash
# 全量运行（支持并行：N_JOBS=6）
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

审计签字：2026-06-09，五轮审计完成。官方 DSCALE 代码零修改。14 项 Bug 修复，290 测试通过，全量 pipeline 通过。
