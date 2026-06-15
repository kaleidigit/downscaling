from pathlib import Path
from typing import Callable

BASE_DIR = Path(__file__).resolve().parents[2]       # downscaling/
COMPARE_DIR = BASE_DIR / "compare"
OUTPUT_DIR = COMPARE_DIR / "output"
OUTPUT_DATA_DIR = OUTPUT_DIR / "data"
OUTPUT_LOGS_DIR = OUTPUT_DIR / "logs"
OUTPUT_PLOTS_DIR = OUTPUT_DIR / "plots"
for _d in (OUTPUT_DIR, OUTPUT_DATA_DIR, OUTPUT_LOGS_DIR, OUTPUT_PLOTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)
DATA_DIR = BASE_DIR / "data"

SCENARIOS = ["SSP126", "SSP245", "SSP434", "SSP460"]
YEARS = list(range(2015, 2101, 5))   # 2015, 2020, ..., 2100

MAPPING_PATH = DATA_DIR / "mapping" / "gcam_country_region1120.xlsx"

# ---------- 国家级 GDP / 人口 ----------
GDP_COUNTRY_DIR = DATA_DIR / "ssp"
POP_COUNTRY_DIR = DATA_DIR / "ssp"
GDP_REGION_DIR = DATA_DIR / "ssp"
POP_REGION_DIR = DATA_DIR / "ssp"

# ---------- 新 IEA WORLDBAL 全历史数据 ----------
IEA_WORLDBAL_PATH = DATA_DIR / "iea" / "WORLDBAL_1970_2024.csv"

# ---------- SSP 完整数据库 ----------
SSP_DATABASE_PATH = DATA_DIR / "ssp" / "SSP_database_v9.csv"


def gdp_country_path(scenario: str) -> Path:
    return GDP_COUNTRY_DIR / f"GDP_{scenario.lower()}.xlsx"


def pop_country_path(scenario: str) -> Path:
    return POP_COUNTRY_DIR / f"pop_{scenario}.xlsx"


def gdp_region_path(scenario: str) -> Path:
    return GDP_REGION_DIR / f"GDP_region_{scenario.lower()}.xlsx"


def pop_region_path(scenario: str) -> Path:
    # pop_region_ 前缀避免 macOS 大小写不敏感与国家级 pop_SSP*.xlsx 冲突
    return POP_REGION_DIR / f"pop_region_{scenario.lower()}.xlsx"


# ═══════════════════════════════════════════════════
# 指标配置注册表
# ═══════════════════════════════════════════════════

class IndicatorConfig:
    """单个指标的数据源和筛选参数。"""

    def __init__(
        self,
        key: str,
        sdg: str,
        name: str,
        unit: str,
        # GCAM 数据
        gcam_dir: Path,
        gcam_file_pattern: str,
        gcam_filter_col: str | None,    # 筛选列名 (fuel/sector/subsector)
        gcam_filter_value: str | None,   # 筛选值 (None=全加总)
        gcam_extra_filter: dict | None,  # 额外筛选 {col: value}
        gcam_unit_factor: float,          # → 目标单位
        # IEA 基准
        iea_path: Path,
        iea_flow: str,
        iea_product: str,
        iea_year: str,
        iea_unit_factor: float = 1.0,     # IEA → 目标单位转换
        # EDGAR 基准（备选）
        edgar_path: Path | None = None,
        edgar_filter_col: str | None = None,
        edgar_filter_value: str | None = None,
        # 输出
        output_prefix: str = "",
    ):
        self.key = key
        self.sdg = sdg
        self.name = name
        self.unit = unit
        self.gcam_dir = gcam_dir
        self.gcam_file_pattern = gcam_file_pattern
        self.gcam_filter_col = gcam_filter_col
        self.gcam_filter_value = gcam_filter_value
        self.gcam_extra_filter = gcam_extra_filter or {}
        self.gcam_unit_factor = gcam_unit_factor
        self.iea_path = iea_path
        self.iea_flow = iea_flow
        self.iea_product = iea_product
        self.iea_year = iea_year
        self.iea_unit_factor = iea_unit_factor
        self.edgar_path = edgar_path
        self.edgar_filter_col = edgar_filter_col
        self.edgar_filter_value = edgar_filter_value
        self.output_prefix = output_prefix or key.upper()

    def gcam_path(self, scenario: str) -> Path:
        fn = self.gcam_file_pattern.replace("{scenario}", scenario).replace("{scenario_lower}", scenario.lower())
        return self.gcam_dir / fn


# 路径常量 (统一指向 data/ 目录)
GCAM_TFC_DIR = DATA_DIR / "gcam"
GCAM_ELEC_DIR = DATA_DIR / "gcam"
GCAM_REN_ELEC_DIR = DATA_DIR / "gcam"
GCAM_PRIMARY_DIR = DATA_DIR / "gcam"
GCAM_REGIONAL_ENERGY_DIR = DATA_DIR / "gcam"
GCAM_INDUSTRY_DIR = DATA_DIR / "gcam"
GCAM_CO2_DIR = DATA_DIR / "gcam"

