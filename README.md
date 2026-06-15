# GCAM 区域→国家降尺度

将 GCAM（Global Change Analysis Model）区域级气候与能源情景数据（32 区域）降尺度到国家粒度（~180 国），支持 SDG 指标评估。

三方案并行对比，覆盖 8 个指标 × 4 个 SSP 情景。

## 数据源

### 核心输入

| 数据 | 来源 | 路径 | 格式 |
|------|------|------|------|
| **GCAM 区域情景** | GCAM 模型输出 | `data/gcam/` | xlsx, 32 区域 × 5 年步长 (1990-2100) |
| **IEA 能源平衡** | OECD IEA WORLDBAL | `data/iea/WORLDBAL_1970_2024.csv` | CSV, 1970-2024, ~180 国, SDMX 格式 |
| **SSP GDP** | IIASA SSP Database v9 | `data/ssp/GDP_{scenario}.xlsx` | xlsx, 172 国, billion US\$2005/yr |
| **SSP 人口** | IIASA-WiC POP | `data/ssp/pop_{scenario}.xlsx` | xlsx, ~190 国, million |
| **USDA 历史 GDP** | USDA ERS | `data/ssp/USDA_GDP_MER.csv` | CSV, 189 国, 1969-2017, billion 2010USD |
| **UN 历史人口** | UN Population Division | `data/ssp/UN_popTot.csv` | CSV, ~200 国, 1950-2020, thousands |
| **EDGAR 排放** | JRC EDGAR v8.0 | `data/emissions/` | xlsx, CO2 和工业排放 |
| **国家-区域映射** | GCAM 社区 | `data/mapping/gcam_country_region1120.xlsx` | 180 国 → 32 GCAM 区域 |

### 数据预处理

1. **台湾合并**：GCAM 区域 "Taiwan" 合并到 "China"；ISO `twn` → `chn`；IEA WORLDBAL 中 "Chinese Taipei" 缓冲并累加到 "China Region"
2. **排除实体**：Greenland (`grl`)、Palestinian Authority (`pse`)、Gibraltar (`gib`)、Kosovo (`xkx`)、South Sudan (`ssd`) — 共 5 个非主权或数据缺失实体
3. **合成 GDP**：9 个缺失 IIASA SSP GDP 的国家（阿富汗、安哥拉、阿尔巴尼亚、阿联酋、缅甸、黑山、新喀里多尼亚、朝鲜、卡塔尔）通过区域人均 GDP 增长 × 国家人口生成
4. **IEA Other 区域处理**：35 个小国在 IEA 中以 "Other non-OECD Africa/Americas/Asia Oceania" 聚合报告，通过 GCAM 区域残差（GCAM 区域总量 − 区域内 IEA 单列国家之和）按人口拆分到各成员国

### 单位转换

| 数据 | 原始单位 | 内部单位 | 转换 |
|------|---------|---------|------|
| GCAM TFC、TES 等 | EJ | **TJ** | ×1,000,000 |
| GCAM 电力 | GWh | **TJ** | ×3.6 |
| IEA 全部数据 | TJ 或 GWh | **TJ** | GWh→TJ ×3.6 |
| SSP 区域人口 | thous | **million** | ÷1,000 |
| SSP GDP（各国别、区域） | 各种 | 仅用比值 | 无需转换 |

所有内部计算以 **TJ** 为统一能量单位。GDP 仅用于比值计算，基准年差异（国家 GDP: 2005\$, 区域 GDP: 1990\$）不影响力比结果。

---

## 三种降尺度方案

### 共享符号

| 符号 | 含义 |
|------|------|
| `E_c^IEA` | 国家 c 的 IEA 2015 基准值（TJ） |
| `E_R(t)` | GCAM 区域 R 在年份 t 的总量（TJ） |
| `G_c(t)` | 国家 c 的 GDP（billion US\$2005/yr） |
| `P_c(t)` | 国家 c 的人口（million） |
| `G_R(t)` | 区域 R 的 GDP 总和 |
| `P_R(t)` | 区域 R 的人口总和 |
| `I_c(t)` | 能源强度 `E_c(t) / G_c(t)` |
| `I_R(t)` | 区域能源强度 `E_R(t) / G_R(t)` |
| `γ` | 收敛衰减率 = ln(d)/(y_c−y_h) |
| `d` | 残差比率 = 0.01 |
| `y_c` | 收敛完成年份 |

