"""会话级共享资源，避免测试参数化时的重复 I/O。"""

import pytest
import pandas as pd

from compare.common.mapping import load_mapping, build_region_members, EXCLUDED_ISO
from compare.common.config import SCENARIOS, INDICATORS


@pytest.fixture(scope="session")
def mapping():
    """会话级：180 国→32 区域映射，所有测试共享。"""
    return load_mapping()


@pytest.fixture(scope="session")
def region_members(mapping):
    """会话级：{region: [member_dicts]}，所有测试共享。"""
    return build_region_members(mapping)


@pytest.fixture(scope="session")
def single_region_isos(region_members):
    """会话级：单国区域的 ISO 列表。"""
    isos = []
    for mlist in region_members.values():
        valid = [m for m in mlist if m["iso"] not in EXCLUDED_ISO]
        if len(valid) == 1:
            isos.append(valid[0]["iso"])
    return isos
