"""三方案对比分析与可视化——多场景合并 + 方法特性 + 全局汇总。"""

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from compare.common.config import (
    OUTPUT_DATA_DIR, OUTPUT_PLOTS_DIR, SCENARIOS, YEARS, INDICATORS, DERIVED_SHARES,
)

METHODS = ["logit", "kaya", "dscale"]
METHOD_COLORS = {"logit": "#2196F3", "kaya": "#FF5722", "dscale": "#4CAF50"}
METHOD_LABELS = {"logit": "Logit (proportional)", "kaya": "Kaya (convergence)", "dscale": "DSCALE (dual-path)"}
SCENARIO_TITLES = {
    "SSP126": "SSP1-2.6 (Sustainability)",
    "SSP245": "SSP2-4.5 (Middle Road)",
    "SSP434": "SSP4-3.4 (Inequality)",
    "SSP460": "SSP4-6.0 (Regional Rivalry)",
}

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
    "font.size": 9, "axes.titlesize": 11, "axes.labelsize": 9,
    "figure.dpi": 150, "savefig.dpi": 150, "savefig.bbox": "tight",
})


def _load(key: str, scenario: str) -> dict[str, pd.DataFrame]:
    data = {}
    cfg = INDICATORS.get(key)
    prefix = cfg.output_prefix if cfg else key
    for m in METHODS:
        path = OUTPUT_DATA_DIR / f"{m}_{prefix}_downscaled_{scenario}.xlsx"
        if path.exists():
            df = pd.read_excel(path)
            data[m] = df[df["iso"] != "oth"] if "iso" in df.columns else df
    return data


def _load_share(key: str, scenario: str) -> dict[str, pd.DataFrame]:
    data = {}
    for m in METHODS:
        path = OUTPUT_DATA_DIR / f"{m}_{key}_downscaled_{scenario}.xlsx"
        if path.exists():
            df = pd.read_excel(path)
            data[m] = df[df["iso"] != "oth"] if "iso" in df.columns else df
    return data


# ═══════════════════════════════════════════════════════════
# P0: 多场景合并仪表板 — 2×2 子图布局
# ═══════════════════════════════════════════════════════════

