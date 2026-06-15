from pathlib import Path

import numpy as np
import pandas as pd

from .config import YEARS, DATA_DIR, IEA_WORLDBAL_PATH, gdp_country_path, pop_country_path
from .mapping import normalize_name, merge_twain_region, load_mapping, build_region_members, EXCLUDED_ISO

# ---------- 名称变体映射 ----------

IEA_VARIANTS = {
    "united states of america": "united states",
    "cote divoire": "cote d ivoire",
    "taiwan": "chinese taipei",
    "peoples republic of china": "china",
    "curacao/netherlands antilles": "curacao/netherlands antilles",
}

# ---------- IEA TFC ----------

def read_iea_tfc(path: Path) -> dict[str, float]:
    """读取 IEA 2015 TFC 基准值，返回 {iso: value_TJ}"""
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    # 筛选 TFC / Total / 2015
    mask = (
        df["Flow"].str.strip().str.lower().eq("total final consumption")
        & df["Product"].str.strip().str.lower().eq("total")
        & df["TIME_PERIOD"].astype(str).str.strip().eq("2015")
    )
    df = df[mask].copy()
    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")

    name_to_iso = _build_iea_name_index()

    # 构建 variant mapping（与模块级 IEA_VARIANTS 一致）
    variants = IEA_VARIANTS

    result: dict[str, float] = {}
    for _, row in df.iterrows():
        country = str(row["Country/Region"]).strip()
        if not country:
            continue
        n = normalize_name(country)
        # apply variant
        n = variants.get(n, n)

        iso = name_to_iso.get(n)
        if iso is None:
            continue
        if iso in EXCLUDED_ISO:
            continue
        val = float(row["OBS_VALUE"])
        if iso in result:
            result[iso] += val
        else:
            result[iso] = val

    return result


# ---------- GCAM TFC ----------

def read_gcam_tfc(path: Path) -> pd.DataFrame:
    """
    读取 GCAM TFC，合并 Taiwan→China，跨 fuel 加总，EJ→TJ。
    返回 DataFrame: columns=[Scenario, Region, 2015, ..., 2100]
    """
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    # 年份列
    year_cols = [c for c in df.columns if str(c).isdigit() and 2015 <= int(c) <= 2100]
    for y in year_cols:
        df[y] = pd.to_numeric(df[y], errors="coerce")

    # Units 检查
    unit = str(df["Units"].iloc[0]).strip() if "Units" in df.columns else ""
    factor = 1_000_000 if "EJ" in unit.upper() else 1.0

    # 合并 Taiwan → China + 聚合
    df = merge_twain_region(df, "Region")
    grp = df.groupby(["Scenario", "Region"], as_index=False)[year_cols].sum()
    for y in year_cols:
        grp[y] = grp[y] * factor
    return grp


# ---------- 国家级 GDP ----------

def read_gdp_country(path: Path) -> pd.DataFrame:
    """
    读取 IIASA 国家 GDP。
    返回 DataFrame: columns=[iso, year_cols...], iso lowercase
    """
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    year_cols = [c for c in df.columns if str(c).isdigit() and 2015 <= int(c) <= 2100]
    for y in year_cols:
        df[y] = pd.to_numeric(df[y], errors="coerce")
    df["iso"] = df["iso"].str.lower().str.strip()
    result = df[["iso"] + year_cols].copy()

    # 为 IIASA SSP 数据库中缺失的国家注入合成 GDP
    scenario = _scenario_from_path(path)
    synthetic = generate_synthetic_gdp(scenario)
    if not synthetic.empty:
        result = pd.concat([result, synthetic], ignore_index=True)
    return result


# ---------- 国家级人口 ----------

def read_pop_country(path: Path) -> pd.DataFrame:
    """
    读取 IIASA 国家人口（REGION 列即 iso），unit: million。
    返回 DataFrame: columns=[iso, year_cols...]
    """
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    year_cols = [c for c in df.columns if str(c).isdigit() and 2015 <= int(c) <= 2100]
    for y in year_cols:
        df[y] = pd.to_numeric(df[y], errors="coerce")
    df["iso"] = df["REGION"].str.lower().str.strip()
    return df[["iso"] + year_cols].copy()


