# CLAUDE.md

## 一、项目概述

本项目将 GCAM（Global Change Analysis Model）的区域级气候与能源情景数据降尺度（downscale）到国家粒度，以支持 SDG（可持续发展目标）相关研究。

### 当前阶段目标

为评估不同降尺度方法对动态趋势的捕捉能力，本项目并行实现三种降尺度方案，以 **SDG7 - TFC（最终能源消费）** 为首个对比指标。三方案使用完全相同的输入数据与统一的输出格式，便于直接对比优劣。

| 方案 | 简称 | 核心思想 | 关键文献 |
|------|------|---------|---------|
| **Kaya 收敛法** | `kaya` | 能源强度按人均 GDP 条件收敛到 GCAM 区域值 | van Vuuren 2007; Gidden 2019 |
| **DSCALE 双路径法** | `dscale` | ENLONG（区域 log-log 回归）+ ENSHORT（GDP 缩放/历史回归）+ MAX_TC 收敛 | Sferra 2026 |
| **恒定份额比例法** | `logit` | TFC 按 2015 IEA 比例分配（无界量）；份额类指标使用完整 Logit 变换流程 | 当前项目 |

---

## 二、数据目录总览

所有输入数据统一存放在 `data/` 目录下。旧版 SDG 子目录（`SDG7/`, `SDG12/` 等）已归档至 `archive/old_sdg/`。

| 目录 | 内容 | 状态 |
|------|------|------|
| `data/gcam/` | GCAM 区域输出（TFC、电力、CO2 等）| ★ 活跃 |
| `data/iea/` | IEA WORLDBAL 1970-2024 CSV + 各指标基准 xlsx | ★ 活跃 |
| `data/ssp/` | SSP GDP/人口（国家+区域）| ★ 活跃 |
| `data/emissions/` | EDGAR 排放数据 | ★ 活跃 |
| `data/mapping/` | 国家-区域映射表 | ★ 活跃 |

---

## 三、TFC 对比用输入数据（详细规格）

### 3.1 GCAM TFC 区域时序

| 属性 | 值 |
|------|---|
| **路径** | `data/gcam/TFC_{SCENARIO}.xlsx` |
| **SCENARIO** | SSP126, SSP245, SSP434, SSP460（大写 SSP） |
| **Shape** | 259 行 × 25 列（四个情景一致） |
| **列列表** | `Scenario, Region, fuel, 1990, 2005, 2010, 2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050, 2055, 2060, 2065, 2070, 2075, 2080, 2085, 2090, 2095, 2100, Units` |
| **fuel 值** | biomass, coal, district heat, electricity, gas, hydrogen, refined liquids, solar, traditional biomass（9 种） |
| **Region 数** | 32（含 Taiwan）|
| **Units** | `EJ` |
| **备注** | GCAM 区域包含 Taiwan，需在 IO 层合并到 China；不同区域的行数不等（7-9 种燃料），district heat 仅 5 个欧洲区域有 |

**处理方式**：
1. 台湾区域行 → Region 改为 China，然后 `groupby(['Scenario','Region'])[years].sum()` 重新聚合为 31 区域
2. 跨所有 fuel 加总得到每个 Region 的 TFC 总量
3. Units = `EJ` → 所有年份值 × `1_000_000` 转为 TJ

### 3.2 IEA TFC 国家基准

| 属性 | 值 |
|------|---|
| **路径** | `data/iea/TFC_IEA.xlsx`（单文件，不分情景；主数据源为 `data/iea/WORLDBAL_1970_2024.csv`）|
| **Shape** | 158 行 × 26 列 |
| **列列表** | `STRUCTURE, STRUCTURE_ID, STRUCTURE_NAME, ACTION, COUNTRY, Country/Region, ENERGY_BALANCE_FLOW, Flow, ENERGY_PRODUCT, Product, FREQUENCY, Frequency, MEASURE, Balance measure, TIME_PERIOD, Time Period, OBS_VALUE, Observation value, CONF_STATUS, Confidential Status, QUALIFIER, Qualifier, UNIT, Unit, DECIMALS, Decimals` |
| **Flow 值** | 全部为 `Total final consumption` |
| **Product 值** | 全部为 `Total` |
| **TIME_PERIOD** | 全部为 `2015` |
| **Unit** | `TJ` |
| **OBS_VALUE 范围** | 3,168 – 82,860,386 TJ |
| **0 值数量** | 0 |

**处理方式**：
1. 筛选：`Flow == 'Total final consumption'`, `Product == 'Total'`, `TIME_PERIOD == '2015'`
2. 删除 5 个实体：`Greenland, Palestinian Authority, Gibraltar, Kosovo, South Sudan`
3. 映射表中的 `IEA_ctry` 列指示各国家的 IEA 报告状态：
   - 以 "Other" 开头的（35 国）→ IEA 不单独报告，通过 GCAM 残差+人口拆分处理
   - 其余 113 国 → WORLDBAL 直接匹配单国数据
4. 产出：`{Country/Region: OBS_VALUE_TJ}` 字典

### 3.3 国家级 GDP（IIASA SSP）