IEA_TFC_PATH = DATA_DIR / "iea" / "TFC_IEA.xlsx"
IEA_ELEC_PATH = DATA_DIR / "iea" / "Electricity output_IEA.xlsx"
IEA_TES_PATH = DATA_DIR / "iea" / "TES_IEA.xlsx"
IEA_TES_FOSSIL_PATH = DATA_DIR / "iea" / "TES_fossil_IEA.xlsx"
IEA_TES_REN_PATH = DATA_DIR / "iea" / "TES_Ren_IEA.xlsx"
IEA_TFC_REN_PATH = DATA_DIR / "iea" / "TFC_Ren_IEA.xlsx"
IEA_TFC_ELEC_PATH = DATA_DIR / "iea" / "TFC_ElE_IEA.xlsx"
IEA_ELEC_OUTPUT_PATH = DATA_DIR / "iea" / "ELEoutput_IEA.xlsx"
IEA_ELEC_REN_PATH = DATA_DIR / "iea" / "ELEoutput_Ren_IEA.xlsx"
EDGAR_INDUSTRY_PATH = DATA_DIR / "emissions" / "industry_emissions.xlsx"
EDGAR_CO2_PATH = DATA_DIR / "emissions" / "IEA_EDGAR_CO2_1970_2023.xlsx"


def _gcam_tfc_path(scenario: str) -> Path:
    return GCAM_TFC_DIR / f"TFC_{scenario}.xlsx"


def _gcam_elec_path(scenario: str) -> Path:
    return GCAM_ELEC_DIR / f"GCAM_elec_{scenario}.xlsx"


def _gcam_ren_elec_path(scenario: str) -> Path:
    return GCAM_REN_ELEC_DIR / f"GCAM_renewable_elec_{scenario}.xlsx"


def _gcam_primary_path(scenario: str) -> Path:
    return GCAM_PRIMARY_DIR / f"primary energy consumption by region_{scenario}.xlsx"


def _gcam_regional_energy_path(scenario: str) -> Path:
    return GCAM_REGIONAL_ENERGY_DIR / f"区域能源消费_{scenario.lower()}.xlsx"


def _gcam_industry_path(scenario: str) -> Path:
    return GCAM_INDUSTRY_DIR / f"GCAM_industry_{scenario}.xlsx"


def _gcam_co2_path(scenario: str) -> Path:
    return GCAM_CO2_DIR / f"CO2_emissions_{scenario}.xlsx"


# 兼容 — gcam_tfc_path 供 logit/kaya/dscale 旧模块使用
gcam_tfc_path = _gcam_tfc_path

# ═══════════════════════════════════════════════════
# 全部指标注册
# ═══════════════════════════════════════════════════