# ---------- 区域级 GDP ----------

def read_gdp_region(path: Path) -> pd.DataFrame:
    """
    读取区域 GDP，合并 Taiwan→China，unit: million 1990$。
    返回 DataFrame: columns=[Region, year_cols...]
    """
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    year_cols = [c for c in df.columns if str(c).isdigit() and 2015 <= int(c) <= 2100]
    for y in year_cols:
        df[y] = pd.to_numeric(df[y], errors="coerce")
    df = merge_twain_region(df, "Region")
    grp = df.groupby("Region", as_index=False)[year_cols].sum()
    return grp


# ---------- 区域级人口 ----------

def read_pop_region(path: Path) -> pd.DataFrame:
    """
    读取区域人口，合并 Taiwan→China，thous → million。
    返回 DataFrame: columns=[Region, year_cols...]
    """
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    # 列名可能是 region（小写）或 Region
    reg_col = "region" if "region" in df.columns else "Region"
    year_cols = [c for c in df.columns if str(c).isdigit() and 2015 <= int(c) <= 2100]
    for y in year_cols:
        df[y] = pd.to_numeric(df[y], errors="coerce")
    df = merge_twain_region(df, reg_col)
    grp = df.groupby(reg_col, as_index=False)[year_cols].sum()
    grp = grp.rename(columns={reg_col: "Region"})
    # thous → million
    for y in year_cols:
        grp[y] = grp[y] / 1000
    return grp


# ---------- 通用 IEA 读取 ----------


def _build_iea_name_index() -> dict[str, str]:
    """构建 IEA 标准化名称 → ISO 代码索引。

    注意：IEA_ctry 中的 "Other..." 是聚合区域名称（覆盖多个国家），
    不能映射到单国。仅使用 GCAM Country 和单国 IEA_ctry。
    """
    mapping = load_mapping()
    members = build_region_members(mapping)
    name_to_iso: dict[str, str] = {}
    for mlist in members.values():
        for m in mlist:
            candidates = [m["gcams_country"]]
            iea = m["iea_ctry"]
            # IEA_ctry 中 "Other..." 是聚合区域，不映射到单国
            if iea and not iea.lower().startswith("other"):
                candidates.append(iea)
            for v in candidates:
                nv = normalize_name(v)
                if nv:
                    name_to_iso[nv] = m["iso"]
    return name_to_iso


def read_iea_generic(
    path: Path,
    flow: str,
    product: str,
    year: str = "2015",
) -> dict[str, float]:
    """通用 IEA 读取——优先使用 WORLDBAL_1970_2024.csv，回退到 xlsx。"""
    # 优先从统一 WORLDBAL CSV 读取
    if IEA_WORLDBAL_PATH.exists() and flow and product:
        result = read_iea_worldbal(flow, product, year=int(year))
        if result:
            return result

    # 回退：从单个 xlsx 文件读取
    df = pd.read_excel(path, engine="openpyxl", dtype=str)

    mask = df["TIME_PERIOD"].astype(str).str.strip().eq(year)
    if flow:
        mask &= df["Flow"].str.strip().str.lower().eq(flow.lower())
    if product:
        mask &= df["Product"].str.strip().str.lower().eq(product.lower())
    df = df[mask].copy()
    if df.empty:
        return {}

    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")

    name_to_iso = _build_iea_name_index()

    result: dict[str, float] = {}
    for _, row in df.iterrows():
        country = str(row["Country/Region"]).strip()
        if not country:
            continue
        n = normalize_name(country)
        n = IEA_VARIANTS.get(n, n)
        iso = name_to_iso.get(n)
        if iso is None or iso in EXCLUDED_ISO:
            continue
        iso = "chn" if iso == "twn" else iso
        val = float(row["OBS_VALUE"])
        result[iso] = result.get(iso, 0.0) + val
    return result