| 属性 | 值 |
|------|---|
| **路径** | `data/ssp/GDP_{scenario}.xlsx` |
| **SCENARIO** | ssp126, ssp245, ssp434, ssp460（小写 ssp）|
| **Shape** | 172 行 × 24 列（四个情景一致）|
| **列列表** | `MODEL, SCENARIO, iso, VARIABLE, UNIT, 2010, 2015, 2020, 2025, 2030, 2035, 2040, 2045, 2050, 2055, 2060, 2065, 2070, 2075, 2080, 2085, 2090, 2095, 2100` |
| **iso 数量** | 172（ISO 3166-1 alpha-3 小写，如 bhs, chn, usa）|
| **VARIABLE** | 全部为 `GDP\|PPP` |
| **UNIT** | `billion US$2005/yr` |
| **MODEL** | `IIASA GDP` |

### 3.4 国家级人口（IIASA SSP）

| 属性 | 值 |
|------|---|
| **路径** | `data/ssp/pop_{SCENARIO}.xlsx` |
| **SCENARIO** | SSP126, SSP245, SSP434, SSP460（大写 SSP）|
| **Shape** | SSP126: 193 行 × 24 列；SSP245/434/460: 193 行 × 34 列（后者含 2105-2150 年份）|
| **列列表** | `MODEL, SCENARIO, REGION, VARIABLE, UNIT, [年份列...]` |
| **年份范围** | SSP126: 2010–2100（5 年间隔）；SSP245/434/460: 2010–2150 |
| **REGION 列** | ISO 3 字母代码（大写，如 BHS, CHN, USA），**注意列名是 REGION 不是 iso** |
| **VARIABLE** | 全部为 `Population` |
| **UNIT** | `million` |
| **MODEL** | `IIASA-WiC POP` |
| **SCENARIO 示例** | `SSP1_v9_130115`（非 SSP126 字符串，由 SSP126 映射而来）|

### 3.5 区域级 GDP（SSP）

| 属性 | 值 |
|------|---|
| **路径** | `data/ssp/GDP_region_{scenario}.xlsx` |
| **SCENARIO** | ssp126, ssp245, ssp434, ssp460（小写 ssp）|
| **Shape** | 32 行 × 24 列（四个情景一致）|
| **列列表** | `Scenario, Region, 1990, 2005, 2010, 2015, 2020, ...[5年列到2100]..., Units` |
| **Region 数** | 32（含 Taiwan）|
| **Units** | `million 1990$` |
| **备注** | 与 GCAM TFC 的 32 区域完全对齐 |

### 3.6 区域级人口（SSP）

| 属性 | 值 |
|------|---|
| **路径** | `data/ssp/pop_region_{scenario}.xlsx` |
| **SCENARIO** | ssp126, ssp245, ssp434, ssp460（小写 ssp）|
| **Shape** | 32 行 × 24 列（四个情景一致）|
| **列列表** | `scenario, region, 1990, 2005, 2010, 2015, 2020, ...[5年列到2100]..., Units` |
| **Region 数** | 32（含 Taiwan）|
| **Units** | `thous`（千人，需 ÷1000 转 million）|
| **备注** | 列名 `scenario, region` 均为小写，与其他数据源的大写 `Scenario, Region` 不同 |

### 3.7 国家-区域映射

| 属性 | 值 |
|------|---|
| **路径** | `gcam_country_region1120.xlsx`（单文件）|
| **Shape** | 180 行 × 8 列 |
| **列列表** | `GCAM_region_ID, GCAM Region, iso, GCAM Country, iso_ctry, IEA_ctry, alternative name 1, remark` |
| **iso** | ISO 3166-1 alpha-3 小写，180 个国家/地区 |
| **GCAM Region** | 32 个区域名 |
| **IEA_ctry** | IEA 国家名称，`Other non-OECD Africa/Americas/Asia/Asia Oceania` 为合并区域标记 |
| **remark** | 仅 Taiwan 行有值：`Provincial administrative regions of China` |

**China/Taiwan 相关行**：
```
China:  GCAM Region=China,  iso=chn, IEA_ctry=China Region (P.R. of China and Hong Kong, China)
Taiwan: GCAM Region=Taiwan, iso=twn, IEA_ctry=Chinese Taipei, remark=Provincial administrative regions of China
```

### 3.8 IEA 多年度历史数据（2015-2020）

| 属性 | 值 |
|------|---|
| **路径** | `补充资料/OECD.IEA,WORLDBAL,1.1,filtered,2025-11-15 19-07-46.csv` |
| **Shape** | 118,770 行 × 26 列 |
| **格式** | OECD.IEA WORLDBAL（同 .xlsx 的 CSV 版本） |
| **年份范围** | 2015–2020（每年） |
| **国家数** | 180 |
| **Flow 类型** | Total final consumption, Total energy supply, Electricity output, Industry, Transport, Residential 等 10 种 |
| **Product 类型** | Total, Total of renewable energy sources, 及按燃料细分 11 种 |
| **Unit** | TJ |
| **用途** | DSCALE ENSHORT 趋势修正：计算各国 2015→2020 能源强度 CAGR，替代恒定 EI 假设 |

### 3.9 场景命名不一致对照表

