"""
方案 B：DSCALE 双路径法。

默认使用官方 DSCALE 算法（dscale_official）：
  - ENLONG: 官方 fit_funcs.LogLogFunc 区域回归
  - ENSHORT: 基年 EI + 2015-2020 IEA 观测趋势外推
  - 收敛: 官方 fun_max_tc_convergence（含 β 指数）
  - 仅修改输入输出层，计算层使用官方代码

如需使用旧版 common.downscale 统一引擎，设置 DSCALE_USE_LEGACY=1。
"""

import os
import pandas as pd
from ..common.config import INDICATORS
from ..common.downscale import load_baseline, load_gcam, load_iea_other, build_iea_baseline, run_indicator
from ..common.io import read_iea_historical_tfc


def downscale_tfc(scenario: str) -> pd.DataFrame:
    if os.environ.get("DSCALE_USE_LEGACY") == "1":
        return run_indicator("dscale", scenario, INDICATORS["tfc"])

    from .dscale_official import downscale_dscale_official

    cfg = INDICATORS["tfc"]
    iea_single = load_baseline(cfg)
    iea_other = load_iea_other(cfg)
    iea_baseline = build_iea_baseline(iea_single, iea_other, scenario)
    gcam = load_gcam(cfg, scenario)

    # 加载 IEA 历史数据 (1970-)
    from ..common.io import read_usda_gdp_historical, read_un_population_historical
    from .dscale_official import fit_enshort_countries

    iea_hist = read_iea_historical_tfc()

    # 加载 历史 GDP (USDA 1969-2017) 和人口 (UN 1950-2020)
    hist_gdp = read_usda_gdp_historical()
    hist_pop = read_un_population_historical()

    # 逐国历史回归
    enshort_params = fit_enshort_countries(iea_hist, hist_gdp, hist_pop)
    n_reg = len(enshort_params)
    print(f"  [DSCALE] IEA 历史: {len(iea_hist)}国, "
          f"GDP: {len(hist_gdp)}国, POP: {len(hist_pop)}国, "
          f"ENSHORT 回归: {n_reg}国")

    df = downscale_dscale_official(iea_baseline, gcam, scenario,
                                   enshort_params=enshort_params)

    # 写入输出
    from ..common.io import write_output_for
    from ..common.conservation import check_regional_conservation, check_global_conservation, write_log
    from ..common.config import OUTPUT_LOGS_DIR

    gcam_scen = gcam[gcam["Scenario"] == scenario]
    n_single = len(iea_single)
    n_baseline = len(iea_baseline)
    log_lines = [
        f"IEA 匹配统计: 单列国家 {n_single} 个, 合并后基准 {n_baseline} 个",
        f"DSCALE 历史回归: {n_reg} 国 (1970-2015 log-log), 其余 GDP 缩放",
    ]

    write_output_for(df, "dscale", scenario, cfg.output_prefix)
    log_path = write_log("dscale_" + cfg.key, log_lines + [
        check_regional_conservation(df, gcam_scen),
        check_global_conservation(df, gcam_scen),
    ])
    target_path = OUTPUT_LOGS_DIR / f"dscale_{cfg.key}_log.txt"
    if log_path != target_path:
        log_path.rename(target_path)

    return df