---

### 方案 A：Kaya 收敛法（`kaya`）

**核心思想**：国家能源强度通过指数插值收敛到区域能源强度。基于 van Vuuren 2007 / Gütschow 2021 标准方法。

#### 计算步骤

**Step 1 — 基年能源强度**
```
I_c(2015) = E_c^IEA / G_c(2015)
I_R(t)    = E_R(t) / G_R(t)
```

**Step 2 — van Vuuren 指数插值收敛**
```
d = 0.01                                     # 残差比率，99%差距在收敛年消除 (Gütschow 2021)
γ = ln(d) / (y_c − y_h)                      # 负值，情景统一的指数衰减率
y_h = 2015                                    # 历史基年
y_c = {SSP126: 2150, SSP245: 2200, SSP434: 2300, SSP460: 2300}

EI_c(y) = a_c × exp(γ×(y−y_h)) + b_c         # 指数插值
```
边界条件：EI_c(y_h) = I_c(2015)，EI_c(y_c) ≈ I_R_target（残差 d=1%）
```
a_c = (I_c(2015) − I_R_target) / (1 − d)
b_c = I_c(2015) − a_c
I_R_target = I_R(2100)                        # GCAM仅到2100，收敛年均在其后
```
- 收敛年后 (y ≥ y_c): EI_c(y) = I_R(y)
- EI 下限: max(EI_c(y), 0), max(EI_c(y), I_c(2015) × 0.1)
- 无 IEA 基准国家: I_c(2015) = I_R(2015)，则 a_c=0, EI 保持平坦

**Step 3 — 能源消费**
```
E_c_proj(t) = EI_c(t) × G_c(t)
```

**Step 4 — 区域守恒校准**
```
E_c_final(t) = [E_c_proj(t) / Σ_k E_k_proj(t)] × E_R(t)    (k ∈ 区域 R)
```

**份额指标处理**：份额类指标在 Logit 变换空间应用收敛权重 w(t) = 1 − exp(γ×(t−y_h))，天然保证 ∈ [0,1]。

#### 关键参数

| 参数 | 值 | 来源 |
|------|---|------|
| d (残差比率) | 0.01 | Gütschow 2021 |
| y_c (收敛年) | 2150/2200/2300/2300 | Gütschow 2021 |
| γ (衰减率) | ln(0.01)/(y_c−2015) | van Vuuren 2007 |
| I_R_target | I_R(2100) | 数据限制（GCAM仅到2100）|
| EI 下限 | 基年 EI × 0.1 | 安全阈值 |

---

### 方案 B：DSCALE 双路径法（`dscale`）

**核心思想**：将国家历史趋势（ENSHORT）与 IAM 长期区域路径（ENLONG）通过动态收敛年份混合。直接调用官方 DSCALE 仓库中的 `LogLogFunc`（零修改）。

#### 计算步骤

**Step 1 — ENLONG（长期投影）：区域 log-log 回归**

对每个 GCAM 区域，拟合如下回归（使用 1990, 2005, 2010, 2015-2100 年数据）：
```
ln(TFC_region / GDP_region) = α + β × ln(GDP_region / POP_region)
```
使用官方 `LogLogFunc` 类（`scipy.stats.linregress`）。

**Alpha 调和**：调整 α 使回归线精确通过基年（2015）观测点：
```
α += ln(EI_2015_obs) − (α + β × ln(GDP_pcap_2015_obs))
```

**ENLONG 投影**：将回归系数应用于区域内每个国家：
```
ENLONG_c(t) = exp(α + β × ln(GDP_c(t) / POP_c(t))) × GDP_c(t)
```

**Step 2 — ENSHORT（短期投影）：逐国历史回归**

数据源：IEA WORLDBAL TFC (1970-2015) + USDA GDP (1969-2017) + UN Population (1950-2020)