| 数据源 | SSP126 | SSP245 | SSP434 | SSP460 |
|--------|--------|--------|--------|--------|
| GCAM TFC | `TFC_SSP126.xlsx`（大写 SSP）| `TFC_SSP245.xlsx` | `TFC_SSP434.xlsx` | `TFC_SSP460.xlsx` |
| 国家级 GDP | `GDP_ssp126.xlsx`（小写 ssp）| `GDP_ssp245.xlsx` | `GDP_ssp434.xlsx` | `GDP_ssp460.xlsx` |
| 国家级人口 | `pop_SSP126.xlsx`（大写 SSP）| `pop_SSP245.xlsx` | `pop_SSP434.xlsx` | `pop_SSP460.xlsx` |
| 区域 GDP | `GDP_region_ssp126.xlsx`（小写）| `GDP_region_ssp245.xlsx` | `GDP_region_ssp434.xlsx` | `GDP_region_ssp460.xlsx` |
| 区域人口 | `pop_region_ssp126.xlsx` | `pop_region_ssp245.xlsx` | `pop_region_ssp434.xlsx` | `pop_region_ssp460.xlsx` |

**在 `common/config.py` 中统一处理所有变体，确保按 `SSP126, SSP245, SSP434, SSP460` 四个情景键遍历。**

### 3.10 单位转换汇总

| 数据 | 原始单位 | 内部计算单位 | 转换公式 |
|------|---------|-------------|---------|
| GCAM TFC | EJ | **TJ** | × 1,000,000 |
| IEA TFC | TJ | **TJ** | 不变 |
| 国家 GDP | billion US$2005/yr | — | 仅用比值，不转换 |
| 区域 GDP | million 1990$ | — | 仅用比值 |
| 国家人口 | million | **million** | 不变 |
| 区域人口 | thous | **million** | ÷ 1,000 |

**注意**：国家级 GDP（2005$）和区域级 GDP（1990$）基准年不同。收敛公式使用 **比值**（`GDP(t)/GDP(2015)`），基准年差异不影响计算结果。

---

## 四、其他 SDG 数据文件（参考）

### SDG7 其他子目录

| 子目录 | 文件 | Shape | 关键列 |
|--------|------|-------|--------|
| 发电量Electricity output | `GCAM_elec_{SCENARIO}.xlsx` | 32×27 | Scenario, Region, subsector, output, technology, [years], Units |
| 发电量Electricity output | `Electricity output_IEA.xlsx` | 158×26 | IEA WORLDBAL 格式，Flow=Electricity output |
| 电气化率 | `TFC_{SCENARIO}.xlsx` | 259×25 | 与最终能源消费TFC 下的数据**完全相同**（副本）|
| 电气化率 | `TFC_IEA.xlsx` | 158×26 | TFC IEA 副本 |
| 电气化率 | `TFC_ElE_IEA.xlsx` | 158×26 | IEA 电力消费数据 |
| 可再生能源份额Ratio | `区域能源消费_{scenario}.xlsx` | 64×24 | Scenario, Region, fuel, [years] — 一次能源消费 |
| 可再生能源份额Ratio | `TES_IEA.xlsx` | 158×26 | 一次能源供应 IEA |
| 可再生能源份额Ratio | `TFC_IEA.xlsx` | 158×26 | TFC IEA 副本 |
| 可再生能源份额Ratio | `TES_Ren_IEA.xlsx` | 158×26 | 可再生能源供应 IEA |
| 可再生能源份额Ratio | `TFC_Ren_IEA.xlsx` | 158×26 | 可再生能源消费 IEA |
| 能源强度 | `GDP_{scenario}.xlsx` | 172×24 | ★ 国家级 GDP（同第三节，核心输入）|
| 能源强度 | `TFC_downscaled_{SCENARIO}.xlsx` | 179×22 | 已降尺度的 TFC 输出（来自 code/ 脚本）|

### SDG12

| 子目录 | 文件 | Shape | 关键列 |
|--------|------|-------|--------|
| 化石能源份额 | `primary energy consumption by region_{SCENARIO}.xlsx` | 317×25 | Scenario, Region, fuel, [years] |
| 化石能源份额 | `TES_IEA.xlsx` | 158×26 | 一次能源供应 IEA |
| 化石能源份额 | `TES_fossil_IEA.xlsx` | 474×26 | 化石能源 IEA（含多 Product 类型）|
| 绿电发电量 | `GCAM_elec_{SCENARIO}.xlsx` | 32×27 | 与 SDG7 发电量副本相同 |
| 绿电发电量 | `GCAM_renewable_elec_{SCENARIO}.xlsx` | 32×27 | 可再生能源发电 GCAM |
| 绿电发电量 | `ELEoutput_IEA.xlsx` | 158×26 | 总发电量 IEA |
| 绿电发电量 | `ELEoutput_Ren_IEA.xlsx` | 158×26 | 可再生能源发电 IEA |

### SDG9 — 工业直接 CO2 排放

| 文件 | Shape | 列 | 备注 |
|------|-------|---|------|
| `GCAM_industry_{SCENARIO}.xlsx` | 32×25 | Scenario, Region, sector, [years], Units | sector 列含 'industry' |
| `industry_emissions.xlsx` | 201×7 | Country_code_A3, Name, Substance, fossil_bio, 2015, 2020, sector | EDGAR 基准，单 sheet |
| `IEA_EDGAR_CO2_1970_2023.xlsx` | 多 sheet | Sheet "TOTALS BY COUNTRY": 234×59 | EDGAR 历史排放数据库 |

