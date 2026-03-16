from __future__ import annotations

import importlib
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[3]
if _REPO_ROOT.joinpath("cli").is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_SUBMODULES = (
    "agent_commands",
    "common",
    "config_commands",
    "discover_commands",
    "identity_commands",
    "main",
    "message_commands",
    "ops_commands",
    "output",
    "register_commands",
    "relay_commands",
    "transport_commands",
)

for _name in _SUBMODULES:
    _module = importlib.import_module(f"cli.{_name}")
    globals()[_name] = _module
    sys.modules[f"{__name__}.{_name}"] = _module

from cli.main import build_parser, main, run

__all__ = ["build_parser", "main", "run", *_SUBMODULES]