对每个国家，拟合历史 log-log 回归：
```
ln(TFC_c / GDP_c) = α + β × ln(GDP_c / POP_c)
```
- 需要 ≥5 个对齐数据点
- Alpha 调和至基年观测值
- EI 封顶至 [0, 1]
- **覆盖率**：143/148 国（96.6%）通过；5 国回退（瓶颈在 USDA GDP 数据）

```
ENSHORT_c(t) = EI_c(t) × GDP_c(t)
```

回退优先级：(a) 历史回归（≥5 点），(b) 2015-2020 IEA 趋势外推，(c) GDP 缩放（恒定 EI）

**Step 3 — MAX_TC 动态收敛**

`MAX_TC`（收敛完成年份，范围 2040-2200）基于 ENSHORT 回归质量动态计算：
- β_short × β_long < 0（符号冲突）→ MAX_TC = 2040（快速收敛）
- 同符号 → `MAX_TC = 2040 + (2200−2040) × (R²×duration − x_min) / (x_max − x_min)`
- 无 ENSHORT 回归时回退：ENLONG R²>0.99→2200, R²>0.95→2120, 否则→2040

**Step 4 — 收敛混合**

来自官方 `Energy_demand_downs_1.py:650-675`（已验证逐元素一致）：
```
CONV_WEIGHT = clip((t − MAX_TC) / (2010 − MAX_TC), 0, 1) ^ clip(β, 1, ∞)
E_c(t) = ENSHORT × CONV_WEIGHT + ENLONG_RATIO × (1 − CONV_WEIGHT)
```
- `CONV_WEIGHT = 1` 在 t=2010（纯 ENSHORT）
- `CONV_WEIGHT = 0` 在 t=MAX_TC（纯 ENLONG）
- β 指数控制收敛曲线形状（`clip(β, 1, ∞)`，负 β→1 线性收敛）

**Step 5 — 区域守恒校准**（同方案 A Step 6）

**份额指标处理**：DSCALE 收敛权重应用于 Logit 空间，保证 ∈ [0,1]。

#### 关键参数

| 参数 | 值 |
|------|---|
| MAX_TC 范围 | 2040-2200（动态） |
| 收敛基年 | 2010 |
| ENLONG 回归年份 | 1990, 2005, 2010, 2015-2100 |
| Alpha 调和基准年 | 2015（官方用 2010） |
| ENSHORT 最少数据点 | 5 |
| 回退 MAX_TC | 2200 / 2120 / 2040（项目自定义） |

---

### 方案 C：Logit/比例法（`logit`）

**核心思想**：TFC 按 2015 IEA 份额分配区域总量（无收敛动力学）。份额类指标使用三阶段 Logit 空间变换。

#### TFC 计算（无界量）

```
share_c = E_c^IEA / Σ_k E_k^IEA          (k ∈ 区域 R)
E_c(t) = share_c × E_R(t)                (恒定份额，∀t)
```
区域内 IEA 单列国家不覆盖的部分归入 Other 区域，按人口拆分。

#### 份额指标计算（有界量 ∈ [0,1]）

**阶段 1 — Logit 变换**
```
S = num / den                          (份额，裁剪至 [ε, 1−ε], ε=1e-4)
L = ln(S / (1−S))                      (Fisher-Pry 变换)
```

**阶段 2 — 空间叠加**
```
L_c(t) = L_c(2015) + [L_R(t) − L_R(2015)]    (国家 = 基年 + 区域 Δ)
S_c(t) = 1 / (1 + exp(−L_c(t)))               (sigmoid 逆变换)
```

**阶段 3 — 迭代封顶缩放**
1. 初始分配：`R_c = S_c × E_c_den`（× 分母得绝对量）
2. 缩放匹配 GCAM 区域分子：`R_c *= target / ΣR`
3. 封顶（`R_c ≤ E_c_den`），超额重新分配给未封顶国家
4. 迭代直到收敛（|误差| < 1e-6）或最大 50 次
5. 最终份额：`S_c = R_c / E_c_den`

此方法为 Fisher-Pry 变换在 IAM 空间降尺度领域的原创应用。

---

## Kaya/DSCALE 份额计算

