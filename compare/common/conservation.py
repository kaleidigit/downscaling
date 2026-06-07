from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd

from .config import YEARS, OUTPUT_DIR


def check_regional_conservation(
    result: pd.DataFrame,
    gcam: pd.DataFrame,
) -> str:
    """对每个区域/年份检查 国家合计 vs GCAM 区域值，返回文本报告"""
    lines: List[str] = []
    year_cols = [y for y in YEARS if y in result.columns]
    max_dev = 0.0

    for _, g_row in gcam.iterrows():
        region = g_row["Region"]
        scenario = g_row.get("Scenario", "")
        rdf = result[(result["Region"] == region) & (result["Scenario"] == scenario)]
        if rdf.empty:
            continue
        for y in year_cols:
            if y not in g_row:
                continue
            target = float(g_row[y])
            allocation = float(rdf[y].sum())
            dev = abs(target - allocation)
            if dev > max_dev:
                max_dev = dev

    lines.append(f"区域守恒: 最大偏差 = {max_dev:.6f} TJ")
    return "\n".join(lines)


def check_global_conservation(
    result: pd.DataFrame,
    gcam: pd.DataFrame,
) -> str:
    """全局守恒校验：所有国家合计 ≈ GCAM 全球合计"""
    lines: List[str] = []
    year_cols = [y for y in YEARS if y in result.columns]

    for y in year_cols:
        country_sum = float(result[y].sum())
        gcam_sum = float(gcam[y].sum())
        dev = abs(gcam_sum - country_sum)
        lines.append(f"{y}: 国家合计={country_sum:.2f} TJ, GCAM={gcam_sum:.2f} TJ, 偏差={dev:.6f} TJ")

    return "\n".join(lines)


def write_log(method: str, reports: list[str], path: Path | None = None) -> Path:
    """写日志文件，reports 为字符串列表，每段间空行分隔"""
    if path is None:
        path = OUTPUT_DIR / f"{method}_TFC_log.txt"
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"=== {method} TFC 降尺度日志 ===\n")
        f.write(f"运行时间: {datetime.now().isoformat()}\n\n")
        for r in reports:
            f.write(r)
            f.write("\n\n")
    return path
