"""COGNIFY execution-service app package.

Startup helper: this service imports the shared ``packages.*`` libraries,
which live at the repository root. When launched from the service
directory (``uvicorn app.main:app`` from ``services/execution-service``),
the root is not on ``sys.path`` yet, so add it — but only when
``packages`` is otherwise unimportable and the computed root really
contains it (a no-op under Docker, where ``/code`` is already on the
path).
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import packages  # noqa: F401
except ImportError:
    _ROOT = Path(__file__).resolve().parents[3]
    if (_ROOT / "packages").is_dir() and str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))

__all__: list[str] = []
