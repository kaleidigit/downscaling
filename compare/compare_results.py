"""三方案对比分析与可视化——支持全部 SDG 指标。"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from compare.common.config import (
    OUTPUT_DIR, SCENARIOS, YEARS, INDICATORS, DERIVED_SHARES,
)

METHODS = ["logit", "kaya", "dscale"]
METHOD_COLORS = {"logit": "#2196F3", "kaya": "#FF5722", "dscale": "#4CAF50"}
METHOD_LABELS = {"logit": "Logit (proportional)", "kaya": "Kaya (convergence)", "dscale": "DSCALE (dual-path)"}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 9, "axes.titlesize": 11, "axes.labelsize": 9,
    "figure.dpi": 150, "savefig.dpi": 150, "savefig.bbox": "tight",
})


def _load(key: str, scenario: str) -> dict[str, pd.DataFrame]:
    """加载某指标某情景下三方案的输出。"""
    data = {}
    cfg = INDICATORS.get(key)
    prefix = cfg.output_prefix if cfg else key
    for m in METHODS:
        path = OUTPUT_DIR / f"{m}_{prefix}_downscaled_{scenario}.xlsx"
        if path.exists():
            df = pd.read_excel(path)
            data[m] = df[df["iso"] != "oth"] if "iso" in df.columns else df
    return data


def _load_share(key: str, scenario: str) -> dict[str, pd.DataFrame]:
    """加载某份额指标。"""
    data = {}
    for m in METHODS:
        path = OUTPUT_DIR / f"{m}_{key}_downscaled_{scenario}.xlsx"
        if path.exists():
            df = pd.read_excel(path)
            data[m] = df[df["iso"] != "oth"] if "iso" in df.columns else df
    return data


# ═══════════════════════════════════════════════════
# Plot 1: 单指标仪表板
# ═══════════════════════════════════════════════════

def plot_indicator_dashboard(indicator_key: str, scenario: str = "SSP126") -> Path:
    """为单个无界量指标生成五面板仪表板。"""
    data = _load(indicator_key, scenario)
    if len(data) < 2:
        return None

    cfg = INDICATORS[indicator_key]
    unit = cfg.unit

    fig = plt.figure(figsize=(16, 10))
    gs = fig.add_gridspec(2, 3, hspace=0.35, wspace=0.30)

    # A. 全球总量
    ax_a = fig.add_subplot(gs[0, :2])
    for m in METHODS:
        if m in data:
            totals = [data[m][y].sum() for y in YEARS]
            ax_a.plot(YEARS, totals, color=METHOD_COLORS[m],
                      label=METHOD_LABELS[m], linewidth=1.5)
    ax_a.set_ylabel(f"Global ({unit})")
    ax_a.set_title(f"A. {cfg.name} — Global Total")
    ax_a.legend(fontsize=8)

    # B. 前10国家 — 2100
    ax_b = fig.add_subplot(gs[0, 2])
    ref_m = "logit" if "logit" in data else list(data.keys())[0]
    df_ref = data[ref_m].groupby("iso")[2100].sum()
    top10 = df_ref.nlargest(10).index.tolist()
    x = np.arange(len(top10))
    w = 0.25
    for i, m in enumerate(METHODS):
        if m in data:
            df_m = data[m].set_index("iso")
            vals = [df_m.loc[iso, 2100] if iso in df_m.index else 0 for iso in top10]
            ax_b.bar(x + i * w, vals, w, color=METHOD_COLORS[m],
                     label=METHOD_LABELS[m], edgecolor="white", linewidth=0.3)
    ax_b.set_xticks(x + w)
    ax_b.set_xticklabels([iso.upper() for iso in top10], rotation=45, ha="right", fontsize=7)
    ax_b.set_ylabel(f"2100 ({unit})")
    ax_b.set_title("B. Top 10 — 2100")
    ax_b.legend(fontsize=7)

    # C. 方案间散点
    ax_c = fig.add_subplot(gs[1, 0])
    if "logit" in data and "kaya" in data:
        dl = data["logit"].set_index("iso")[2050]
        dk = data["kaya"].set_index("iso")[2050]
        common = dl.index.intersection(dk.index)
        x, y = dl[common].values, dk[common].values
        mask = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
        ax_c.scatter(x[mask], y[mask], s=6, alpha=0.5, c="#333333", edgecolors="none")
        ax_c.set_xlabel("Logit")
        ax_c.set_ylabel("Kaya")
        if mask.sum() > 2:
            r = np.corrcoef(np.log(x[mask]), np.log(y[mask]))[0, 1]
            ax_c.text(0.95, 0.05, f"log-log r={r:.3f}", transform=ax_c.transAxes,
                      ha="right", fontsize=8, bbox=dict(boxstyle="round", fc="white", alpha=0.7))
        ax_c.set_title("C. Logit vs Kaya (2050)")

    # D. DSCALE vs Logit
    ax_d = fig.add_subplot(gs[1, 1])
    if "logit" in data and "dscale" in data:
        dl = data["logit"].set_index("iso")[2050]
        dd = data["dscale"].set_index("iso")[2050]
        common = dl.index.intersection(dd.index)
        x, y = dl[common].values, dd[common].values
        mask = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
        ax_d.scatter(x[mask], y[mask], s=6, alpha=0.5, c="#333333", edgecolors="none")
        ax_d.set_xlabel("Logit")
        ax_d.set_ylabel("DSCALE")
        if mask.sum() > 2:
            r = np.corrcoef(np.log(x[mask]), np.log(y[mask]))[0, 1]
            ax_d.text(0.95, 0.05, f"log-log r={r:.3f}", transform=ax_d.transAxes,
                      ha="right", fontsize=8, bbox=dict(boxstyle="round", fc="white", alpha=0.7))
        ax_d.set_title("D. Logit vs DSCALE (2050)")

    # E. 国家层面方法偏差分布（替代无信息量的区域热力图）
    ax_e = fig.add_subplot(gs[1, 2])
    if "logit" in data and "kaya" in data:
        dl = data["logit"].set_index("iso")[2100]
        dk = data["kaya"].set_index("iso")[2100]
        dd = data["dscale"].set_index("iso")[2100] if "dscale" in data else None
        common_lk = dl.index.intersection(dk.index)
        if len(common_lk) > 0:
            lk_dev = ((dk[common_lk] - dl[common_lk]) / dl[common_lk].clip(1e-6) * 100).dropna()
            lk_dev = lk_dev[np.isfinite(lk_dev) & (abs(lk_dev) < 500)]  # 剔除极端值
            ax_e.hist(lk_dev, bins=40, alpha=0.5, color=METHOD_COLORS["kaya"],
                      label=f"Kaya vs Logit (n={len(lk_dev)})", density=True)
            if dd is not None:
                common_ld = dl.index.intersection(dd.index)
                ld_dev = ((dd[common_ld] - dl[common_ld]) / dl[common_ld].clip(1e-6) * 100).dropna()
                ld_dev = ld_dev[np.isfinite(ld_dev) & (abs(ld_dev) < 500)]
                ax_e.hist(ld_dev, bins=40, alpha=0.5, color=METHOD_COLORS["dscale"],
                          label=f"DSCALE vs Logit (n={len(ld_dev)})", density=True)
            ax_e.set_xlabel("Deviation from Logit (%)")
            ax_e.set_title("E. Country-Level Deviation (2100)")
            ax_e.legend(fontsize=7)
    elif len(data) >= 1:
        ax_e.text(0.5, 0.5, "insufficient data", ha="center", va="center",
                  transform=ax_e.transAxes, fontsize=10)
        ax_e.set_title("E. N/A")

    fig.suptitle(f"{cfg.name} ({cfg.sdg}) — {scenario}", fontsize=14, y=1.01)
    out = OUTPUT_DIR / f"dashboard_{indicator_key}_{scenario}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ═══════════════════════════════════════════════════
# Plot 2: 跨指标方法一致性
# ═══════════════════════════════════════════════════

def plot_cross_indicator_agreement(scenario: str = "SSP126") -> Path:
    """比较各指标下三方案之间的一致性。"""
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # 1. Logit-Kaya log-log r per indicator
    ax = axes[0]
    indicators_checked = []
    r_values_logit_kaya = []
    r_values_logit_dscale = []

    for key in INDICATORS:
        data = _load(key, scenario)
        if "logit" not in data or "kaya" not in data:
            continue
        dl = data["logit"].set_index("iso")[2050]
        dk = data["kaya"].set_index("iso")[2050]
        common = dl.index.intersection(dk.index)
        if len(common) < 5:
            continue
        x, y = dl[common].values, dk[common].values
        mask = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
        if mask.sum() > 5:
            indicators_checked.append(INDICATORS[key].name)
            r_values_logit_kaya.append(np.corrcoef(np.log(x[mask]), np.log(y[mask]))[0, 1])
            if "dscale" in data:
                dd = data["dscale"].set_index("iso")[2050]
                y2 = dd[common].values
                mask2 = (x > 0) & (y2 > 0) & np.isfinite(x) & np.isfinite(y2)
                r_values_logit_dscale.append(np.corrcoef(np.log(x[mask2]), np.log(y2[mask2]))[0, 1])
            else:
                r_values_logit_dscale.append(0)

    x_pos = np.arange(len(indicators_checked))
    w = 0.35
    ax.bar(x_pos - w/2, r_values_logit_kaya, w, color=METHOD_COLORS["kaya"], label="Logit-Kaya")
    if len(r_values_logit_dscale) == len(indicators_checked):
        ax.bar(x_pos + w/2, r_values_logit_dscale, w, color=METHOD_COLORS["dscale"], label="Logit-DSCALE")
    ax.set_xticks(x_pos)
    ax.set_xticklabels(indicators_checked, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("log-log correlation (2050)")
    ax.set_title("Method Agreement Across Indicators")
    ax.legend(fontsize=8)
    ax.set_ylim(0.5, 1.01)
    ax.axhline(y=1.0, color="gray", linewidth=0.5, linestyle="--")

    # 2. CV comparison
    ax2 = axes[1]
    cv_data = {}
    for key in INDICATORS:
        data = _load(key, scenario)
        if not data:
            continue
        for m in METHODS:
            if m in data:
                vals = data[m].groupby("iso")[2100].sum()
                cv = float(vals.std() / vals.mean()) if vals.mean() > 0 else 0
                cv_data[(INDICATORS[key].name, m)] = cv

    indicators_names = list(INDICATORS.values())
    x2 = np.arange(len(indicators_names))
    w2 = 0.25
    for i, m in enumerate(METHODS):
        vals = [cv_data.get((cfg.name, m), 0) for cfg in INDICATORS.values()]
        ax2.bar(x2 + i * w2, vals, w2, color=METHOD_COLORS[m], label=METHOD_LABELS[m],
                edgecolor="white", linewidth=0.3)
    ax2.set_xticks(x2 + w2)
    ax2.set_xticklabels([cfg.name for cfg in INDICATORS.values()], rotation=30, ha="right", fontsize=8)
    ax2.set_ylabel("CV of country values (2100)")
    ax2.set_title("Distribution Inequality (CV)")
    ax2.legend(fontsize=7)

    fig.suptitle(f"Cross-Indicator Method Comparison — {scenario}", fontsize=14, y=1.01)
    fig.tight_layout()
    out = OUTPUT_DIR / f"cross_indicator_{scenario}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ═══════════════════════════════════════════════════
# Plot 3: 份额指标对比
# ═══════════════════════════════════════════════════

def plot_share_comparison(scenario: str = "SSP126") -> list[Path]:
    """为每个份额指标生成三方案对比图。"""
    outputs = []
    for share_key, spec in DERIVED_SHARES.items():
        data = _load_share(share_key, scenario)
        if len(data) < 2:
            continue

        fig, axes = plt.subplots(1, 3, figsize=(15, 5))

        # A. Top countries share time series
        ax = axes[0]
        ref = list(data.values())[0]
        top5 = ref.groupby("iso")[2100].sum().nlargest(5).index.tolist()
        for iso in top5:
            for m in METHODS:
                if m in data:
                    row = data[m][data[m]["iso"] == iso]
                    if len(row):
                        vals = [row[y].values[0] for y in YEARS]
                        ax.plot(YEARS, vals, color=METHOD_COLORS[m], linewidth=1.2,
                                alpha=0.7, label=f"{iso.upper()} {m}" if iso == top5[0] else "")
        ax.set_title(f"{spec['name']} — Top 5 Countries")
        ax.legend(fontsize=6, ncol=2)

        # B. Distribution (2050)
        ax2 = axes[1]
        is_bounded = share_key not in ("energy_intensity", "per_capita_co2")
        for i, m in enumerate(METHODS):
            if m in data:
                vals = data[m][2050].dropna().values
                vals = vals[np.isfinite(vals)]
                if is_bounded:
                    vals = np.clip(vals, 0, 1)
                else:
                    vals = vals[vals > 0]  # 无界量过滤零值
                if len(vals) > 0:
                    bins = 30 if is_bounded else np.logspace(np.log10(max(vals.min(), 1)), np.log10(max(vals.max(), 10)), 30)
                    ax2.hist(vals, bins=bins, alpha=0.5, color=METHOD_COLORS[m],
                             label=METHOD_LABELS[m], density=True)
        ax2.set_title(f"Distribution (2050)")
        ax2.legend(fontsize=7)
        ax2.set_xlabel("Value")
        if not is_bounded:
            ax2.set_xscale("log")

        # C. Method scatter (2050)
        ax3 = axes[2]
        if "logit" in data and "kaya" in data:
            dl = data["logit"].set_index("iso")[2050].clip(lower=0)
            dk = data["kaya"].set_index("iso")[2050].clip(lower=0)
            common = dl.index.intersection(dk.index)
            x, y = dl[common], dk[common]
            ax3.scatter(x, y, s=6, alpha=0.5, c="#333333")
            ax3.set_xlabel("Logit")
            ax3.set_ylabel("Kaya")
            ax3.set_title(f"Logit vs Kaya (2050)")
            # 数据驱动坐标轴：对份额指标用 [0,1]，对无界量用 p5-p95
            both = np.concatenate([x.values, y.values])
            both = both[np.isfinite(both)]
            if len(both) > 0:
                if both.max() <= 1.05:
                    lo, hi = 0, 1
                else:
                    lo = max(0, np.percentile(both, 0.5))
                    hi = min(both.max(), np.percentile(both, 99.5))
                ax3.plot([lo, hi], [lo, hi], "k--", linewidth=0.5, alpha=0.4)
                ax3.set_xlim(lo, hi)
                ax3.set_ylim(lo, hi)

        fig.suptitle(f"{spec['name']} ({spec['sdg']}) — {scenario}", fontsize=13)
        fig.tight_layout()
        out = OUTPUT_DIR / f"share_{share_key}_{scenario}.png"
        fig.savefig(out, bbox_inches="tight")
        plt.close(fig)
        outputs.append(out)
    return outputs


# ═══════════════════════════════════════════════════
# Legacy TFC 可视化（保持兼容）
# ═══════════════════════════════════════════════════

def plot_key_countries(scenario: str = "SSP126", top_n: int = 9) -> Path:
    data = _load("tfc", scenario)
    if not data:
        raise FileNotFoundError(f"No TFC output for {scenario}")
    df0 = data["logit"]
    top_isos = df0.groupby("iso")[2015].sum().nlargest(top_n).index.tolist()
    n_cols, n_rows = 3, (top_n + 2) // 3
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, 3.2 * n_rows))
    axes = axes.flatten()
    for idx, iso in enumerate(top_isos):
        ax = axes[idx]
        for m in METHODS:
            if m in data:
                row = data[m][data[m]["iso"] == iso]
                if len(row):
                    country = row["Country"].values[0]
                    ax.plot(YEARS, [row[y].values[0] for y in YEARS],
                            color=METHOD_COLORS[m], label=METHOD_LABELS[m], linewidth=1.2, alpha=0.85)
        ax.set_title(f"{iso.upper()} ({country})", fontsize=9)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1e6:.0f}M"))
        if idx == 0:
            ax.legend(fontsize=7, framealpha=0.8)
    for idx in range(top_n, len(axes)):
        axes[idx].set_visible(False)
    fig.suptitle(f"Key Countries TFC — {scenario}", fontsize=13, y=1.01)
    fig.tight_layout()
    out = OUTPUT_DIR / f"compare_key_countries_{scenario}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_multi_country_region(scenario: str = "SSP126", region: str = "Africa_Eastern", year: int = 2050) -> Path:
    data = _load("tfc", scenario)
    if not data:
        raise FileNotFoundError(f"No TFC output for {scenario}")
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    ref = data["logit"]
    order = ref[ref["Region"] == region].groupby("iso")[year].sum().sort_values(ascending=False).index.tolist()
    for ax, m in zip(axes, METHODS):
        if m not in data:
            continue
        df_m = data[m]
        vals, labels = [], []
        for iso in order:
            row = df_m[df_m["iso"] == iso]
            if len(row):
                vals.append(row[year].values[0])
                labels.append(iso.upper())
        colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(vals)))
        ax.bar(range(len(vals)), vals, color=colors, edgecolor="white", linewidth=0.3)
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=7)
        ax.set_title(METHOD_LABELS[m], fontsize=10)
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1e6:.1f}M"))
    fig.suptitle(f"{region} TFC Allocation ({year}) — {scenario}", fontsize=13)
    fig.tight_layout()
    out = OUTPUT_DIR / f"compare_region_{region}_{scenario}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_method_scatter(scenario: str = "SSP126", year: int = 2050) -> Path:
    data = _load("tfc", scenario)
    if not data:
        raise FileNotFoundError(f"No TFC output for {scenario}")
    pairs = [("logit", "kaya"), ("logit", "dscale"), ("kaya", "dscale")]
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    for ax, (m1, m2) in zip(axes, pairs):
        if m1 not in data or m2 not in data:
            continue
        df1 = data[m1].set_index("iso")[year]
        df2 = data[m2].set_index("iso")[year]
        common = df1.index.intersection(df2.index)
        x, y = df1[common].values / 1e6, df2[common].values / 1e6
        ax.scatter(x, y, s=8, alpha=0.5, c="#333333", edgecolors="none")
        lims = [min(x.min(), y.min()) * 0.9, max(x.max(), y.max()) * 1.1]
        ax.plot(lims, lims, "k--", linewidth=0.6, alpha=0.4)
        ax.set_xlim(lims); ax.set_ylim(lims)
        ax.set_xlabel(f"{METHOD_LABELS[m1]} (M TJ)", fontsize=8)
        ax.set_ylabel(f"{METHOD_LABELS[m2]} (M TJ)", fontsize=8)
        ax.set_title(f"{m1.upper()} vs {m2.upper()}", fontsize=10)
    fig.suptitle(f"TFC Method Agreement — {year} — {scenario}", fontsize=13)
    fig.tight_layout()
    out = OUTPUT_DIR / f"compare_scatter_{scenario}_{year}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_summary_dashboard(scenario: str = "SSP126") -> Path:
    """TFC 汇总仪表板（保留旧接口）。"""
    return plot_indicator_dashboard("tfc", scenario)


# ═══════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════

def generate_all_plots(scenario: str | None = None) -> list[Path]:
    """生成所有对比图表。"""
    scenarios = [scenario] if scenario else SCENARIOS
    outputs = []

    # 1. 所有无界量指标的仪表板
    for sc in scenarios:
        print(f"  Indicator dashboards ({sc})...")
        for key in INDICATORS:
            try:
                out = plot_indicator_dashboard(key, sc)
                if out:
                    outputs.append(out)
            except Exception as e:
                print(f"    WARNING {key}: {e}")

    # 2. Legacy TFC 详细图表（每种一张）
    for sc in scenarios:
        print(f"  TFC detailed plots ({sc})...")
        try:
            outputs.append(plot_key_countries(sc))
            outputs.append(plot_multi_country_region(sc, "Africa_Eastern", 2050))
            outputs.append(plot_multi_country_region(sc, "EU-12", 2050))
            outputs.append(plot_method_scatter(sc, 2050))
        except Exception as e:
            print(f"    WARNING TFC plots: {e}")

    # 3. 跨指标对比
    for sc in scenarios:
        print(f"  Cross-indicator ({sc})...")
        try:
            outputs.append(plot_cross_indicator_agreement(sc))
        except Exception as e:
            print(f"    WARNING cross-indicator: {e}")

    # 4. 份额指标对比
    for sc in scenarios:
        print(f"  Share indicators ({sc})...")
        try:
            outputs.extend(plot_share_comparison(sc))
        except Exception as e:
            print(f"    WARNING shares: {e}")

    return outputs


if __name__ == "__main__":
    paths = generate_all_plots()
    print(f"\nGenerated {len(paths)} plots:")
    for p in paths:
        print(f"  {p}")
