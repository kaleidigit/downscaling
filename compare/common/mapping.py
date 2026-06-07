import re
import unicodedata

import pandas as pd

from .config import MAPPING_PATH

# 不参与匹配的实体 ISO 代码
# 注意: Burkina Faso (bfa), Chad (tcd), Mali (mli), Mauritania (mrt)
# 在旧 IEA xlsx 中缺失，但在 WORLDBAL_1970_2024.csv 中有完整数据，
# 已从排除列表中移除（2026-06-01 B7 审计修复）。
EXCLUDED_ISO = {
    "grl",   # Greenland — 非主权实体
    "pse",   # Palestinian Authority — 非主权实体
    "gib",   # Gibraltar — 非主权实体，WORLDBAL 仅有 Electricity output
    "xkx",   # Kosovo — IEA 数据缺失
    "ssd",   # South Sudan — IEA 数据缺失（2011 年独立）
}

# Other 合并区域关键词
OTHER_KEYWORDS = [
    "other non-oecd africa",
    "other non-oecd americas",
    "other non-oecd asia",
    "other non-oecd asia oceania",
]


def normalize_name(s: str | None) -> str:
    if s is None:
        return ""
    t = str(s).strip()
    t = re.sub(r"\s+", " ", t)
    t = unicodedata.normalize("NFD", t)
    t = "".join(ch for ch in t if unicodedata.category(ch) != "Mn")
    t = t.lower()
    t = re.sub(r'["\']', "", t)
    t = re.sub(r"[()]", "", t)
    t = re.sub(r"\s*,\s*", ",", t)
    t = re.sub(r'[^0-9a-zA-Z一-龥,\/]+', "", t)
    return t.strip()


def load_mapping() -> pd.DataFrame:
    df = pd.read_excel(MAPPING_PATH, engine="openpyxl", dtype=str)
    df = df.fillna("")
    # TWN → CHN
    df.loc[df["iso"].str.lower().str.strip() == "twn", "iso"] = "chn"
    df["iso"] = df["iso"].str.lower().str.strip()
    df["Region"] = df["GCAM Region"]
    df["Region_norm"] = df["Region"].apply(normalize_name)
    return df


def build_region_members(df: pd.DataFrame) -> dict:
    """
    返回 {region_name: [member_dicts]}，每个 member dict 含:
      iso, gcams_country, iea_ctry, iso_ctry, alt_name, candidates (list, 按优先级排序)
    """
    members: dict[str, list[dict]] = {}
    for _, row in df.iterrows():
        iso = str(row.get("iso", "")).lower().strip()
        if iso in EXCLUDED_ISO:
            continue
        region = row["Region"]
        gcams_country = str(row.get("GCAM Country", ""))
        iea_ctry = str(row.get("IEA_ctry", ""))
        iso_ctry = str(row.get("iso_ctry", ""))
        alt = str(row.get("alternative name 1", ""))

        candidates = []
        for v in [gcams_country, iea_ctry, iso_ctry, alt]:
            if v and v not in candidates:
                candidates.append(v)

        if region not in members:
            members[region] = []
        members[region].append({
            "iso": iso,
            "gcams_country": gcams_country,
            "iea_ctry": iea_ctry,
            "iso_ctry": iso_ctry,
            "alt_name": alt,
            "candidates": candidates,
        })
    return members


def is_other_region(name: str) -> bool:
    n = normalize_name(name)
    for kw in OTHER_KEYWORDS:
        if kw in n:
            return True
    return False


def merge_twain_region(df: pd.DataFrame, region_col: str) -> pd.DataFrame:
    """将 GCAM 区域数据中 Taiwan 行合并到 China，然后 groupby sum"""
    df = df.copy()
    n = normalize_name
    df[region_col] = df[region_col].apply(
        lambda v: "China" if n(str(v)) == n("Taiwan") else str(v)
    )
    return df
