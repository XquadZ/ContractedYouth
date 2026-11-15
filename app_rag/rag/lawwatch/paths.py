# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from rag.paths import APP, LAW_API_CURRENT, OUT, WORK

LAW_API_ROOT = WORK / "data_contract" / "law_api"
LAW_API_HISTORY = LAW_API_ROOT / "연혁"
LAW_VERSIONS = APP / "data_local" / "law_versions"
CRITERIA_VERSIONS = APP / "criteria" / "versions"
CRITERIA_PROPOSALS = APP / "criteria" / "proposals"
LAWWATCH_OUT = OUT / "lawwatch"
APPLIED_LOG = LAW_VERSIONS / "applied_log.json"
TARGET_LAWS_FILE = LAW_VERSIONS / "target_laws.json"

APPLY_RULES = ("contract_date", "in_force", "performance_period", "unknown")
