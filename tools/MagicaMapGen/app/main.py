"""MagicaMapGen entry point.

Usage:
    python -m app.main [workdir]

The workdir holds generated maps and the progress file; it defaults to
``_mmg_work`` beside this package so nothing is ever written into the source tree.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main_window import run  # noqa: E402


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    workdir = Path(argv[0]) if argv else Path(__file__).resolve().parents[1] / "_mmg_work"
    return run(workdir)


if __name__ == "__main__":
    raise SystemExit(main())