### SDG13 — 人均温室气体排放

| 文件 | Shape | 列 | 备注 |
|------|-------|---|------|
| `CO2_emissions_{SCENARIO}.xlsx` | 32×21 | Scenario, Region, [years 2010-2100] | GCAM CO2 区域总量（单位 MTC） |
| `IEA_EDGAR_CO2_1970_2023.xlsx` | 多 sheet | Sheet "TOTALS BY COUNTRY"（索引 3）: 234×59 | EDGAR 历史 CO2，Columns: Country_code_A3, Name, Substance, Y_2015,... |

### SDG1 — 最低分位数收入

| 文件 | Shape | 列 | 备注 |
|------|-------|---|------|
| `mip_income_d_long_{scenario}.csv` | 29340×27 | Model, Scenario, Region, Year, Income\|D1..Income\|D10 | 长格式 CSV，Region 列含 ISO 代码 |

### IEA WORLDBAL 通用格式

所有 `*_IEA.xlsx` 文件共享 OECD.IEA WORLDBAL 格式：
- 26 列：`STRUCTURE, STRUCTURE_ID, ..., COUNTRY, Country/Region, Flow, Product, TIME_PERIOD, OBS_VALUE, Unit`
- Unit 为 `TJ`
- 通过 `Flow` + `Product` + `TIME_PERIOD` 组合筛选目标数据

### 已有降尺度输出格式

所有已降尺度输出（`*_downscaled_*.xlsx`）统一为：
```
Columns: Scenario | iso | Country | Region | 2015 | 2020 | 2025 | ... | 2100
Rows: 179（含国家 + Other 区域行）
iso: lowercase, TWN→CHN
```
SDG1 输出为 160 行（不同的国家覆盖范围），CSV 格式。

---

## 五、三方案统一输出格式

### Excel 输出

- **路径**：`compare/output/{method}_TFC_downscaled_{scenario}.xlsx`
- **列结构（严格此顺序）**：

| 列 | 类型 | 说明 |
|----|------|------|
| Scenario | str | `SSP126` / `SSP245` / `SSP434` / `SSP460` |
| iso | str | ISO 3166-1 alpha-3 小写（twn→chn）|
| Country | str | 归一化显示名称（来自 `GCAM Country`）|
| Region | str | GCAM 区域名（31 个，Taiwan→China）|
| 2015 | float | TJ，6 位小数 |
| 2020 | float | TJ |
| ... | float | 每 5 年到 2100 |
| 2100 | float | TJ |

### 日志输出

- **路径**：`compare/output/{method}_TFC_log.txt`
- 必须包含：
  1. 运行时间戳 + 方法名称
  2. IEA 匹配统计：`单列国家 X 个，已匹配 Y 个，未匹配 Z 个（列名）`
  3. 每个 GCAM 区域：单列国家数 / Other 成员数 / 未匹配数
  4. 每个区域逐年守恒：最大偏差（TJ）[期望 ≤ 1e-6]
  5. 全局守恒：`国家合计 + Other合计 vs GCAM总量`

### 对比汇总输出

- **路径**：`compare/output/compare_TFC_summary.xlsx`
- 内容：三方案并列，每年区域守恒偏差、关键国家 TFC 值对比

---

## 六、三方案数学公式

### 共享符号

| 符号 | 含义 | 来源 |
|------|------|------|
| `E_c^IEA` | 国家 c 的 IEA 2015 TFC 基准值（TJ）| IEA TFC |
| `E_R(t)` | GCAM 区域 R 在年份 t 的 TFC 总量（TJ，已合并 Taiwan）| GCAM TFC |
| `G_c(t)` | 国家 c 在年份 t 的 GDP（billion US$2005/yr）| 国家 GDP |
| `P_c(t)` | 国家 c 在年份 t 的人口（million）| 国家人口 |
| `G_R(t)` | 区域 R 的 GDP 总量（sum over c∈R）| 区域 GDP |
| `P_R(t)` | 区域 R 的人口总量（sum over c∈R）| 区域人口 |
| `I_c(t)` | 能源强度 `E_c(t) / G_c(t)` | 计算 |
| `I_R(t)` | 区域能源强度 `E_R(t) / G_R(t)` | 计算 |
| `φ(c,t)` | 收敛权重函数 ∈ [0,1] | 方案定义 |
| `t_0` | 基年 2015 | 固定 |

---

### 方案 A：Kaya 收敛法（kaya）

**文献基础**：Kaya 恒等式（Kaya 1995）; van Vuuren et al. 2007（指数收敛降尺度概念）;
Gütschow et al. 2021（SSP 收敛参数：d=0.01, 收敛年 2150-2300）

> ⚠️ **方法定位**：本方案的数学公式（指数 φ 乘方追踪区域比例变化、γ_c 按人均 GDP 调整、
> t_c 取 2070-2100）**不同于**文献中 van Vuuren 的指数插值法（`a_c × e^(γ·y) + b_c`，
> 收敛年份 2150-2300）。这是对 Kaya 恒等式框架下收敛概念的**独立实现**，不宜直接归因于
> van Vuuren 2007 或 Gidden 2019 的具体算法。在 IAM 降尺度文献中，将按国别调整的
> 收敛速度（γ_c）与比例跟踪公式（φ 乘方）结合的做法**未见先例**。公式设计理念和参数
> 选择（γ_c 的 0.3 系数、t_c 的 SSP 映射）为本项目的方法论决策。
> 文献背景见下文对照表。

