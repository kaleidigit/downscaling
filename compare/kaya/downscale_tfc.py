"""方案 A：Kaya 收敛法（委托 common.downscale 统一引擎）。"""

import pandas as pd
from ..common.config import INDICATORS
from ..common.downscale import run_indicator


def downscale_tfc(scenario: str) -> pd.DataFrame:
    return run_indicator("kaya", scenario, INDICATORS["tfc"])
