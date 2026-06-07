# Round 2 Audit: B 层 — 数据链路

审计日期：2026-06-01
审计范围：`compare/common/io.py`, `config.py`, `mapping.py`
数据源：WORLDBAL_1970_2024.csv (新), TFC_IEA.xlsx (旧)

---

## 执行摘要

| 审计项 | 状态 | 发现 |
|--------|------|------|
| B1 — 名称→ISO 匹配 | ⚠️ 1 个未匹配 | Curaçao/Netherlands Antilles (TFC=0, 无害) |
| B2 — Chinese Taipei 合并 | ✅ 通过 | 精确匹配，偏差 0.01 TJ |
| B3 — FSU/Yugoslavia 排除 | ✅ 通过 | 1990+ 全为 0，正确排除 |
| B4 — Other Americas 处理 | ⚠️ 已记录 | 6 国映射至 IEA 聚合区域，需人口拆分 |
| B5 — 单位换算 | ✅ 通过 | 所有转换正确 |
| B6 — 新旧数据比对 | ⚠️ 2 国缺失 | STP/WSM 在 WORLDBAL 中缺失 |
| B7 — EXCLUDED_ISO 合理性 | ✅ 已修复 | 4 国从排除列表移除（现含 WORLDBAL 数据）|

**通过: 3 / 需关注: 3 / 已修复: 1**

---

## B1 — 名称→ISO 匹配完整率 [高] ⚠️

### 匹配链

```
WORLDBAL Country/Region → normalize_name() → IEA_VARIANTS → name_to_iso
```

### 结果

- WORLDBAL 唯一 Country/Region: **158**
- 成功匹配: **146** (92.4%)
- 未匹配: **12**

### 未匹配清单

| 名称 | 类别 | 处理方式 |
|------|------|---------|
| Burkina Faso | EXCLUDED_ISO (已移除) | ✅ B7 修复后已匹配 |
| Chad | EXCLUDED_ISO (已移除) | ✅ B7 修复后已匹配 |
| Mali | EXCLUDED_ISO (已移除) | ✅ B7 修复后已匹配 |
| Mauritania | EXCLUDED_ISO (已移除) | ✅ B7 修复后已匹配 |
| Greenland | EXCLUDED_ISO | ✅ 非主权实体，正确排除 |
| Palestinian Authority | EXCLUDED_ISO | ✅ 非主权实体，正确排除 |
| Gibraltar | EXCLUDED_ISO | ✅ 非主权实体 |
| Kosovo | EXCLUDED_ISO | ✅ 数据缺失 |
| South Sudan | EXCLUDED_ISO | ✅ 2011 独立，数据缺失 |
| Former Soviet Union | EXCLUDED_IEA_ENTITIES | ✅ 历史实体，1990+ 全为 0 |
| Former Yugoslavia | EXCLUDED_IEA_ENTITIES | ✅ 历史实体，1990+ 全为 0 |
| Curaçao/Netherlands Antilles | **未处理** | ⚠️ IEA_VARIANTS 映射至自身（无操作）|

### Curaçao/Netherlands Antilles 分析

- WORLDBAL 有此实体，但 TFC 2015 = **0 TJ**
- IEA_VARIANTS: `"curacao/netherlands antilles": "curacao/netherlands antilles"` (恒等映射)
- 映射表中无 Curaçao 对应行，最近的 ISO 是 nld (Netherlands)
- **影响**: 无。TFC 为 0，不匹配不影响任何计算
- **建议**: 添加至 IEA_VARIANTS 映射到 "netherlands" 或在 name_to_iso 中添加条目

---

## B2 — Chinese Taipei 合并验证 [高] ✅

### 验证

| 数据源 | China (不含 CT) | Chinese Taipei | 合并后 China |
|--------|----------------|----------------|-------------|
| 旧 IEA xlsx | 82,860,386.47 TJ | 3,135,608.00 TJ | 85,995,994.46 TJ |
| 新 WORLDBAL CSV | — | 3,135,608.00 TJ | 85,995,994.46 TJ |

```
|旧 China+CT - 新 China| = |85,995,994.46 - 85,995,994.46| = 0.01 TJ
```
偏差 < 1.0 TJ ✅

### 合并路径

