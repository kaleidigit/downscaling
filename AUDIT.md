# 代码审计报告

审计日期：2026-06-01 ~ 2026-06-02
审计方法：5 层 25 项系统审计 + 补充深度审计 + 全量修复 + 重跑验证

---

## 一、项目概况

本项目将 GCAM 区域级气候情景数据降尺度到国家粒度，在 `compare/` 下并行实现三种方案：

| 方案 | 核心思想 | 关键文献 |
|------|---------|---------|
| Logit | 基年 IEA 份额 × 区域总量（恒定比例）| 当前项目 |
| Kaya | 能源强度按人均 GDP 条件收敛到 GCAM 区域值 | van Vuuren 2007; Gidden 2019 |
| DSCALE | ENLONG（区域 log-log 回归）+ ENSHORT（逐国历史回归）+ MAX_TC 收敛 | Sferra 2026 |

覆盖 8 个指标（TFC、电力、TES、化石 TES、可再生 TES、绿色电力、工业 CO2、CO2 排放）× 4 个 SSP 情景（SSP126/245/434/460）。

---

## 二、审计方法

按 5 层 25 项检查点执行（见 `docs/audit/audit_workflow.md`）：

| 层级 | 审计对象 | 项数 | 核心问题 |
|------|---------|------|---------|
| A | DSCALE 官方代码一致性 | 6 | `dscale_official.py` vs `DSCALE/downscaler/` |
| B | 数据链路 | 7 | WORLDBAL 匹配率、单位换算、合并验证 |
| C | 算法参数 | 5 | γ 系数溯源、收敛年份、迭代参数 |
| D | 统计严谨性 | 6 | 守恒性、有界性、极端值检测 |
| E | 代码质量 | 3 | 重复函数、死代码、数值安全 |

审计原则：每一步可追溯（文献/官方代码行号）、官方计算层零修改、差异透明量化。

---

## 三、发现与修复（15 项）

### A 层 — 官方 DSCALE 一致性

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| A1 | `np.abs(beta)` 翻转负值，官方直接 clip | 移除 `np.abs()` | `dscale_official.py` |
| A2 | ENSHORT 缺少 alpha 调和（官方 `fun_harmonize_alpha`） | 拟合后按 2015 基准年修正 alpha | `dscale_official.py` |
| A3 | MAX_TC 简化为 R² 线性插值 | 实现官方 `fun_max_tc()`（beta 符号检测 + R²×duration）| `dscale_official.py` |
| A4 | ENSHORT EI 无 [0,1] 封顶 | 添加 `.clip(0, 1)` | `dscale_official.py` |
| A6 | 旧版 DSCALE 收敛缺少 β 指数 | 添加 `** max(abs(beta), 1.0)` | `common/downscale.py` |

### B 层 — 数据链路

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| B7 | bfa/tcd/mli/mrt 被排除但 WORLDBAL 有完整数据 | 从 EXCLUDED_ISO 移除（9→5）| `common/mapping.py` |

### C 层 — 算法参数

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| C1 | Kaya γ 公式使用总量 GDP（98% 国家 γ<0，收敛反转）| 改用人均 GDP | `common/downscale.py` |

### E 层 — 代码质量

| # | 问题 | 修复 | 文件 |
|---|------|------|------|
| E1 | 5 个函数在 `common/downscale.py` 和 `dscale_official.py` 重复 | 删除 dscale 副本，改为 import | 双文件 |
| E2 | IEA_VARIANTS 字典重复定义（io.py 两处）| 统一至模块顶部 | `common/io.py` |
| E3 | `np.seterr(all="ignore")` 全局副作用 | 改为 context manager | `dscale_official.py` |

### 补充审计修复

| 缺口 | 问题 | 修复 |
|------|------|------|
| Gap 1 | `_finalize_df` 空 DataFrame 崩溃 | 提前检查 `df_out.empty` |
| Gap 2 | 9 个死导入 | 全部清理 |
| Gap 4 | 非 TFC 指标使用简化 DSCALE | 统一路由至官方算法 |
| Gap 5 | np.seterr 全局副作用（二次验证）| 确认 context manager 无泄漏 |
| Gap 6 | CLAUDE.md 过期路径 | 更新至 data/ 目录 |

---

## 四、全量重跑验证（2026-06-02）