def plot_indicator_dashboard_all_scenarios(indicator_key: str) -> Path | None:
    """单指标 4 情景 2×2 布局：全局总量时序 + 2100 偏差分布。"""
    cfg = INDICATORS[indicator_key]
    unit = cfg.unit

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()

    for idx, sc in enumerate(SCENARIOS):
        ax = axes[idx]
        data = _load(indicator_key, sc)
        if len(data) < 1:
            ax.text(0.5, 0.5, "no data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, color="gray")
            ax.set_title(SCENARIO_TITLES.get(sc, sc), fontsize=10)
            continue

        # 左轴：国家中位数时序（方法差异在分配层面体现，全球总因守恒相同）
        for m in data:
            medians = [data[m][y].median() for y in YEARS]
            ax.plot(YEARS, medians, color=METHOD_COLORS[m],
                    label=METHOD_LABELS[m], linewidth=1.5)
        ax.set_ylabel(f"Median country ({unit})")
        ax.set_title(SCENARIO_TITLES.get(sc, sc), fontsize=10)
        if idx == 0:
            ax.legend(fontsize=7, loc="upper left")

        # 右轴（twin）：2100 偏差分布
        if "logit" in data and "kaya" in data:
            ax2 = ax.twinx()
            dl = data["logit"].set_index("iso")[2100]
            dk = data["kaya"].set_index("iso")[2100]
            common = dl.index.intersection(dk.index)
            dev = ((dk[common] - dl[common]) / dl[common].clip(1e-6) * 100).dropna()
            dev = dev[np.isfinite(dev) & (abs(dev) < 200)]
            if len(dev) > 0:
                ax2.hist(dev, bins=25, alpha=0.25, color=METHOD_COLORS["kaya"], density=True)
            ax2.set_ylabel("Kaya dev %", fontsize=7, alpha=0.5)
            ax2.tick_params(axis='y', labelsize=6)

    fig.suptitle(f"{cfg.name} ({cfg.sdg}) — All Scenarios", fontsize=14, y=1.01)
    fig.tight_layout()
    out = OUTPUT_PLOTS_DIR / f"dashboard_{indicator_key}_all.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ═══════════════════════════════════════════════════════════
# P0: 多场景份额对比 — 2×2 子图布局
# ═══════════════════════════════════════════════════════════

def plot_share_all_scenarios(share_key: str) -> Path | None:
    """单份额指标 4 情景 2×2 布局：Top-5 国家时序。

    至少有一个情景有数据才生成图表，单方法场景不做 "insufficient data" 报错。
    """
    spec = DERIVED_SHARES[share_key]

    # 预检：是否有任何情景有数据
    has_any_data = False
    for sc in SCENARIOS:
        if len(_load_share(share_key, sc)) >= 1:
            has_any_data = True
            break
    if not has_any_data:
        return None  # 无数据，静默跳过

    is_bounded = share_key not in ("energy_intensity", "per_capita_co2")
    fig, axes = plt.subplots(2, 2, figsize=(16, 10))
    axes = axes.flatten()

    for idx, sc in enumerate(SCENARIOS):
        ax = axes[idx]
        data = _load_share(share_key, sc)
        if len(data) < 1:
            ax.text(0.5, 0.5, "no data", ha="center", va="center",
                    transform=ax.transAxes, fontsize=10, color="gray")
            ax.set_title(SCENARIO_TITLES.get(sc, sc), fontsize=10)
            continue

        ref = list(data.values())[0]
        top5 = ref.groupby("iso")[2100].sum().nlargest(5).index.tolist()
        for iso in top5:
            for m in data:
                row = data[m][data[m]["iso"] == iso]
                if len(row):
                    vals = [row[y].values[0] for y in YEARS]
                    ax.plot(YEARS, vals, color=METHOD_COLORS[m], linewidth=1.2,
                            alpha=0.7)
        # ISO 标签在曲线末端
        for iso in top5:
            if iso in ref.index:
                v = float(ref.loc[iso, 2100])
                ax.text(2102, v, iso.upper(), fontsize=6, va='center', alpha=0.8)
        ax.set_title(SCENARIO_TITLES.get(sc, sc), fontsize=10)
        ax.set_ylabel("Value")
        if not is_bounded:
            ax.set_yscale("log")
        else:
            ax.set_ylim(-0.05, 1.05)
        if idx == 0:
            # 方法颜色图例 + 国家名标注
            from matplotlib.lines import Line2D
            handles = [Line2D([0],[0], color=METHOD_COLORS[m], linewidth=1.5,
                              label=METHOD_LABELS[m]) for m in data]
            ax.legend(handles=handles, fontsize=7, loc="upper left")

    fig.suptitle(f"{spec['name']} ({spec['sdg']}) — All Scenarios", fontsize=14, y=1.01)
    fig.tight_layout()
    out = OUTPUT_PLOTS_DIR / f"share_{share_key}_all.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ═══════════════════════════════════════════════════════════
# P1: 收敛速度分布 — Kaya + DSCALE 方法特性
# ═══════════════════════════════════════════════════════════

def plot_convergence_profile() -> Path:
    """Kaya w(t) 曲线 + DSCALE CONV_WEIGHT 曲线，富国/穷国对比。"""
    from compare.common.downscale import (
        convergence_gamma, convergence_weight, CONVERGENCE_YEAR_DEFAULT,
    )
    from compare.common.io import read_gdp_country, read_pop_country
    from compare.common.config import gdp_country_path, pop_country_path
    from compare.common.mapping import load_mapping, build_region_members, EXCLUDED_ISO

    fig, axes = plt.subplots(1, 3, figsize=(18, 5.5))

    # ---- Panel A: Kaya convergence weight w(t) by GDP quintile ----
    ax = axes[0]
    sc = "SSP126"
    y_c = CONVERGENCE_YEAR_DEFAULT[sc]
    gamma = convergence_gamma(y_c)

    gdp = read_gdp_country(gdp_country_path(sc)).set_index("iso")
    pop = read_pop_country(pop_country_path(sc)).set_index("iso")
    mapping = load_mapping()
    members = build_region_members(mapping)

    # Compute GDP pcap for all countries
    pcap = {}
    for mlist in members.values():
        for m in mlist:
            iso = m["iso"]
            if iso in EXCLUDED_ISO:
                continue
            iso = "chn" if iso == "twn" else iso
            if iso in gdp.index and iso in pop.index:
                g = float(gdp.loc[iso, 2015])
                p = max(float(pop.loc[iso, 2015]), 1e-6)
                if g > 0:
                    pcap[iso] = g / p

    if len(pcap) > 10:
        sorted_isos = sorted(pcap, key=pcap.get)
        n = len(sorted_isos)
        quintiles = {
            "Bottom 20%": sorted_isos[:n//5],
            "Mid": sorted_isos[n//2 - 5:n//2 + 5],
            "Top 20%": sorted_isos[-n//5:],
        }
        years_plot = list(range(2015, 2160, 5))
        for label, isos in quintiles.items():
            avg_pcap = np.mean([pcap[i] for i in isos])
            w_vals = [convergence_weight(y, gamma) for y in years_plot]
            ax.plot(years_plot, w_vals, linewidth=1.8,
                    label=f"{label} (GDPpcap≈{avg_pcap/1000:.0f}k$)")

    ax.axvline(x=2100, color="gray", linestyle="--", alpha=0.5, linewidth=0.8)
    ax.text(2102, 0.15, "2100", fontsize=8, color="gray")
    ax.set_ylabel("Convergence weight w(t)")
    ax.set_title("A. Kaya Convergence Speed (SSP126)")
    ax.legend(fontsize=7)

    # ---- Panel B: DSCALE convergence weight comparison ----
    ax2 = axes[1]
    from compare.dscale.dscale_official import fun_max_tc_convergence
    years_arr = np.array(list(range(2010, 2110, 5)), dtype=float)
    n = len(years_arr)

    for max_tc, beta, label in [(2040, 1.0, "Early (2040, β=1)"),
                                  (2120, 2.0, "Medium (2120, β=2)"),
                                  (2200, 3.0, "Late (2200, β=3)")]:
        es = np.full(n, 0.0)
        el = np.full(n, 1.0)
        mtc = np.full(n, float(max_tc))
        b = np.full(n, float(beta))
        result = fun_max_tc_convergence(es, el, years_arr, mtc, b)
        ax2.plot(years_arr, result, linewidth=1.8, label=label)

    ax2.set_ylabel("ENLONG fraction (1 − CONV_WEIGHT)")
    ax2.set_title("B. DSCALE ENSHORT → ENLONG Transition")
    ax2.legend(fontsize=7)

    # ---- Panel C: Method divergence over time ----
    ax3 = axes[2]
    data = _load("tfc", "SSP126")
    years_sel = [2015, 2030, 2050, 2070, 2100]
    cv_vals = {m: [] for m in METHODS if m in data}
    for y in years_sel:
        method_vals = []
        for m in cv_vals:
            v = float(data[m][y].sum())
            method_vals.append(v)
            cv_vals[m].append(v)
        # Compute CV across methods
        if len(method_vals) >= 2:
            cv = np.std(method_vals) / np.mean(method_vals) * 100
        else:
            cv = 0

    for m in cv_vals:
        if m == "logit":
            continue
        ref = np.array(cv_vals["logit"])
        other = np.array(cv_vals[m])
        dev = (other - ref) / ref.clip(1e-10) * 100
        ax3.plot(years_sel, dev, 'o-', color=METHOD_COLORS[m],
                 linewidth=1.8, markersize=6, label=f"{METHOD_LABELS[m]} vs Logit")

    ax3.axhline(y=0, color="gray", linestyle="--", alpha=0.4)
    ax3.set_ylabel("Deviation from Logit (%)")
    ax3.set_xlabel("Year")
    ax3.set_title("C. Global TFC Method Divergence (SSP126)")
    ax3.legend(fontsize=7)

    fig.suptitle("Convergence Dynamics — Method Characteristics", fontsize=14, y=1.02)
    fig.tight_layout()
    out = OUTPUT_PLOTS_DIR / "convergence_profile.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ═══════════════════════════════════════════════════════════
# P1: 散点图 — 2050 + 2100 双年对比
# ═══════════════════════════════════════════════════════════

def plot_method_scatter_two_years(scenario: str = "SSP126") -> Path:
    """TFC 方法间散点图：2050 vs 2100 双行对比。"""
    data = _load("tfc", scenario)
    if len(data) < 1:
        return None

    pairs = [("logit", "kaya"), ("logit", "dscale"), ("kaya", "dscale")]
    fig, axes = plt.subplots(2, 3, figsize=(16, 10))

    for row, year in enumerate([2050, 2100]):
        for col, (m1, m2) in enumerate(pairs):
            ax = axes[row, col]
            if m1 not in data or m2 not in data:
                continue
            df1 = data[m1].set_index("iso")[year]
            df2 = data[m2].set_index("iso")[year]
            common = df1.index.intersection(df2.index)
            x, y = df1[common].values / 1e6, df2[common].values / 1e6
            ax.scatter(x, y, s=6, alpha=0.5, c="#333333", edgecolors="none")
            lims = [min(x.min(), y.min()) * 0.9, max(x.max(), y.max()) * 1.1]
            ax.plot(lims, lims, "k--", linewidth=0.6, alpha=0.4)
            ax.set_xlim(lims); ax.set_ylim(lims)
            ax.set_xlabel(f"{METHOD_LABELS[m1]} (M TJ)", fontsize=8)
            ax.set_ylabel(f"{METHOD_LABELS[m2]} (M TJ)", fontsize=8)
            # log-log correlation
            mask = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
            if mask.sum() > 5:
                r = np.corrcoef(np.log(x[mask]), np.log(y[mask]))[0, 1]
                ax.text(0.95, 0.05, f"r={r:.3f}", transform=ax.transAxes,
                        ha="right", fontsize=8, bbox=dict(boxstyle="round", fc="white", alpha=0.7))
            ax.set_title(f"{m1.upper()} vs {m2.upper()} ({year})", fontsize=9)

    fig.suptitle(f"TFC Method Agreement — {scenario}", fontsize=14, y=1.01)
    fig.tight_layout()
    out = OUTPUT_PLOTS_DIR / f"compare_scatter_{scenario}.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ═══════════════════════════════════════════════════════════
# P2: 全局汇总图
# ═══════════════════════════════════════════════════════════

def plot_global_summary() -> Path:
    """跨指标×方法×场景 全局汇总：3 面板。"""
    fig = plt.figure(figsize=(18, 12))
    gs = fig.add_gridspec(2, 3, hspace=0.35, wspace=0.35)

    # ---- Panel A: Global totals by indicator (SSP126, 2100) ----
    ax_a = fig.add_subplot(gs[0, :2])
    indicators_list = list(INDICATORS.keys())
    x = np.arange(len(indicators_list))
    w = 0.25
    for i, m in enumerate(METHODS):
        vals, labels = [], []
        for key in indicators_list:
            cfg = INDICATORS[key]
            data = _load(key, "SSP126")
            if m in data:
                v = float(data[m][2100].sum())
            else:
                v = 0
            vals.append(v)
            labels.append(cfg.name)
        # Normalize to relative change from 2015
        vals_2015 = []
        for key in indicators_list:
            data = _load(key, "SSP126")
            if m in data:
                vals_2015.append(float(data[m][2015].sum()))
            else:
                vals_2015.append(1.0)
        rel_change = [v / max(v0, 1e-10) for v, v0 in zip(vals, vals_2015)]
        ax_a.bar(x + i * w, rel_change, w, color=METHOD_COLORS[m],
                 label=METHOD_LABELS[m], edgecolor="white", linewidth=0.3)
    ax_a.set_xticks(x + w)
    ax_a.set_xticklabels([cfg.name for cfg in INDICATORS.values()],
                          rotation=25, ha="right", fontsize=8)
    ax_a.axhline(y=1.0, color="gray", linestyle="--", alpha=0.4)
    ax_a.set_ylabel("2100 / 2015 Ratio")
    ax_a.set_title("A. Global Change by Indicator (SSP126)")
    ax_a.legend(fontsize=7)

    # ---- Panel B: Correlation heatmap across indicators (logit, 2050) ----
    ax_b = fig.add_subplot(gs[0, 2])
    n_ind = len(indicators_list)
    corr_mat = np.zeros((n_ind, n_ind))
    for i, ki in enumerate(indicators_list):
        for j, kj in enumerate(indicators_list):
            if i == j:
                corr_mat[i, j] = 1.0
                continue
            d1 = _load(ki, "SSP126")
            d2 = _load(kj, "SSP126")
            if "logit" not in d1 or "logit" not in d2:
                continue
            s1 = d1["logit"].set_index("iso")[2050]
            s2 = d2["logit"].set_index("iso")[2050]
            common = s1.index.intersection(s2.index)
            x, y = s1[common].values, s2[common].values
            mask = (x > 0) & (y > 0) & np.isfinite(x) & np.isfinite(y)
            if mask.sum() > 5:
                corr_mat[i, j] = np.corrcoef(np.log(x[mask]), np.log(y[mask]))[0, 1]
    im = ax_b.imshow(corr_mat, cmap="RdBu_r", vmin=0, vmax=1, aspect="auto")
    ax_b.set_xticks(range(n_ind))
    ax_b.set_yticks(range(n_ind))
    ax_b.set_xticklabels([cfg.name[:12] for cfg in INDICATORS.values()],
                          rotation=45, ha="right", fontsize=7)
    ax_b.set_yticklabels([cfg.name[:12] for cfg in INDICATORS.values()], fontsize=7)
    ax_b.set_title("B. Indicator Correlation (logit, 2050)")
    plt.colorbar(im, ax=ax_b, shrink=0.8)

    # ---- Panel C: Scenario comparison (TFC, all methods) ----
    ax_c = fig.add_subplot(gs[1, 0])
    for m in METHODS:
        vals = []
        for sc in SCENARIOS:
            data = _load("tfc", sc)
            if m in data:
                vals.append(float(data[m][2100].sum()))
            else:
                vals.append(0)
        ax_c.plot([s.replace("SSP", "") for s in SCENARIOS], vals,
                  'o-', color=METHOD_COLORS[m], linewidth=1.8, markersize=7,
                  label=METHOD_LABELS[m])
    ax_c.set_ylabel("Global TFC 2100 (TJ)")
    ax_c.set_title("C. TFC by Scenario (2100)")
    ax_c.legend(fontsize=7)

    # ---- Panel D: Top-10 country TFC shares (SSP126, 2100) ----
    ax_d = fig.add_subplot(gs[1, 1])
    data = _load("tfc", "SSP126")
    if "logit" in data:
        shares = data["logit"].set_index("iso")[2100]
        shares = shares / shares.sum()
        top10 = shares.nlargest(10)
        colors = plt.cm.viridis(np.linspace(0.2, 0.9, 10))
        ax_d.barh(range(10)[::-1], top10.values[::-1], color=colors[::-1])
        ax_d.set_yticks(range(10))
        ax_d.set_yticklabels([i.upper() for i in top10.index[::-1]], fontsize=8)
        ax_d.set_xlabel("Share of global TFC")
        ax_d.set_title("D. Top 10 Country Shares (Logit, SSP126, 2100)")

    # ---- Panel E: Convergence diagnosis ----
    ax_e = fig.add_subplot(gs[1, 2])
    from compare.common.downscale import convergence_gamma, convergence_weight, CONVERGENCE_YEAR_DEFAULT
    for sc in SCENARIOS:
        y_c = CONVERGENCE_YEAR_DEFAULT[sc]
        gamma = convergence_gamma(y_c)
        w_vals = [convergence_weight(y, gamma) for y in YEARS]
        ax_e.plot(YEARS, w_vals, linewidth=1.5, label=f"{sc} (y_c={y_c})")
    ax_e.axhline(y=1.0, color="gray", linestyle="--", alpha=0.3)
    ax_e.axhline(y=0.99, color="gray", linestyle=":", alpha=0.3)
    ax_e.set_ylabel("Kaya convergence weight w(t)")
    ax_e.set_title("E. Convergence Weight by Scenario")
    ax_e.legend(fontsize=7)

    fig.suptitle("Global Summary — Multi-Indicator × Multi-Method × Multi-Scenario",
                 fontsize=14, y=1.01)
    out = OUTPUT_PLOTS_DIR / "global_summary.png"
    fig.savefig(out, bbox_inches="tight")
    plt.close(fig)
    return out


# ═══════════════════════════════════════════════════════════
# 保留兼容旧接口（单场景版本仍可用）
# ═══════════════════════════════════════════════════════════

def plot_indicator_dashboard(indicator_key: str, scenario: str = "SSP126") -> Path | None:
    """Legacy: 单指标单场景仪表板。建议使用 plot_indicator_dashboard_all_scenarios。"""
    return plot_indicator_dashboard_all_scenarios(indicator_key)


def plot_summary_dashboard(scenario: str = "SSP126") -> Path | None:
    """Legacy: TFC 汇总仪表板。"""
    return plot_indicator_dashboard_all_scenarios("tfc")


# ═══════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════

def generate_all_plots() -> list[Path]:
    """生成所有对比图表。"""
    outputs = []

    # ---- Phase 1: 多场景合并仪表板 (8 indicators → 8 plots) ----
    print("  Multi-scenario dashboards...")
    for key in INDICATORS:
        try:
            out = plot_indicator_dashboard_all_scenarios(key)
            if out:
                outputs.append(out)
        except Exception as e:
            print(f"    WARNING dashboard {key}: {e}")

    # ---- Phase 2: 多场景合并份额 (6 shares → 6 plots) ----
    print("  Multi-scenario shares...")
    for share_key in DERIVED_SHARES:
        try:
            out = plot_share_all_scenarios(share_key)
            if out:
                outputs.append(out)
        except Exception as e:
            print(f"    WARNING share {share_key}: {e}")

    # ---- Phase 3: 收敛特性 ----
    print("  Convergence profile...")
    try:
        outputs.append(plot_convergence_profile())
    except Exception as e:
        print(f"    WARNING convergence: {e}")

    # ---- Phase 4: 散点图 (4 scenarios, 2050+2100) ----
    print("  Scatter plots...")
    for sc in SCENARIOS:
        try:
            out = plot_method_scatter_two_years(sc)
            if out:
                outputs.append(out)
        except Exception as e:
            print(f"    WARNING scatter {sc}: {e}")

    # ---- Phase 5: 全局汇总 ----
    print("  Global summary...")
    try:
        outputs.append(plot_global_summary())
    except Exception as e:
        print(f"    WARNING summary: {e}")

    return outputs


if __name__ == "__main__":
    paths = generate_all_plots()
    print(f"\nGenerated {len(paths)} plots:")
    for p in sorted(paths):
        print(f"  {p.name}")