# ---------- 通用 GCAM 读取 ----------

def _parse_year_cols(df: pd.DataFrame) -> list:
    cols = []
    for c in df.columns:
        try:
            if 2015 <= int(c) <= 2100:
                cols.append(c)
        except (ValueError, TypeError):
            pass
    return cols


def read_gcam_generic(
    path: Path,
    filter_col: str | None = None,
    filter_value: str | None = None,
    extra_filters: dict | None = None,
    unit_factor: float = 1_000_000,
) -> pd.DataFrame:
    """通用 GCAM 区域数据读取。

    返回 DataFrame: columns=[Scenario, Region, 2015(int), ..., 2100(int)]
    filter_value=None 时跨所有值加总。
    """
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    year_cols = _parse_year_cols(df)
    # Normalize year columns to int type for consistent access
    rename_map = {}
    for y in year_cols:
        df[y] = pd.to_numeric(df[y], errors="coerce")
        if int(y) != y:
            rename_map[y] = int(y)
    if rename_map:
        df = df.rename(columns=rename_map)
    year_cols = [int(y) for y in year_cols]

    # 额外筛选
    if extra_filters:
        for col, val in extra_filters.items():
            if col in df.columns:
                df = df[df[col].astype(str).str.strip().str.lower() == val.lower()]

    # 主筛选
    if filter_col:
        if filter_col not in df.columns:
            import warnings
            warnings.warn(f"GCAM filter column '{filter_col}' not found in {path.name}; skipping filter")
        elif filter_value:
            df = df[df[filter_col].astype(str).str.strip().str.lower() == filter_value.lower()]

    # Units
    unit = str(df["Units"].iloc[0]).strip() if "Units" in df.columns else ""
    if unit_factor != 1.0:
        factor = unit_factor
    else:
        if not unit:
            import warnings
            warnings.warn(f"GCAM file {path.name} missing 'Units' column; assuming raw unit = target unit (no conversion)")
        unit_upper = unit.upper()
        if "EJ" in unit_upper:
            factor = 1_000_000
        elif "PJ" in unit_upper:
            factor = 1_000
        elif "MTOE" in unit_upper:
            factor = 41_868  # 1 Mtoe ≈ 41.868 TJ
        elif "GWH" in unit_upper:
            factor = 3.6
        elif unit_upper:
            import warnings
            warnings.warn(f"GCAM file {path.name}: unknown unit '{unit}', no conversion applied")
            factor = 1.0
        else:
            factor = 1.0

    # Taiwan → China
    df = merge_twain_region(df, "Region")
    grp = df.groupby(["Scenario", "Region"], as_index=False)[year_cols].sum()
    for y in year_cols:
        grp[y] = grp[y] * factor
    return grp


def read_gcam_fossil_tes(path: Path) -> pd.DataFrame:
    """读取 GCAM 一次能源消费，仅保留化石燃料（oil, natural gas, coal）。"""
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    year_cols = _parse_year_cols(df)
    for y in year_cols:
        df[y] = pd.to_numeric(df[y], errors="coerce")

    fossil = {"a oil", "b natural gas", "c coal"}
    df = df[df["fuel"].astype(str).str.strip().str.lower().isin(fossil)]

    df = merge_twain_region(df, "Region")
    grp = df.groupby(["Scenario", "Region"], as_index=False)[year_cols].sum()
    for y in year_cols:
        grp[y] = grp[y] * 1_000_000  # EJ → TJ
    return grp


# ---------- EDGAR 读取 ----------