INDICATORS: dict[str, IndicatorConfig] = {
    # ---- SDG7 ----
    "tfc": IndicatorConfig(
        key="tfc", sdg="SDG7", name="Total Final Consumption",
        unit="TJ",
        gcam_dir=GCAM_TFC_DIR,
        gcam_file_pattern="TFC_{scenario}.xlsx",
        gcam_filter_col="fuel", gcam_filter_value=None,  # 全 fuel 加总
        gcam_extra_filter=None,
        gcam_unit_factor=1_000_000,  # EJ → TJ
        iea_path=IEA_TFC_PATH,
        iea_flow="Total final consumption", iea_product="Total", iea_year="2015",
        output_prefix="TFC",
    ),
    "electricity": IndicatorConfig(
        key="electricity", sdg="SDG7", name="Electricity Output",
        unit="TJ",
        gcam_dir=GCAM_ELEC_DIR,
        gcam_file_pattern="GCAM_elec_{scenario}.xlsx",
        gcam_filter_col="output", gcam_filter_value="electricity",
        gcam_extra_filter={"subsector": "Total", "technology": "Total"},
        gcam_unit_factor=3.6,  # GWh → TJ
        iea_path=IEA_ELEC_PATH, iea_unit_factor=3.6,  # GWh → TJ
        iea_flow="Electricity output", iea_product="Total", iea_year="2015",
        output_prefix="Elec",
    ),
    "tes": IndicatorConfig(
        key="tes", sdg="SDG7", name="Total Energy Supply",
        unit="TJ",
        gcam_dir=GCAM_PRIMARY_DIR,
        gcam_file_pattern="primary energy consumption by region_{scenario}.xlsx",
        gcam_filter_col="fuel", gcam_filter_value=None,
        gcam_extra_filter=None,
        gcam_unit_factor=1_000_000,  # EJ → TJ
        iea_path=IEA_TES_PATH,
        iea_flow="Total energy supply", iea_product="Total", iea_year="2015",
        output_prefix="TES",
    ),
    "fossil_tes": IndicatorConfig(
        key="fossil_tes", sdg="SDG12", name="Fossil Fuel TES",
        unit="TJ",
        gcam_dir=GCAM_PRIMARY_DIR,
        gcam_file_pattern="primary energy consumption by region_{scenario}.xlsx",
        gcam_filter_col="fuel", gcam_filter_value=None,  # 需手动筛选化石燃料
        gcam_extra_filter=None,
        gcam_unit_factor=1_000_000,
        iea_path=IEA_TES_FOSSIL_PATH,
        iea_flow="Total energy supply", iea_product="", iea_year="2015",
        output_prefix="FossilTES",
    ),
    "renewable_tes": IndicatorConfig(
        key="renewable_tes", sdg="SDG7", name="Renewable TES",
        unit="TJ",
        gcam_dir=GCAM_REGIONAL_ENERGY_DIR,
        gcam_file_pattern="区域能源消费_{scenario_lower}.xlsx",
        gcam_filter_col="fuel", gcam_filter_value="renewable",
        gcam_extra_filter=None,
        gcam_unit_factor=1_000_000,
        iea_path=IEA_TES_REN_PATH,
        iea_flow="Total energy supply", iea_product="Total of renewable energy sources", iea_year="2015",
        output_prefix="RenTES",
    ),
    "green_elec": IndicatorConfig(
        key="green_elec", sdg="SDG12", name="Green Electricity Output",
        unit="TJ",
        gcam_dir=GCAM_REN_ELEC_DIR,
        gcam_file_pattern="GCAM_renewable_elec_{scenario}.xlsx",
        gcam_filter_col="output", gcam_filter_value="electricity",
        gcam_extra_filter={"subsector": "Renewable", "technology": "Renewable"},
        gcam_unit_factor=3.6,  # GWh → TJ
        iea_path=IEA_ELEC_REN_PATH, iea_unit_factor=3.6,  # GWh → TJ
        iea_flow="Electricity output", iea_product="Total of renewable energy sources", iea_year="2015",
        output_prefix="GreenElec",
    ),
    # ---- SDG9 ----
    "industry_co2": IndicatorConfig(
        key="industry_co2", sdg="SDG9", name="Industrial Direct CO2",
        unit="Mt",
        gcam_dir=GCAM_INDUSTRY_DIR,
        gcam_file_pattern="GCAM_industry_{scenario}.xlsx",
        gcam_filter_col="sector", gcam_filter_value="industry",
        gcam_extra_filter=None,
        gcam_unit_factor=0.001,  # Gg CO₂ → Mt
        iea_path=IEA_TFC_PATH,  # placeholder — uses EDGAR
        iea_flow="", iea_product="", iea_year="2015",
        edgar_path=EDGAR_INDUSTRY_PATH,
        edgar_filter_col="sector", edgar_filter_value="industry",
        output_prefix="IndustryCO2",
    ),
    # ---- SDG13 ----
    "co2_emissions": IndicatorConfig(
        key="co2_emissions", sdg="SDG13", name="CO2 Emissions",
        unit="MTC",
        gcam_dir=GCAM_CO2_DIR,
        gcam_file_pattern="CO2_emissions_{scenario}.xlsx",
        gcam_filter_col=None, gcam_filter_value=None,
        gcam_extra_filter=None,
        gcam_unit_factor=1.0,
        iea_path=IEA_TFC_PATH,  # placeholder — uses EDGAR
        iea_flow="", iea_product="", iea_year="2015",
        edgar_path=EDGAR_CO2_PATH,
        edgar_filter_col=None, edgar_filter_value=None,
        output_prefix="CO2",
    ),
}

# 份额指标（由无界量计算得出，不直接降尺度）
DERIVED_SHARES = {
    "fossil_share": {
        "sdg": "SDG12", "name": "Fossil Fuel Share of TES",
        "numerator": "fossil_tes", "denominator": "tes",
    },
    "renewable_share": {
        "sdg": "SDG7", "name": "Renewable Share of TES",
        "numerator": "renewable_tes", "denominator": "tes",
    },
    "electrification_rate": {
        "sdg": "SDG7", "name": "Electrification Rate",
        "numerator": "electricity", "denominator": "tfc",
    },
    "green_elec_share": {
        "sdg": "SDG12", "name": "Green Electricity Share",
        "numerator": "green_elec", "denominator": "electricity",
    },
    "energy_intensity": {
        "sdg": "SDG7", "name": "Energy Intensity (TFC/GDP)",
        "numerator": "tfc", "denominator": "gdp",
    },
    "per_capita_co2": {
        "sdg": "SDG13", "name": "Per Capita CO2 Emissions",
        "numerator": "co2_emissions", "denominator": "population",
    },
}
