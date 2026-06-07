# GCAM 区域→国家降尺度

将 GCAM（Global Change Analysis Model）区域级气候与能源情景数据降尺度到国家粒度，支持 SDG 指标研究。

## 方法

| 方案 | 简称 | 核心思想 | 文献 |
|------|------|---------|------|
| Kaya 收敛法 | `kaya` | 能源强度按人均 GDP 条件收敛到 GCAM 区域值 | van Vuuren 2007 |
| DSCALE 双路径法 | `dscale` | ENLONG（log-log 回归）+ ENSHORT（历史回归）+ MAX_TC 收敛 | Sferra 2026 |
| 恒定份额法 | `logit` | 按 IEA 基准年份额分配区域总量 | 当前项目 |

覆盖 8 个指标：TFC、电力、TES、化石 TES、可再生 TES、绿色电力、工业 CO2、CO2 排放，4 个 SSP 情景（SSP126/245/434/460）。

## 项目结构

```
├── AUDIT.md                 # 审计报告
├── CLAUDE.md                # 详细数据规格与代码规范
├── data/                    # 输入数据
│   ├── gcam/                # GCAM 区域输出
│   ├── iea/                 # IEA WORLDBAL 1970-2024
│   ├── ssp/                 # SSP GDP/人口
│   ├── emissions/           # EDGAR 排放数据
│   └── mapping/             # 国家-区域映射
├── compare/                 # 三方案对比
│   ├── common/              # 共享模块 (config, io, mapping, downscale)
│   ├── logit/               # 方案 C
│   ├── kaya/                # 方案 A
│   ├── dscale/              # 方案 B（官方 DSCALE 适配）
│   ├── output/              # 所有输出
│   ├── run_all.py           # 一键运行
│   └── compare_results.py   # 对比可视化
├── DSCALE/                  # 官方 DSCALE 仓库（零修改）
└── docs/audit/              # 详细审计报告
```

## 快速开始

```bash
# 安装依赖
uv sync

# 全量运行（8 指标 × 3 方法 × 4 情景 + 份额 + 图表）
python compare/run_all.py

# 仅 TFC
python -c "from compare.dscale.downscale_tfc import downscale_tfc; downscale_tfc('SSP126')"
```

## 输出

`compare/output/` 下的文件：
- `{method}_{indicator}_downscaled_{scenario}.xlsx` — 降尺度结果（Scenario, iso, Country, Region, 2015...2100）
- `{method}_{indicator}_log.txt` — 守恒校验日志
- `*.png` — 对比图表

## 审计

2026-06 完成 v2 审计（5 级 33 项不变量）。4 项 Bug 修复（含 9 国合成 GDP 注入修复 Kaya/DSCALE 塌缩）。137 项测试全部通过，全量 pipeline（96+72）通过。详见 `docs/audit/audit_v2_report.md`。

## 测试

```bash
uv run pytest compare/tests/ -v   # 137 项测试
```

## IEA 数据覆盖

WORLDBAL_1970_2024.csv 覆盖 148 个可直接匹配的 IEA 国家。另外 35 个小国（非洲 18、亚太 11、美洲 6）在 IEA 中以聚合区域（"Other non-OECD *"）形式报告，代码通过 GCAM 残差+人口拆分自动处理。映射文件 `gcam_country_region1120.xlsx` 中的 `IEA_ctry` 列直接标注了各国家的 IEA 报告状态。

## 数据来源

- GCAM 区域情景：`data/gcam/`
- IEA 能源平衡：`data/iea/WORLDBAL_1970_2024.csv`
- SSP GDP/人口：`data/ssp/`
- EDGAR 排放：`data/emissions/`
- 国家-区域映射：`data/mapping/gcam_country_region1120.xlsx`
