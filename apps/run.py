"""Compatibility wrapper for the installed ``telecraft`` command.

The public CLI implementation lives in :mod:`telecraft.cli` so it is included
in wheels.  Keeping this wrapper preserves the historical development command
``python apps/run.py ...``.
"""

from __future__ import annotations

from telecraft.cli import main

__all__ = ["main"]


if __name__ == "__main__":
    raise SystemExit(main())
