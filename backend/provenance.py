"""Metadados reproduzíveis para API e relatórios do Solver."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict


ENGINE_VERSION = "0.2.0"


@lru_cache(maxsize=1)
def _git_commit() -> str:
    configured = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT")
        or os.getenv("SOURCE_COMMIT")
    )
    if configured:
        return configured.strip()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return completed.stdout.strip()
    except Exception:
        return "desconhecido"


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def build_provenance(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") or []
    config = {key: value for key, value in payload.items() if key != "data"}
    return {
        "engine_version": ENGINE_VERSION,
        "git_commit": _git_commit(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "data_sha256": hashlib.sha256(_canonical_json(data).encode("utf-8")).hexdigest(),
        "config_sha256": hashlib.sha256(_canonical_json(config).encode("utf-8")).hexdigest(),
        "config": config,
    }
