"""一键运行全部 SDG 指标三方案降尺度 + 对比可视化。"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from compare.common.config import SCENARIOS, INDICATORS, DERIVED_SHARES, YEARS
from compare.common.downscale import run_indicator
from compare.common.io import write_output_for

METHODS = ["logit", "kaya", "dscale"]

# 只降尺度的无界量指标（跳过份额/派生指标）
UNBOUNDED_KEYS = list(INDICATORS.keys())


def main():
    start = time.time()
    results: dict[str, dict] = {}

    # ═══════════════════════════════════════════
    # Phase 1: 无界量降尺度
    # ═══════════════════════════════════════════
    n_total = len(UNBOUNDED_KEYS) * len(METHODS) * len(SCENARIOS)
    print("=" * 70)
    print(f"Phase 1: Downscaling ({len(UNBOUNDED_KEYS)} indicators × {len(METHODS)} methods × {len(SCENARIOS)} scenarios = {n_total} runs)")
    print("=" * 70)

    count = 0
    for key in UNBOUNDED_KEYS:
        cfg = INDICATORS[key]
        for method in METHODS:
            for sc in SCENARIOS:
                label = f"{method}_{key}_{sc}"
                t0 = time.time()
                try:
                    df = run_indicator(method, sc, cfg)
                    elapsed = time.time() - t0
                    results[label] = {"status": "OK", "rows": len(df), "time": elapsed}
                    count += 1
                    print(f"  [{count}/{n_total}] {label}: OK ({len(df)} rows, {elapsed:.1f}s)")
                except Exception as e:
                    elapsed = time.time() - t0
                    results[label] = {"status": "FAIL", "error": str(e), "time": elapsed}
                    count += 1
                    print(f"  [{count}/{n_total}] {label}: FAIL ({e})")

    ok = sum(1 for v in results.values() if v["status"] == "OK")
    fail = sum(1 for v in results.values() if v["status"] == "FAIL")
    p1_time = time.time() - start
    print(f"\n  Phase 1: {ok} OK / {fail} FAIL ({p1_time:.1f}s)")

    if fail > 0:
        print("  Failures:")
        for k, v in results.items():
            if v["status"] == "FAIL":
                print(f"    {k}: {v['error']}")
        return 1

    # ═══════════════════════════════════════════
    # Phase 2: 派生份额指标
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print(f"Phase 2: Derived shares ({len(DERIVED_SHARES)} indicators × {len(METHODS)} methods × {len(SCENARIOS)} scenarios)")
    print("=" * 70)

    from compare.common.downscale import (
        compute_logit_share, compute_kaya_share, compute_dscale_share, load_gcam,
    )

    share_functions = {
        "logit": compute_logit_share,
        "kaya": compute_kaya_share,
        "dscale": compute_dscale_share,
    }

    share_count = 0
    for share_key, spec in DERIVED_SHARES.items():
        num_key = spec["numerator"]
        den_key = spec["denominator"]
        cfg_num = INDICATORS.get(num_key)
        cfg_den = INDICATORS.get(den_key)
        if cfg_num is None or cfg_den is None:
            continue
        for method in METHODS:
            for sc in SCENARIOS:
                try:
                    df_num = _load_output(method, num_key, sc)
                    df_den = _load_output(method, den_key, sc)

                    gcam_num = load_gcam(cfg_num, sc)
                    gcam_den = load_gcam(cfg_den, sc)
                    df_share = share_functions[method](df_num, df_den, gcam_num, gcam_den, sc)

                    write_output_for(df_share, method, sc, share_key)
                    share_count += 1
                except Exception as e:
                    if method == "logit":
                        print(f"    WARNING {method}_{share_key}_{sc}: {e}")

    print(f"  Phase 2: {share_count} share files written")

    # ═══════════════════════════════════════════
    # Phase 3: 可视化
    # ═══════════════════════════════════════════
    print(f"\n{'=' * 70}")
    print("Phase 3: Visualization")
    print("=" * 70)
    try:
        from compare.compare_results import generate_all_plots
        plot_paths = generate_all_plots()
        p3_time = time.time() - start - p1_time
        print(f"  Phase 3: {len(plot_paths)} plots ({p3_time:.1f}s)")
        for p in plot_paths:
            print(f"    {p.name}")
    except Exception as e:
        print(f"  Visualization FAILED: {e}")
        import traceback
        traceback.print_exc()

    total = time.time() - start
    print(f"\n{'=' * 70}")
    print(f"All done: {ok} downscaled + {share_count} shares + plots ({total:.1f}s)")
    return 0


def _load_output(method: str, key: str, scenario: str):
    """加载已降尺度的输出，处理 key 为 gdp/population 的特殊情况。"""
    import pandas as pd

    if key == "gdp":
        from compare.common.io import read_gdp_country
        from compare.common.config import gdp_country_path
        from compare.common.mapping import load_mapping, EXCLUDED_ISO
        df = read_gdp_country(gdp_country_path(scenario))
        mapping = load_mapping()
        iso_info: dict[str, dict] = {}
        for _, row in mapping.iterrows():
            iso = str(row.get("iso", "")).lower().strip()
            if iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            display = (row.get("GCAM Country", "") or row.get("IEA_ctry", "")
                       or row.get("iso_ctry", "") or str(row.get("iso", "")))
            if iso not in iso_info:
                iso_info[iso] = {"Country": display, "Region": row["Region"]}
        df_out = pd.DataFrame({"iso": df["iso"]})
        df_out["Country"] = df_out["iso"].map(lambda x: iso_info.get(x, {}).get("Country", ""))
        df_out["Region"] = df_out["iso"].map(lambda x: iso_info.get(x, {}).get("Region", ""))
        df_out["Scenario"] = scenario
        for y in YEARS:
            df_out[y] = df[y]
        return df_out

    if key == "population":
        from compare.common.io import read_pop_country
        from compare.common.config import pop_country_path
        from compare.common.mapping import load_mapping, EXCLUDED_ISO
        df = read_pop_country(pop_country_path(scenario))
        mapping = load_mapping()
        iso_info: dict[str, dict] = {}
        for _, row in mapping.iterrows():
            iso = str(row.get("iso", "")).lower().strip()
            if iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            display = (row.get("GCAM Country", "") or row.get("IEA_ctry", "")
                       or row.get("iso_ctry", "") or str(row.get("iso", "")))
            if iso not in iso_info:
                iso_info[iso] = {"Country": display, "Region": row["Region"]}
        df_out = pd.DataFrame({"iso": df["iso"]})
        df_out["Country"] = df_out["iso"].map(lambda x: iso_info.get(x, {}).get("Country", ""))
        df_out["Region"] = df_out["iso"].map(lambda x: iso_info.get(x, {}).get("Region", ""))
        df_out["Scenario"] = scenario
        for y in YEARS:
            df_out[y] = df[y]
        return df_out

    from compare.common.config import OUTPUT_DIR

    # 使用 INDICATORS 中的 output_prefix 查找文件
    prefix = key
    if key in INDICATORS:
        prefix = INDICATORS[key].output_prefix

    path = OUTPUT_DIR / f"{method}_{prefix}_downscaled_{scenario}.xlsx"
    if path.exists():
        return pd.read_excel(path)
    # Fallback: try various prefixes
    for alt in [key, key.upper(), key.lower()]:
        path = OUTPUT_DIR / f"{method}_{alt}_downscaled_{scenario}.xlsx"
        if path.exists():
            return pd.read_excel(path)
    raise FileNotFoundError(f"Cannot find output for {method}_{key}_{scenario} (tried prefix={prefix})")


if __name__ == "__main__":
    sys.exit(main())
