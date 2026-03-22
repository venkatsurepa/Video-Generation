"""Shared constants for pipeline handler modules."""

from __future__ import annotations

import tempfile
from pathlib import Path

_TMP_ROOT = Path(tempfile.gettempdir()) / "crimemill" / "worker"
_TMP_ROOT.mkdir(parents=True, exist_ok=True)