def read_edgar_industry(path: Path) -> dict[str, float]:
    """读取 EDGAR 工业 CO2 排放 2015 基准值，返回 {iso: value_Mt}。"""
    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    mask = (
        df["sector"].astype(str).str.strip().str.lower().eq("industry")
        & df["Substance"].astype(str).str.strip().str.lower().eq("co2")
        & df["fossil_bio"].astype(str).str.strip().str.lower().eq("fossil")
    )
    df = df[mask].copy()
    df["2015"] = pd.to_numeric(df["2015"], errors="coerce")

    result: dict[str, float] = {}
    for _, row in df.iterrows():
        iso = str(row["Country_code_A3"]).strip().lower()
        if not iso or iso in EXCLUDED_ISO:
            continue
        iso = "chn" if iso == "twn" else iso
        val = float(row["2015"])
        result[iso] = result.get(iso, 0.0) + val
    return result


def read_edgar_co2(path: Path) -> dict[str, float]:
    """读取 EDGAR CO2 排放 2015 基准值（TOTALS BY COUNTRY sheet），返回 {iso: value_MTC}。"""
    df = pd.read_excel(path, sheet_name="TOTALS BY COUNTRY", engine="openpyxl")
    # 跳过表头行，找到数据起始
    # 格式: Country_code_A3, Name, Substance, Y_2015, ...
    iso_col = "Country_code_A3"
    year_col = "Y_2015"

    if iso_col not in df.columns:
        # 尝试在首几行找到表头
        for skip in range(0, 10):
            try:
                df2 = pd.read_excel(path, sheet_name="TOTALS BY COUNTRY", engine="openpyxl", skiprows=skip)
                if iso_col in df2.columns:
                    df = df2
                    break
            except Exception:
                continue

    if iso_col not in df.columns:
        return {}

    result: dict[str, float] = {}
    for _, row in df.iterrows():
        try:
            iso = str(row[iso_col]).strip().lower()
            if not iso or len(iso) != 3 or iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            val = float(row.get(year_col, 0) or 0)
            if val > 0:
                result[iso] = result.get(iso, 0.0) + val
        except (ValueError, AttributeError):
            continue
    return result


# ---------- IEA Other 区域值（用于人口拆分）----------

