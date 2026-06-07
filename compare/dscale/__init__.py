"""方案 B：DSCALE 双路径法。

提供两个版本：
  - downscale_tfc: 使用 common.downscale 统一引擎（简化 ENSHORT）
  - downscale_tfc_official: 使用官方 DSCALE fit_funcs + 完整收敛公式（含 β 指数）
"""