```
Phase 1: 96 downscaling runs — 96 OK / 0 FAIL (196.8s)
Phase 2: 72 derived shares — all OK
Phase 3: 76 PNG charts regenerated
Total: 228.6s
```

### 关键指标

| 验证项 | 结果 |
|--------|------|
| TFC 全局守恒（3 方法 × 4 情景）| ✅ 偏差 0.000000 TJ |
| 电力全局守恒 | ✅ 偏差 0.000000 |
| CO2 全局守恒 | ⚠️ 微量残差（舍入，~1e-9 量级）|
| 单国区域一致性（15 国）| ✅ 三方案完全相同 |
| 非 TFC 指标 DSCALE 统一 | ✅ 全部 8 指标使用官方算法 |
| 新增 4 国（bfa/tcd/mli/mrt）| ✅ TFC 输出中包含；CO2 缺失（EDGAR 限制）|
| 负值检查 | ✅ 仅 oth 行 ~1e-6 TJ 舍入误差 |
| CO2 负值 | ✅ 预期行为（SSP126 净负排放情景）|
| Kaya 极端值（C1 修复后）| ⚠️ SSP126: 28 小国（基年 <300 TJ）CAGR < -10% |

---

## 五、已知局限

论文中应标注以下 6 点：

1. **Kaya 方法对小经济体的适用性**：28 个基年 TFC < 300 TJ 的国家在收敛公式下 TFC→0，建议在论文方法讨论中标注
2. **ENLONG 回归数据范围**：使用 2015-2100 年数据（18 点），官方 DSCALE 使用 1990-2100（21 点）。影响微小（<1% β 差异），在论文中注明
3. **Kaya 参数来源**：γ=1.0+0.3×log(G_pc/G_world_pc) 中的 0.3 系数为校准参数，t_c 取值（SSP126→2070 等）为推断值，均无文献出处。建议标注并做敏感性分析
4. **EDGAR 数据覆盖**：bfa/tcd/mli/mrt 四国在 CO2 和工业 CO2 指标中缺失（EDGAR 源文件无数据），TFC 中已包含
5. **DSCALE ENSHORT 历史数据**：仅 TFC 有 1970-2015 IEA WORLDBAL 历史回归数据，其他指标使用 GDP 缩放回退
6. **DSCALE 部门聚合**：本项目仅处理聚合指标（如总 TFC、总电力），未实现官方 DSCALE 的多部门层次化降尺度

---

## 六、项目结构（审计后）

```
downscaling/
├── CLAUDE.md                     # 项目指令与数据规格
├── AUDIT.md                      # 本文件
├── README.md
├── pyproject.toml                # uv 环境配置
├── data/                         # 输入数据
│   ├── gcam/                     # GCAM 区域输出
│   ├── iea/                      # IEA WORLDBAL 1970-2024
│   ├── ssp/                      # SSP GDP/人口
│   ├── emissions/                # EDGAR 排放数据
│   └── mapping/                  # 国家-区域映射
├── compare/                      # ★ 三方案对比
│   ├── common/                   # 共享模块 (config, io, mapping, downscale, conservation)
│   ├── logit/                    # 方案 C: 恒定份额
│   ├── kaya/                     # 方案 A: 条件收敛
│   ├── dscale/                   # 方案 B: 官方 DSCALE 适配
│   ├── output/                   # 所有输出 (xlsx + txt + png)
│   ├── run_all.py                # 一键运行
│   └── compare_results.py        # 对比可视化
├── DSCALE/                       # 官方 DSCALE 仓库（零修改）
├── archive/                      # 归档文件
│   ├── old_docs/                 # 旧文档
│   ├── old_logs/                 # 旧日志
│   └── old_output_docs/          # 旧输出文档
└── docs/audit/                   # 详细审计报告（14 份）
```

---

## 七、运行方式

```bash
# 全量运行（8 指标 × 3 方法 × 4 情景 + 份额 + 图表）
python compare/run_all.py

# 单指标运行
python -c "
from compare.common.downscale import run_indicator
from compare.common.config import INDICATORS
df = run_indicator('dscale', 'SSP126', INDICATORS['tfc'])
"

# 仅 TFC（含 ENSHORT 历史回归）
python -c "
from compare.dscale.downscale_tfc import downscale_tfc
df = downscale_tfc('SSP126')
"
```

---

审计签字：2026-06-02，全部 5 层 25 项审计 + 补充审计完成，15 项修复应用，全量重跑通过。官方 DSCALE 代码零修改。