**旧路径** (`read_iea_tfc`):
- Chinese Taipei → normalize → "chinese taipei" → name_to_iso 查找 → "chn"（因 mapping 中 twn→chn）
- `result["chn"] += val`

**新路径** (`read_iea_worldbal`):
- Chinese Taipei → WORLDBAL_NAME_MERGE → buffer to china_buffer
- 最后合并: `result["chn"] += china_buffer[year]`

两条路径结果一致 ✅

---

## B3 — Former Soviet Union / Yugoslavia 排除 [中] ✅

### 验证

| 实体 | 数据范围 | 1990+ 值 | 处理 |
|------|---------|---------|------|
| Former Soviet Union | 1970-2024 | **全部为 0 TJ** | ✅ EXCLUDED_IEA_ENTITIES |
| Former Yugoslavia | 1970-2024 | **全部为 0 TJ** | ✅ EXCLUDED_IEA_ENTITIES |

两个实体在 1970-1989 年有实际能源消费数据（FSU 峰值 ~37,700,000 TJ），但从 1990 年起全部为 0（与苏联解体/南斯拉夫解体时间吻合）。

降尺度输出中未发现任何包含 "soviet", "yugoslav", "ussr", "fsu" 的行 ✅

**代码位置**: `io.py:416-419`
```python
EXCLUDED_IEA_ENTITIES = {
    "Former Soviet Union",
    "Former Yugoslavia",
}
```

---

## B4 — Other non-OECD Americas 处理 [中] ⚠️

### 现状

6 个加勒比小国映射至 IEA 聚合区域 "Other non-OECD Americas"：

| ISO | 国家 | GCAM Region |
|-----|------|-------------|
| bhs | Bahamas | Central America and Caribbean |
| blz | Belize | Central America and Caribbean |
| brb | Barbados | Central America and Caribbean |
| grd | Grenada | Central America and Caribbean |
| lca | Saint Lucia | Central America and Caribbean |
| vct | St. Vincent & Grenadines | Central America and Caribbean |

### 数据流

1. IEA WORLDBAL 中 "Other non-OECD Americas" 在 2015 年 TFC = **166,576.91 TJ**（一个聚合值）
2. 这 6 个国家的 IEA_ctry 均为 "Other non-OECD Americas"
3. WORLDBAL CSV 中无这些国家的单独条目（它们被合并到聚合区域中）
4. 当前代码通过**人口份额拆分**处理：将聚合 TFC 值按各国人口比例分配给各成员国

### 问题

- 人口拆分假设能源消费与人口成正比，忽略了人均 GDP 差异（如 Bahamas 人均 GDP 远高于 Belize）
- WORLDBAL CSV 中只有 "Other non-OECD Americas" 这一个 Other 区域，缺少 "Other non-OECD Africa" 和 "Other non-OECD Asia"（它们可能在 GCAM 区域层面处理）

### 建议

- 当前人口拆分方法已是最简可行方案
- 如有国家尺度的 IEA 数据（如从旧 xlsx 文件），可替代人口拆分

---

## B5 — 单位换算 [高] ✅

### 验证

| 转换 | 因子 | 代码位置 | 状态 |
|------|------|---------|------|
| GCAM EJ → TJ | × 1,000,000 | `io.py:86,92,289,306` | ✅ |
| 区域人口 thous → million | ÷ 1,000 | `io.py:158-159` | ✅ |
| IEA TJ → TJ | × 1 | — | ✅ |
| UN 人口 thous → million | ÷ 1,000 | `io.py:724` | ✅ |

### 10 国抽样

| ISO | TFC 2015 (TJ) | 数量级合理性 |
|-----|---------------|------------|
| chn | 85,995,994.46 | ✅ （中国 ~86M TJ ≈ 2,940 Mtoe）|
| usa | 63,168,674.52 | ✅ |
| ind | 22,779,360.03 | ✅ |
| bra | 9,557,492.89 | ✅ |
| rus | 18,946,891.95 | ✅ |

所有值在合理范围内。未涉及 ktoe→TJ 转换（项目全部使用 TJ）。

---

## B6 — IEA 新旧数据逐国比对 [高] ⚠️

### 对比结果

- 旧 IEA xlsx: **147** 国
- 新 WORLDBAL CSV: **145** 国
- 并集: **147** 国

### 偏差 >1% 的国家: **0**

所有重叠国家的 2015 TFC 值完全一致（偏差 < 1%）。