对于份额指标（fossil_share, renewable_share, electrification_rate, green_elec_share），Kaya 和 DSCALE 方法同样使用 Logit 空间变换，但用各自收敛权重替代阶段 2 的完整 ΔL 叠加：

- **Kaya**：`L_c(t) = L_c(2015) + w(t) × ΔL_R(t)`，w(t) = 1 − exp(γ×(t−y_h))（implemented in `compute_kaya_share()`）
- **DSCALE**：`L_c(t) = ENSHORT_L × CONV_WEIGHT + ENLONG_L × (1−CONV_WEIGHT)`（implemented in `compute_dscale_share()`）

然后用 sigmoid 逆变换 + 迭代封顶缩放（`_iterative_capped_scaling`）得到最终份额。三方案共享同一套迭代缩放逻辑，保证 ∈ [0,1] 且区域守恒完美。

---

## 运行

```bash
# 安装依赖
uv sync

# 全量运行（并行：6 核）
N_JOBS=6 uv run python compare/run_all.py

# 顺序运行
uv run python compare/run_all.py

# 全部测试
uv run python -m pytest compare/tests/ -q

# 单独运行一个指标
uv run python -c "
from compare.common.downscale import run_indicator
from compare.common.config import INDICATORS
df = run_indicator('dscale', 'SSP126', INDICATORS['tfc'])
"
```

---

## 输出

`compare/output/`（gitignored，由 pipeline 生成）：

| 文件 | 格式 | 说明 |
|------|------|------|
| `{method}_{indicator}_downscaled_{scenario}.xlsx` | xlsx | 降尺度结果（Scenario, iso, Country, Region, 2015...2100），6 位小数 |
| `{method}_{indicator}_log.txt` | txt | 守恒校验日志 |
| `dashboard_{indicator}_{scenario}.png` | png | 5 面板仪表盘（全球总计、Top-10、散点图、偏差分布） |
| `share_{indicator}_{scenario}.png` | png | 4 份份额指标对比（Top-5 时间序列、分布直方图、散点图） |
| `cross_indicator_{scenario}.png` | png | 跨指标方法一致性（相关性 + CV） |

---

## 测试

```bash
uv run python -m pytest compare/tests/ -q   # 226 测试，全部通过
uv run python -m pytest compare/tests/ -q -m "not slow"  # 核心测试 ~60s
```

| 文件 | 测试数 | 覆盖 |
|------|--------|------|
| `test_conservation.py` | 82 | 区域守恒（GCAM 对比）、单国一致性、份额有界、NaN/负数、情景排序 |
| `test_cross_validate.py` | 24 | 官方 DSCALE 公式逐元素对比 |
| `test_edge_cases.py` | 39 | convergence_gamma、van_vuuren_ei、convergence_weight、mapping |
| `test_synthetic_gdp.py` | 21 | 合成 GDP 生成 |
| `test_validation_experiments.py` | 60 | 份额有界性、单国一致性（全情景）、ENLONG α 调和、边缘场景 |

---

## 项目结构