**步骤 1**：基年能源强度
```
I_c(2015) = E_c^IEA / G_c(2015)
I_R(t)   = E_R(t) / G_R(t)
```

**步骤 2**：条件收敛（原创公式）
```
I_c(t) = I_c(2015) × [I_R(t) / I_R(2015)] ^ φ(c,t)
φ(c,t) = 1 - exp(-γ_c × (t - 2015) / (t_c - 2015))
```
核心思想：t=2015 时 φ=0，国家 EI 保持基年值；随着 t→t_c，φ→1-exp(-γ_c)，国家 EI
逐渐追踪区域 EI 的比例变化。完全收敛仅渐进实现（φ→1 当 t→∞）。

**对比文献方法**（van Vuuren 2007; Gütschow et al. 2021 ESSD）：
```
EI_c(y) = a_c × e^(γ·y) + b_c      # 指数插值到固定目标
γ = ln(0.01) / (y_c - y_h)         # d=0.01: 到收敛年消除 99% 差距
EI_c(y) = EI_R(y)   for y ≥ y_c    # 收敛年后完全等于区域值
```
| 差异点 | 文献（van Vuuren/Gütschow）| 本实现 |
|--------|--------------------------|--------|
| 收敛目标 | 收敛年的固定区域 EI 值 | 逐年变化的区域 EI 比例轨迹 |
| 收敛年份 | SSP1=2150, SSP2=2200, SSP3/4=2300 | SSP126=2070, SSP245=2085, SSP434/460=2100 |
| 收敛速度 | d=0.01 固定（99%差距消除）| γ_c 按人均 GDP 逐国调整 |
| GDP 依赖 | 无（仅用于计算 EI）| γ_c = 1.0 + 0.3×ln(GDP_pcap_c/GDP_pcap_world) |
| EI 下限 | 无 | max(I_c_t, I_c_2015 × 0.1)（10% 基年值）|

**步骤 3-4**：同前。

> **份额指标扩展**：对于份额类指标（fossil_share, renewable_share 等），Kaya 方法
> 将上述 φ(t) 收敛权重应用于 Logit 变换空间：`L_c(t) = L_c(2015) + φ(t) × ΔL_R(t)`，
> 然后 sigmoid 逆变换。这保留了逐国收敛速度差异，同时天然保证份额 ∈ [0,1]。
> 实现见 `compute_kaya_share()`。

---

### 方案 B：DSCALE 双路径法（dscale）

**文献**：Sferra et al. 2026 (GMD, DOI:10.5194/gmd-19-3157-2026)
**官方代码**：https://github.com/fabiosferra/DSCALE

**步骤 1 — ENLONG（长期投影）**：对每个 GCAM 区域做 log-log 回归
```
log(TFC_region / GDP_region) = α + β × log(GDP_region / POP_region)
# 使用 GCAM 时间序列 (1990, 2005, 2010, 2015-2100) 作为回归数据
# 然后将回归系数应用到区域内每个国家：
ENLONG_c(t) = exp(α + β × log(GDP_c(t) / POP_c(t))) × GDP_c(t)
```
回归使用官方 `fit_funcs.py` 中的 `LogLogFunc` 类（直接调用，零修改）。

**步骤 2 — ENSHORT（短期投影）**：逐国历史 log-log 回归

数据源：IEA WORLDBAL (1970-2020 TFC) + USDA GDP (1969-2017) + UN Population (1950-2020)

```
log(TFC_c / GDP_c) = α + β × log(GDP_c / POP_c)          # 对每个国家分别回归
α += log(EI_base) - (α + β × log(GDP_pcap_base))         # alpha 调和至基年观测值
EI_c(t) = clip(exp(α + β × log(GDP_c(t)/POP_c(t))), 0, 1)  # 封顶到 [0,1]
ENSHORT_c(t) = EI_c(t) × GDP_c(t)
```

**覆盖率**：148 个有 WORLDBAL TFC 数据的国家中，143 个（96.6%）满足 ≥5 对齐数据点要求，
成功拟合 ENSHORT 回归（全部拥有 40+ 数据点）。瓶颈不在 TFC（WORLDBAL 覆盖充分），
而在 USDA GDP 历史数据的国家覆盖。

**5 个回退到 GDP 缩放的国家**：

| ISO | 国家 | 失败原因 |
|-----|------|---------|
| `mne` | Montenegro | USDA GDP 无数据；2006 年从塞尔维亚独立，历史经济数据归属于前身国家 |
| `prk` | North Korea | USDA GDP 无数据；极端封闭经济体 |
| `qat` | Qatar | USDA GDP 无数据；合成 GDP 国家 |
| `rou` | Romania | USDA GDP 无数据；SSP 数据库 GDP 仅有 2010 一个历史年份（不足 ≥5）|
| `zwe` | Zimbabwe | 同上，SSP GDP 仅有 2010 一年 |