def read_iea_other_values(path: Path, flow: str, product: str, year: str = "2015") -> dict[str, float]:
    """读取 IEA 中 Other 合并区域的值，返回 {normalized_name: value_TJ}。"""
    from .config import IndicatorConfig

    OTHER_KEYWORDS_LIST = [
        "other non-oecd africa", "other non-oecd americas",
        "other non-oecd asia oceania", "other non-oecd asia",
    ]

    df = pd.read_excel(path, engine="openpyxl", dtype=str)
    mask = df["TIME_PERIOD"].astype(str).str.strip().eq(year)
    if flow:
        mask &= df["Flow"].str.strip().str.lower().eq(flow.lower())
    if product:
        mask &= df["Product"].str.strip().str.lower().eq(product.lower())
    df = df[mask].copy()
    if df.empty:
        return {}

    df["OBS_VALUE"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")

    result: dict[str, float] = {}
    for _, row in df.iterrows():
        name = normalize_name(str(row.get("Country/Region", "")))
        for kw in OTHER_KEYWORDS_LIST:
            if kw in name:
                # 映射到统一 key
                if "africa" in kw:
                    key = normalize_name("Other non-OECD Africa")
                elif "americas" in kw:
                    key = normalize_name("Other non-OECD Americas")
                else:
                    key = normalize_name("Other non-OECD Asia Oceania")
                result[key] = result.get(key, 0.0) + float(row["OBS_VALUE"])
                break
    return result


# ---------- IEA 多年度历史数据（2015-2020）----------

# ── WORLDBAL 1970-2024 主数据源 ──────────────────────────

# 在 IEA 层面排除的历史实体（非现代国家，无 ISO 对应）
EXCLUDED_IEA_ENTITIES = {
    "Former Soviet Union",
    "Former Yugoslavia",
}

# WORLDBAL 国家名 → 目标实体（用于合并/映射）
WORLDBAL_NAME_MERGE = {
    "Chinese Taipei": "China Region (P.R. of China and Hong Kong, China)",
}


def read_iea_worldbal(
    flow: str,
    product: str,
    year: int | None = None,
) -> dict[str, float]:
    """从统一的 WORLDBAL_1970_2024.csv 读取 IEA 数据。

    自动处理:
      - Former Soviet Union / Yugoslavia → 排除
      - Chinese Taipei → 合并到 China Region
      - Other non-OECD Americas → 保留为聚合区域

    Args:
        flow: Flow 筛选值 (如 "Total final consumption")
        product: Product 筛选值 (如 "Total")
        year: 年份过滤，None 返回所有年份的聚合

    Returns:
        {iso: value_TJ} 字典 (单年) 或 {iso: {year: value_TJ}} (多年)
    """
    import pandas as pd

    name_to_iso = _build_iea_name_index()

    result: dict[str, float] = {}
    china_buffer: dict[int, float] = {}

    for chunk in pd.read_csv(IEA_WORLDBAL_PATH, dtype=str, chunksize=500000):
        mask = (
            chunk["Flow"].str.strip().str.lower().eq(flow.lower())
            & chunk["Product"].str.strip().str.lower().eq(product.lower())
        )
        if year is not None:
            mask &= chunk["TIME_PERIOD"].astype(str).str.strip().eq(str(year))
        filtered = chunk[mask].copy()
        if filtered.empty:
            continue

        filtered["OBS_VALUE"] = pd.to_numeric(filtered["OBS_VALUE"], errors="coerce")
        filtered["TIME_PERIOD"] = filtered["TIME_PERIOD"].astype(int)

        for _, row in filtered.iterrows():
            name = str(row["Country/Region"]).strip()
            if not name or name in EXCLUDED_IEA_ENTITIES:
                continue

            # Chinese Taipei → buffer for China merge
            if name in WORLDBAL_NAME_MERGE:
                target = WORLDBAL_NAME_MERGE[name]
                y = int(row["TIME_PERIOD"])
                china_buffer[y] = china_buffer.get(y, 0.0) + float(row["OBS_VALUE"])
                continue

            n = normalize_name(name)
            n = IEA_VARIANTS.get(n, n)
            iso = name_to_iso.get(n)
            if iso is None or iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            val = float(row["OBS_VALUE"])

            if year is not None:
                result[iso] = result.get(iso, 0.0) + val
            else:
                y = int(row["TIME_PERIOD"])
                if iso not in result:
                    result[iso] = {}
                result[iso][y] = result[iso].get(y, 0.0) + val

    # 将 Chinese Taipei 的缓冲值加到 China
    iso_china = name_to_iso.get(
        normalize_name(WORLDBAL_NAME_MERGE["Chinese Taipei"])
    )
    if iso_china is None:
        iso_china = "chn"
    if year is not None:
        if year in china_buffer:
            result[iso_china] = result.get(iso_china, 0.0) + china_buffer[year]
    else:
        if iso_china not in result:
            result[iso_china] = {}
        for y, v in china_buffer.items():
            result[iso_china][y] = result[iso_china].get(y, 0.0) + v

    return result


def read_iea_historical_tfc() -> dict[str, dict[int, float]]:
    """读取 IEA 2015-2020 多年度 TFC 数据。

    Returns:
        {iso: {2015: value_TJ, 2016: ..., 2020: value_TJ}}
    """
    return read_iea_worldbal("Total final consumption", "Total")


def compute_ei_trend_2015_2020(
    iea_hist: dict[str, dict[int, float]],
    scenario: str,
) -> dict[str, float]:
    """从 IEA 2015-2020 数据计算各国能源强度年均变化率。

    使用 2015 和 2020 两个端点（均可从 SSP GDP 获取），
    计算能源强度 CAGR: (EI_2020 / EI_2015)^(1/5) - 1。

    Returns:
        {iso: yearly_ei_change_rate}  (-0.05 到 +0.02 截断)
    """
    gdp = read_gdp_country(gdp_country_path(scenario)).set_index("iso")
    pop = read_pop_country(pop_country_path(scenario)).set_index("iso")

    trends: dict[str, float] = {}
    for iso, annual in iea_hist.items():
        tfc_2015 = annual.get(2015, 0)
        tfc_2020 = annual.get(2020, 0)
        if tfc_2015 <= 0 or tfc_2020 <= 0:
            trends[iso] = 0.0
            continue

        g_2015 = float(gdp.loc[iso, 2015]) if iso in gdp.index else 0.0
        g_2020 = float(gdp.loc[iso, 2020]) if iso in gdp.index else 0.0
        if g_2015 <= 0 or g_2020 <= 0:
            trends[iso] = 0.0
            continue

        ei_2015 = tfc_2015 / g_2015
        ei_2020 = tfc_2020 / g_2020
        if ei_2015 <= 0:
            trends[iso] = 0.0
            continue

        cagr = (ei_2020 / ei_2015) ** (1.0 / 5.0) - 1.0
        # 截断极端值：EI 年变化率不超过 -5% 或 +2%
        cagr = max(-0.05, min(0.02, cagr))
        trends[iso] = cagr

    return trends


# ---------- 输出 ----------

def write_output(df: pd.DataFrame, method: str, scenario: str) -> Path:
    """按统一格式写 Excel，返回文件路径（兼容旧接口）。"""
    from .config import OUTPUT_DIR
    return _write_output_generic(df, method, scenario, "TFC")


def write_output_for(df: pd.DataFrame, method: str, scenario: str, prefix: str) -> Path:
    """按统一格式写 Excel，指定 prefix。"""
    from .config import OUTPUT_DIR
    return _write_output_generic(df, method, scenario, prefix)


def _write_output_generic(df: pd.DataFrame, method: str, scenario: str, prefix: str) -> Path:
    from .config import OUTPUT_DIR, YEARS

    out_path = OUTPUT_DIR / f"{method}_{prefix}_downscaled_{scenario}.xlsx"
    year_cols = [y for y in YEARS if y in df.columns]
    cols = ["Scenario", "iso", "Country", "Region"] + year_cols
    df = df[[c for c in cols if c in df.columns]]
    df.to_excel(out_path, index=False)
    return out_path


# ── SSP 完整数据库 (1950-2100) ──────────────────────────

def read_ssp_database_historical(
    variable: str,
    iso_set: set[str] | None = None,
) -> dict[str, dict[int, float]]:
    """从 SSP_database_v9.csv 读取指定变量的完整历史+未来序列。

    返回 {iso: {year: value}}，年份为 5 年间隔 (1950-2100)。

    Args:
        variable: VARIABLE 列筛选值 (如 'GDP|PPP', 'Population')
        iso_set: 可选，仅返回指定 ISO 集合的国家
    """
    import pandas as pd
    from .config import SSP_DATABASE_PATH

    df = pd.read_csv(SSP_DATABASE_PATH, dtype=str, skiprows=6)
    df = df[df["VARIABLE"].str.strip() == variable].copy()

    year_cols = [c for c in df.columns if c.isdigit()]
    result: dict[str, dict[int, float]] = {}

    for _, row in df.iterrows():
        iso = str(row.get("REGION", "")).strip().lower()
        scenario = str(row.get("SCENARIO", "")).strip()
        if not iso or len(iso) != 3:
            continue
        if iso_set and iso not in iso_set:
            continue

        # 对所有 SSP 情景取平均（作为"历史"估计）
        if iso not in result:
            result[iso] = {}
        for y in year_cols:
            v = pd.to_numeric(row[y], errors="coerce")
            if pd.notna(v) and v > 0:
                yr = int(y)
                if yr <= 2015:
                    # 历史年份直接取平均
                    if yr not in result[iso]:
                        result[iso][yr] = []
                    result[iso][yr].append(v)

    # 对多年取平均（多个 SSP 情景+模型）
    for iso in result:
        for yr in list(result[iso].keys()):
            vals = result[iso][yr]
            if isinstance(vals, list):
                result[iso][yr] = sum(vals) / len(vals)

    return result


# ── USDA 历史 GDP (1969-2017) ─────────────────────────

def read_usda_gdp_historical() -> dict[str, dict[int, float]]:
    """读取 USDA GDP 历史数据，返回 {iso: {year: value_billion_2010USD}}。"""
    import pandas as pd

    df = pd.read_csv(DATA_DIR / "ssp" / "USDA_GDP_MER.csv", dtype=str, skiprows=6)
    year_cols = [c for c in df.columns if c.isdigit()]
    result: dict[str, dict[int, float]] = {}
    for _, row in df.iterrows():
        iso = str(row.get("iso", "")).strip().lower()
        if not iso or len(iso) != 3:
            continue
        result[iso] = {}
        for y in year_cols:
            v = pd.to_numeric(row[y], errors="coerce")
            if pd.notna(v) and v > 0:
                result[iso][int(y)] = float(v)
    return result


# ── UN 历史人口 (1950-2020) ───────────────────────────

def read_un_population_historical() -> dict[str, dict[int, float]]:
    """读取 UN 人口历史数据，返回 {iso: {year: value_million}}。

    UN 单位是 thousands，返回时自动转为 million。
    列: Country, Region, Sex, Scenario, Year, Value
    """
    import pandas as pd

    df = pd.read_csv(DATA_DIR / "ssp" / "UN_popTot.csv", dtype=str, skiprows=7)
    df = df[df["Sex"].str.strip() == "M+F"].copy()
    df = df[df["Scenario"].str.strip() == "EST"].copy()
    df["Year"] = pd.to_numeric(df["Year"], errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    df = df.dropna(subset=["Year", "Value"])

    # 构建 Country→iso 映射 (Country 列是 ISO-3 大写)
    result: dict[str, dict[int, float]] = {}
    for _, row in df.iterrows():
        iso = str(row.get("Country", "")).strip().lower()
        if not iso or len(iso) != 3:
            continue
        y = int(row["Year"])
        v = float(row["Value"])
        if iso not in result:
            result[iso] = {}
        result[iso][y] = v / 1000.0  # thousands → million

    return result


# ── 合成 GDP（填补 IIASA SSP 数据缺口）───────────────────

def _scenario_from_path(path: Path) -> str:
    """从 GDP 文件路径中提取情景名（如 GDP_ssp126.xlsx → SSP126）。"""
    import re
    m = re.search(r'[Ss][Ss][Pp](\d{3})', path.stem)
    if m:
        return f"SSP{m.group(1)}"
    return "SSP126"


def generate_synthetic_gdp(scenario: str) -> pd.DataFrame:
    """为 IIASA SSP GDP 缺失的 9 国生成合成 GDP。

    方法：区域人均 GDP 增长 × 国家人口。
    2015 年基准水平基于 USDA 历史数据相对于区域的比值（如有），
    或使用区域平均水平。

    返回 DataFrame: columns=[iso, 2015, 2020, ..., 2100]，若无缺口国家则返回空。
    """
    mapping = load_mapping()
    members_by_region = build_region_members(mapping)

    # ---- 加载参考数据 ----
    gdp_path = gdp_country_path(scenario)
    gdp_ref = pd.read_excel(gdp_path, engine="openpyxl", dtype=str)
    year_cols = [c for c in gdp_ref.columns if str(c).isdigit() and 2015 <= int(c) <= 2100]
    for y in year_cols:
        gdp_ref[y] = pd.to_numeric(gdp_ref[y], errors="coerce")
    gdp_ref["iso"] = gdp_ref["iso"].str.lower().str.strip()
    ref_isos = set(gdp_ref["iso"].unique())

    pop = read_pop_country(pop_country_path(scenario))
    pop_by_iso = pop.set_index("iso")

    # ---- 确定缺口国家 ----
    all_mapped_isos: set[str] = set()
    for mlist in members_by_region.values():
        for m in mlist:
            iso = m["iso"]
            if iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            all_mapped_isos.add(iso)

    gap_isos = all_mapped_isos - ref_isos
    if not gap_isos:
        return pd.DataFrame()

    # ---- 加载 USDA 和 UN 历史数据（用于相对财富比）----
    usda = read_usda_gdp_historical()
    un_pop = read_un_population_historical()

    # ---- 构建 iso -> region 映射 ----
    iso_to_region: dict[str, str] = {}
    for region_name, mlist in members_by_region.items():
        for m in mlist:
            iso = m["iso"]
            if iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            iso_to_region[iso] = region_name

    # 按区域分组缺口国家
    gap_by_region: dict[str, set[str]] = {}
    for iso in gap_isos:
        region = iso_to_region.get(iso)
        if region:
            gap_by_region.setdefault(region, set()).add(iso)

    # ---- 全局参考人均 GDP（回退用）----
    global_ref_isos = ref_isos - gap_isos
    gdp_ref_indexed = gdp_ref.set_index("iso")
    global_gdp_sum = gdp_ref_indexed.loc[gdp_ref_indexed.index.intersection(global_ref_isos), year_cols].sum()
    global_pop_sum = pop_by_iso.loc[pop_by_iso.index.intersection(global_ref_isos), year_cols].sum()
    global_pcap = global_gdp_sum / global_pop_sum.clip(1e-10)

    rows = []
    for region, gap_set in gap_by_region.items():
        # 参考国家（该区域中有 IIASA GDP 的非缺口国家）
        region_ref_isos = {iso for iso in iso_to_region if iso_to_region[iso] == region and iso in ref_isos and iso not in gap_isos}

        if region_ref_isos:
            ref_gdp = gdp_ref_indexed.loc[gdp_ref_indexed.index.intersection(region_ref_isos), year_cols].sum()
            ref_pop = pop_by_iso.loc[pop_by_iso.index.intersection(region_ref_isos), year_cols].sum()
        else:
            ref_gdp = global_gdp_sum
            ref_pop = global_pop_sum

        pcap_R = ref_gdp / ref_pop.clip(1e-10)
        growth_R = pcap_R / pcap_R.get(2015, global_pcap.get(2015, 1.0)).clip(1e-10)

        # USDA 参考集（用于相对财富比）
        region_ref_with_usda = region_ref_isos & set(usda.keys())
        usda_pcap_R_2015 = 0.0
        if region_ref_with_usda:
            usda_gdp_sum = sum(usda[iso].get(2015, 0.0) for iso in region_ref_with_usda)
            usda_pop_sum = sum(un_pop.get(iso, {}).get(2015, 0.0) for iso in region_ref_with_usda)
            usda_pcap_R_2015 = usda_gdp_sum / max(usda_pop_sum, 1e-10)

        for iso in sorted(gap_set):
            if iso not in pop_by_iso.index:
                continue
            pop_c = pop_by_iso.loc[iso, year_cols]

            # 基准人均 GDP
            if iso in usda and usda_pcap_R_2015 > 0:
                usda_pcap_c = usda[iso].get(2015, 0.0)
                un_pop_c = un_pop.get(iso, {}).get(2015, 0.0)
                if un_pop_c > 0 and usda_pcap_c > 0:
                    ratio = (usda_pcap_c / un_pop_c) / usda_pcap_R_2015
                    ratio = np.clip(ratio, 0.1, 10.0)
                    base_pcap = ratio * pcap_R.get(2015, global_pcap.get(2015, 0.0))
                else:
                    base_pcap = pcap_R.get(2015, global_pcap.get(2015, 0.0))
            else:
                base_pcap = pcap_R.get(2015, global_pcap.get(2015, 0.0))

            # 前向投影
            gdp_c = base_pcap * growth_R * pop_c
            gdp_c = gdp_c.clip(lower=0.0)

            row = {"iso": iso}
            for y in year_cols:
                row[int(y)] = round(float(gdp_c.get(y, 0.0)), 6)
            rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    out_cols = ["iso"] + [int(y) for y in year_cols]
    return df[out_cols]
