from __future__ import annotations

import sys
from pathlib import Path

SHADOW_PYTHON = Path(__file__).resolve().parents[1]
if str(SHADOW_PYTHON) not in sys.path:
    sys.path.insert(0, str(SHADOW_PYTHON))