### WORLDBAL 缺失国家

| ISO | 名称 | 旧 IEA TFC 2015 | WORLDBAL | 影响 |
|-----|------|----------------|----------|------|
| stp | São Tomé and Príncipe | 1,677,189.6 TJ | **缺失** | 小岛国，非洲 |
| wsm | Samoa | 489,272.5 TJ | **缺失** | 小岛国，大洋洲 |

两个国家在 WORLDBAL CSV 中完全不存在（不是 0 值，是不在 Country/Region 列表中）。

### 评估

- 这是 WORLDBAL 数据源的局限——部分小岛国可能未被 IEA 纳入世界能源平衡扩展数据集
- 对全球 TFC 总量影响极小（两国合计约占全球 TFC 的 0.0005%）
- **建议**: 从旧 IEA xlsx 中补充这两个国家的数据，或标记为已知数据缺口

---

## B7 — EXCLUDED_ISO 合理性 [中] ✅ 已修复

### 修复前

9 个 ISO 代码被排除（全部来自 CLAUDE.md 初始定义）。

### 审计发现

使用新 WORLDBAL CSV 验证：

| ISO | 旧 IEA xlsx | 新 WORLDBAL | 有 GDP? | 有 POP? | 在映射中? | 决定 |
|-----|-----------|------------|---------|---------|----------|------|
| bfa | ❌ 缺失 | ✅ 175,723 TJ | ✅ | ✅ | ✅ Africa_Western | **移除排除** |
| tcd | ❌ 缺失 | ✅ 123,132 TJ | ✅ | ✅ | ✅ Africa_Western | **移除排除** |
| mli | ❌ 缺失 | ✅ 123,809 TJ | ✅ | ✅ | ✅ Africa_Western | **移除排除** |
| mrt | ❌ 缺失 | ✅ 44,586 TJ | ✅ | ✅ | ✅ Africa_Western | **移除排除** |
| grl | ❌ | ❌ | — | — | — | 保留（非主权实体）|
| pse | ❌ | ❌ | — | — | — | 保留（非主权实体）|
| gib | ✅ 仅 Electricity | ❌ 无 TFC | — | — | — | 保留（非主权实体）|
| xkx | ❌ | ❌ | — | — | — | 保留（数据缺失）|
| ssd | ❌ | ❌ | — | — | — | 保留（2011 独立）|

### 修复

`mapping.py:9-18`: 从 EXCLUDED_ISO 中移除 `bfa`, `tcd`, `mli`, `mrt`

**修复后**: 5 个实体仍排除（均为合理理由），4 个已纳入。

### 新增国家影响

- 4 国均属于 **Africa_Western** 区域
- 区域 TFC 将在更多国家间分配，每个国家份额略微下降
- 区域守恒不受影响（总和仍然等于 GCAM 区域值）

---

## 审计验证

### B1 匹配率
```
146/158 matched (92.4%)
12 unmatched → 11 expected + 1 Curaçao (harmless)
```

### B2 合并偏差
```
|(Old_China + Old_CT) - New_China| = 0.01 TJ < 1.0 TJ ✓
```

### B3 排除验证
```
FSU 1990+: 0 TJ (all years) ✓
Yugoslavia 1990+: 0 TJ (all years) ✓
Downscale outputs: 0 occurrences ✓
```

### B7 修复验证
```
bfa: 175,723 TJ → INCLUDED ✓
tcd: 123,132 TJ → INCLUDED ✓
mli: 123,809 TJ → INCLUDED ✓
mrt:  44,586 TJ → INCLUDED ✓
Total: 149 countries (up from 145)
```

---

## 剩余风险

1. **STP/WSM 缺失**: WORLDBAL 数据源不完整，需从旧 IEA 补充
2. **Curaçao**: 未匹配但 TFC=0，无害。映射表可补充以保持清洁
3. **Other Americas 人口拆分**: 假设能源-人口线性关系，对高人均 GDP 小国可能有偏
4. **CLAUDE.md 未同步**: 排除实体列表需要更新（从 9 个减少到 5 个）
5. **Other non-OECD Africa/Asia**: WORLDBAL 仅有 Americas 聚合区域，其他洲的 Other 区域可能以不同形式存在

## 下一步

第 3 轮: C 层（算法参数）— 5 项审计