```
downscaling/
├── README.md                     # 本文件
├── AUDIT.md                      # v4 审计报告（21 项 Bug 修复）
├── CLAUDE.md                     # 详细数据规格与代码规范
├── pyproject.toml                # uv 环境配置
├── data/                         # 输入数据
│   ├── gcam/                     # GCAM 区域输出 (TFC, 电力, CO2 等)
│   ├── iea/                      # IEA WORLDBAL 1970-2024 + 各指标基准
│   ├── ssp/                      # SSP GDP/人口 + USDA GDP + UN 人口
│   ├── emissions/                # EDGAR 排放数据
│   └── mapping/                  # 国家-区域映射表
├── compare/                      # ★ 三方案对比
│   ├── common/                   # 共享模块
│   │   ├── config.py             # 路径、场景、YEARS、IndicatorConfig 注册表
│   │   ├── io.py                 # 统一数据读写（IEA, GCAM, GDP, POP, EDGAR）
│   │   ├── mapping.py            # 国家-区域映射、名称标准化、台湾合并
│   │   ├── downscale.py          # 三方案实现 + share 函数 + run_indicator
│   │   └── conservation.py       # 守恒校验 + 日志
│   ├── logit/                    # 方案 C: 恒定份额比例法
│   ├── kaya/                     # 方案 A: Kaya 收敛法
│   ├── dscale/                   # 方案 B: DSCALE 官方适配层
│   │   ├── dscale_official.py    # ENLONG/ENSHORT/收敛/MAX_TC
│   │   └── downscale_tfc.py      # TFC 专用入口（含 ENSHORT 历史回归）
│   ├── tests/                    # 5 测试文件 + conftest，226 测试
│   ├── output/                   # 所有输出（gitignored）
│   ├── run_all.py                # 一键运行（支持 N_JOBS 并行）
│   └── compare_results.py        # 对比可视化
├── DSCALE/                       # 官方 DSCALE 仓库（零修改）
│   └── downscaler/
│       ├── fit_funcs.py          # LogLogFunc, LogisticFunc, LinearFunc
│       ├── Energy_demand_downs_1.py  # 官方主降尺度流程
│       └── utils.py              # 工具函数
├── archive/                      # 归档文件（历史代码、旧输出、补充资料）
└── docs/audit/                   # 详细审计报告
```

---

## 审计状态

v4（2026-06-15）：Kaya 方法切换到 van Vuuren 2007 官方指数插值法。21 项 Bug 修复。226 测试全部通过，0 warnings。详见 `AUDIT.md`。

---

## 参考文献

### 方案 A — Kaya 收敛法
1. **van Vuuren, D.P., Lucas, P.L. & Hilderink, H.** (2007). "Downscaling drivers of global environmental change." *Global Environmental Change*, 17(1), 114–130. DOI: 10.1016/j.gloenvcha.2006.04.004 — 原始指数收敛降尺度方法
2. **Gidden, M.J. et al.** (2019). "Global emissions pathways under different socioeconomic scenarios for use in CMIP6." *GMD*, 12(4), 1443–1475. DOI: 10.5194/gmd-12-1443-2019 — CMIP6 排放数据集
3. **Gütschow, J. et al.** (2021). "Country-level GHG emissions pathways derived from RCP and SSP scenarios." *ESSD*, 13(3), 1005–1040. DOI: 10.5194/essd-13-1005-2021 — SSP 收敛参数（d=0.01, 收敛年 2150–2300）
4. **Kaya, Y.** (1995). "Impact of carbon dioxide emission control on GNP growth." *IPCC Energy and Industry Subgroup*, Paris. — Kaya 恒等式

### 方案 B — DSCALE 双路径法
5. **Sferra, F. et al.** (2026). "DSCALE v0.1 — an open-source algorithm for downscaling regional and global mitigation pathways to the country level." *GMD*, 19(8), 3157–3197. DOI: 10.5194/gmd-19-3157-2026 — DSCALE 方法论文
6. **Sferra, F. et al.** (2019). "Towards optimal 1.5 and 2 °C emission pathways for individual countries." *Energy Policy*, 133, 110890. DOI: 10.1016/j.enpol.2019.04.020 — DSCALE 前身
7. **Official DSCALE repository**: https://github.com/fabiosferra/DSCALE

### 方案 C — Logit/比例法
8. **Marchetti, C. & Nakicenovic, N.** (1979). "The dynamics of energy systems and the logistic substitution model." *IIASA Research Report RR-79-013*. — Fisher-Pry 变换（L = ln(S/(1−S))）

### 数据与情景框架
9. **Riahi, K. et al.** (2017). "The Shared Socioeconomic Pathways and their energy, land use, and greenhouse gas emissions implications." *Global Environmental Change*, 42, 153–168. DOI: 10.1016/j.gloenvcha.2016.05.009 — SSP 情景框架

### 项目内部文档
10. `archive/old_docs/logit降尺度方案.md` — Logit 降尺度方法论文档
11. `archive/supplementary/补充资料/DSCALE v0.1 – an open-source algorithm for downscaling...pdf` — DSCALE 论文全文
12. `archive/supplementary/补充资料/WORLDBAL_Documentation_July2025.pdf` — IEA WORLDBAL 数据文档

---

## License

MIT