> 官方 DSCALE 使用 1980-2015 逐国 IEA 回归。本项目回退优先级：
> (a) log-log 历史回归（≥5 对齐点，143 国），
> (b) 2015-2020 IEA 能源强度 CAGR 外推，
> (c) GDP 缩放（恒定基年 EI，5 国）。

**步骤 3 — MAX_TC 收敛**（来自官方 `Energy_demand_downs_1.py:650-675`）
```
CONV_WEIGHT = ((t - MAX_TC) / (2010 - MAX_TC)) ^ clip(β, 1, ∞)
CONV_WEIGHT = clip(CONV_WEIGHT, 0, 1)
E_c(t) = ENSHORT × CONV_WEIGHT + ENLONG_RATIO × (1 - CONV_WEIGHT)
```
β 优先使用逐国 ENSHORT 回归斜率（与官方一致），无 ENSHORT 回归时回退到区域 ENLONG β。
MAX_TC 通过 `fun_max_tc()` 动态计算（2040-2200），基于 ENSHORT 回归质量 + β 符号一致性。

**步骤 4**：区域守恒校准（同 A 步骤 4）

**关键参数**：
| 参数 | 值 |
|------|---|
| MAX_TC | 2040-2200（动态，基于 ENSHORT 回归质量 + β 符号一致性）|
| β 指数 | `clip(β, 1, ∞)`（优先 ENSHORT β，回退 ENLONG β；负 β→1）|
| 收敛方向 | ENSHORT → ENLONG（近期ENSHORT主导，远期ENLONG主导）|

> **份额指标扩展**：对于份额类指标，DSCALE 方法将 MAX_TC 收敛权重应用于 Logit 空间：
> ENSHORT = L_c(2015)，ENLONG = L_c(2015) + ΔL_R(t)，通过 CONV_WEIGHT 混合。
> 实现见 `compute_dscale_share()`。

---

### 方案 C：Logit/比例法（logit）

**文献**：Marchetti & Nakicenovic 1979（Fisher-Pry 变换：L = ln(S/(1-S))，用于
**时间**维度的技术替代建模）; 本项目（将 Logit 变换应用于**空间**维度的区域→国家
降尺度，在 IAM 降尺度文献中未见先例）。

TFC 为无界变量，本方案使用简单比例分配；份额类指标（化石份额、可再生份额、电气化率等）
使用三阶段 Logit 空间降尺度：Logit 变换 → 叠加区域 ΔL → 逆变换 + 迭代封顶缩放。
此方法在 `archive/old_docs/logit降尺度方案.md` 中详细说明。

对于 Kaya 和 DSCALE 方法，份额指标采用相同的 Logit 变换框架但用各自收敛权重（φ_Kaya、
CONV_WEIGHT_DSCALE）替换阶段 2 的完整 ΔL 叠加，保留方法间收敛动力学的差异同时确保
份额有界 ∈ [0,1]。

**步骤 1**：2015 权重
```
weight_c = E_c^IEA / Σ_k E_k^IEA          # k ∈ 单列国家(R)
other_share_R = 1 - Σ_k E_k^IEA / E_R(2015)
```

**步骤 2**：逐年分配
```
E_c(t) = weight_c × E_R(t) × (1 - other_share_R)
```

**步骤 3**：Other 与残差处理
残差计入对应 Other 区域类别，无法归类的计入 Other Residual Global。

---

## 七、代码结构

```
downscaling/
├── pyproject.toml                           # uv 环境配置
├── CLAUDE.md                                # 本文件
├── AUDIT.md                                 # 审计报告
├── README.md
├── data/                                    # 输入数据
│   ├── gcam/                                # GCAM 区域输出
│   ├── iea/                                 # IEA WORLDBAL + 基准
│   ├── ssp/                                 # SSP GDP/人口
│   ├── emissions/                           # EDGAR 排放
│   └── mapping/                             # 国家-区域映射
├── DSCALE/                                  # 官方 DSCALE 仓库（零修改）
├── archive/                                 # 归档文件
│
└── compare/                                 # ★ 三方案对比
    ├── common/                              # 共享模块
    │   ├── __init__.py
    │   ├── config.py                        # 路径常量、场景列表、指标注册
    │   ├── mapping.py                       # 映射加载、normalize、ISO↔区域
    │   ├── io.py                            # 统一数据读写
    │   ├── downscale.py                     # 通用降尺度引擎（三方案 + 份额计算）
    │   └── conservation.py                  # 守恒校验 + 日志输出
    ├── kaya/                                # 方案 A
    ├── dscale/                              # 方案 B（含 dscale_official.py 适配层）
    ├── logit/                               # 方案 C
    ├── output/                              # 输出
    ├── run_all.py                           # 一键运行 8×3×4 + 份额 + 图表
    └── compare_results.py                   # 对比分析 + 可视化
```

### 各方案 downscale_tfc.py 统一签名

```python
def downscale_tfc(scenario: str) -> pd.DataFrame:
    """
    Args:
        scenario: 'SSP126' | 'SSP245' | 'SSP434' | 'SSP460'
    Returns:
        DataFrame: columns=[Scenario, iso, Country, Region, 2015, 2020, ..., 2100]
    """
```

### common/ 模块职责

