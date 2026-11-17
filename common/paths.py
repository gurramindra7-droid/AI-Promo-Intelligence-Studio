"""Project paths. Importing this makes the ORIGINAL pipeline (src/) importable, unchanged."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
OUTPUTS = ROOT / "outputs"
DATA = ROOT / "data"
CONFIG = ROOT / "config.yaml"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