**config.py**：所有路径统一指向 `data/` 目录
```python
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
COMPARE_DIR = BASE_DIR / "compare"
OUTPUT_DIR = COMPARE_DIR / "output"
SCENARIOS = ["SSP126", "SSP245", "SSP434", "SSP460"]
YEARS = list(range(2015, 2101, 5))
MAPPING_PATH = DATA_DIR / "mapping" / "gcam_country_region1120.xlsx"

GDP_COUNTRY_DIR = DATA_DIR / "ssp"
POP_COUNTRY_DIR = DATA_DIR / "ssp"
GDP_REGION_DIR = DATA_DIR / "ssp"
POP_REGION_DIR = DATA_DIR / "ssp"

GCAM_TFC_DIR = DATA_DIR / "gcam"
IEA_TFC_PATH = DATA_DIR / "iea" / "TFC_IEA.xlsx"
IEA_WORLDBAL_PATH = DATA_DIR / "iea" / "WORLDBAL_1970_2024.csv"
```

**mapping.py**：
- `normalize_name(s: str) -> str`：复用现有 `code/` 脚本的标准化逻辑
- `load_mapping() -> pd.DataFrame`：读取映射表，合并 TWN→CHN
- `build_region_members() -> dict[str, list]`

**io.py**：
- `read_iea_tfc() -> dict[str, float]`：`{iso: 2015_TJ}`
- `read_gcam_tfc(path) -> pd.DataFrame`：合并 Taiwan→China + 跨 fuel 加总 + EJ→TJ
- `read_gdp_country(scenario) -> pd.DataFrame`：返回 `iso` 为 index
- `read_pop_country(scenario) -> pd.DataFrame`：列名 REGION→iso
- `read_gdp_region(scenario) -> pd.DataFrame`：合并 Taiwan→China
- `read_pop_region(scenario) -> pd.DataFrame`：合并 Taiwan→China + thous→million
- `write_output(df, method, scenario)`：统一 Excel 输出

**conservation.py**：
- `check_conservation(df, gcam_data) -> str`：返回校验报告
- `write_log(method, report, path)`：写日志

---

## 八、代码编写规范

### Python 规范

1. 所有路径使用 `pathlib.Path`
2. 所有函数参数和返回值添加类型注解（`typing`）
3. 名称匹配前调 `common.mapping.normalize_name()`
4. Excel 读取用 `pd.read_excel(path, engine="openpyxl")`，`dtype=str` 读入后分别 `pd.to_numeric()` 转换数值列
5. 日志统一用 `common.conservation` 中的函数
6. **不要添加不必要的注释或 docstring**；仅在不明显处加短注释
7. `for scenario in SCENARIOS` 遍历，不硬编码场景名

### 单位处理

- 所有内部计算以 **TJ** 为单位
- GCAM 数据读入立即 ×1e6（EJ→TJ）
- IEA 数据已为 TJ，不变
- GDP 和人口仅用于比值计算

### 映射与匹配

- **映射文件**：`data/mapping/gcam_country_region1120.xlsx`（180 行 × 8 列）
  - `IEA_ctry` 列直接标注各国家的 IEA 报告状态：
    - 以 "Other" 开头 → IEA 聚合区域（35 国），不单独报告
    - 其余 → IEA 单独报告国家（113 国），可直接匹配
  - 代码通过 `_build_iea_name_index()` 构建名称→ISO 索引，**仅使用 GCAM Country 和非 Other 的 IEA_ctry**（避免将聚合名映射到单国）
- **台湾合并**：IO 层读取 GCAM 区域数据时即合并 Taiwan→China（`groupby sum`），ISO 映射层 TWN→CHN
- **排除实体**：Greenland, Palestinian Authority, Gibraltar, Kosovo, South Sudan（5 个）
- **Other 区域**：`Other non-OECD Africa/Americas/Asia Oceania`（3 个）
  - Other 聚合值 = GCAM 区域总量 - 区域内 IEA 单列国家值，通过人口拆分为各国基线
- **未匹配残差** → `Other Residual Global`

### 守恒约束

- 三方案逐年区域 TFC 之和 = GCAM 区域值
- 日志记录每个区域最大偏差（期望 ≤ 1e-6 TJ）

---

## 九、实施顺序

1. `compare/common/config.py` → 路径配置
2. `compare/common/mapping.py` → 映射加载（参考现有代码）
3. `compare/common/io.py` → 数据读写（Taiwan 合并逻辑在此）
4. `compare/common/conservation.py` → 守恒校验
5. `compare/logit/downscale_tfc.py` → 方案 C（最简单，参考 code/ 脚本）
6. `compare/kaya/downscale_tfc.py` → 方案 A
7. `compare/dscale/downscale_tfc.py` → 方案 B（最复杂）
8. `compare/run_all.py` → 一键运行
9. `compare/compare_results.py` → 对比分析

---

## 十、参考文献

### 方案 A
1. **van Vuuren, D.P., Lucas, P.L. & Hilderink, H.** (2007). "Downscaling drivers of global environmental change: Enabling use of global SRES scenarios at the national and grid levels." *Global Environmental Change*, 17(1), 114–130. DOI: 10.1016/j.gloenvcha.2006.04.004  — 原始指数收敛降尺度方法（`EI_c = a_c×e^(γ·y) + b_c`, d=0.01）
2. **van Vuuren, D.P., de Vries, B., Beusen, A. & Heuberger, P.** (2007). "Stabilizing greenhouse gas concentrations at low levels: an assessment of reduction strategies and costs." *Climatic Change*, 81(2), 119–159. DOI: 10.1007/s10584-006-9122-6  — 稳定化情景（收敛方法应用场景）
3. **Gidden, M.J., Riahi, K., Smith, S.J., Fujimori, S., Luderer, G., Krey, V., ... & Zwaan, B.** (2019). "Global emissions pathways under different socioeconomic scenarios for use in CMIP6." *Geoscientific Model Development*, 12(4), 1443–1475. DOI: 10.5194/gmd-12-1443-2019  — CMIP6 排放数据集（使用 `iiasa/emissions_downscaling` 包实现 van Vuuren 方法）
4. **Gütschow, J., Jeffery, M.L., Günther, A. & Gieseke, R.** (2021). "Country-level greenhouse gas emissions pathways derived from the RCP and SSP scenarios." *Earth System Science Data*, 13(3), 1005–1040. DOI: 10.5194/essd-13-1005-2021  — SSP 收敛参数权威来源（d=0.01, 收敛年 2150–2300）
5. **Kaya, Y.** (1995). "Impact of carbon dioxide emission control on GNP growth." *IPCC Energy and Industry Subgroup*, Paris.

### 方案 B
4. **Sferra, F., van Ruijven, B., Riahi, K., Hackstock, P., Maczek, F., Kikstra, J.S. & Haas, R.** (2026). "DSCALE v0.1 — an open-source algorithm for downscaling regional and global mitigation pathways to the country level." *Geoscientific Model Development*, 19(8), 3157–3197. DOI: 10.5194/gmd-19-3157-2026
5. **Sferra, F., Kikstra, J.S., Riahi, K. & Haas, R.** (2019). "Towards optimal 1.5 and 2 °C emission pathways for individual countries." *Energy Policy*, 133, 110890. DOI: 10.1016/j.enpol.2019.04.020

### 方案 C
6. **Marchetti, C. & Nakicenovic, N.** (1979). "The dynamics of energy systems and the logistic substitution model." *IIASA Research Report RR-79-013*.
7. **Grubler, A. & Fujii, Y.** (1991). "Inter-generational and spatial equity issues of carbon accounts." *Energy*, 16(11–12), 1397–1416.  (注：非降尺度方法论文，仅提供排放配额空间公平背景)

### 数据与情景框架
8. **Riahi, K., van Vuuren, D.P., Kriegler, E., Edmonds, J., O'Neill, B.C., ... & Luderer, G.** (2017). "The Shared Socioeconomic Pathways and their energy, land use, and greenhouse gas emissions implications." *Global Environmental Change*, 42, 153–168. DOI: 10.1016/j.gloenvcha.2016.05.009

### 项目内部文档
9. `logit降尺度方案.md` — Logit 降尺度方法论文档
10. `补充资料/DSCALE v0.1 – an open-source algorithm for downscaling regional and global mitigation pathways to the country level.pdf` — DSCALE 论文全文
11. `补充资料/GCAM_区域匹配与下推详解.pdf` — GCAM 区域匹配方法
12. `补充资料/WORLDBAL_Documentation_July2025.pdf` — IEA WORLDBAL 数据文档

---

## 十一、审计状态

最新审计：**v2**（2026-06-02），报告位置：`docs/audit/audit_v2_report.md`

| 指标 | 值 |
|------|---|
| 测试通过 | 137/137（116 核心 + 21 合成 GDP） |
| Pipeline 状态 | 96 降尺度 + 72 份额，全部通过（434.6s） |
| 审计完成度 | 32/33 ✅, 1 ⚠️（E2 可解释） |
| 已知 Bug 修复 | 4 项 |

### 已知局限（审计确认 + 修复后更新）

1. **E2 相关性 r=0.849**：Logit-Kaya 2100 年 log-log 相关性略低于 0.85 阈值（修复后从 0.838 提升至 0.849，仅差 0.001），由多国区域中两种方法的根本数学差异导致，可解释。
2. **ENSHORT 简化**：因缺乏 1980-2015 历史数据，ENSHORT 简化为 GDP 缩放。
3. **Kaya γ_c 参数**：0.3 系数为校准值，未在文献中找到确切出处。

### 审计中修复的 Bug

| # | 修复内容 |
|---|---------|
| 1 | `read_iea_tfc()` 改用 `_build_iea_name_index()` 防止 Other 聚合名泄漏（v1 遗留 Bug） |
| 2 | `test_conservation.py` sys.path 修正（parents[3]→parents[2]） |
| 3 | 新增 `generate_synthetic_gdp()` 函数，为 9 个 GDP 缺失国生成合成 GDP（区域人均 GDP 增长 × SSP 人口），修复 Kaya/DSCALE 塌缩 |
| 4 | 新增 `test_synthetic_gdp.py`（21 项测试） |

### 审计后建议

- Kaya γ_c 敏感性分析（0.1/0.3/0.5）
- DSCALE ENSHORT 全实现（需要 1980-2015 IEA 历史数据）
- 建立 CI/CD pipeline 自动验证
- 创建 git tag `audit-v2-20260602`
