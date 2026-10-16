"""Path resolution helpers.

Bundled resources (reference country list, etc.) must always be located
relative to this package's own location on disk, never relative to the
process's current working directory. Data pack files are supplied as an
absolute ``pack_dir`` argument and are also resolved without reference to
the working directory.
"""
from __future__ import annotations

from pathlib import Path

# Resolved once, from this file's own location, so it is stable no matter
# where the process is invoked from.
PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parent

REFERENCE_DIR = PACKAGE_DIR / "reference"
REFERENCE_COUNTRIES_PATH = REFERENCE_DIR / "countries.json"

TRACKER_FILENAME = "VELARA_tracker.xlsx"
DASHBOARD_FILENAME = "dashboard_status.csv"


def resolve_pack_paths(pack_dir: str) -> dict[str, Path]:
    """Resolve the two expected input files inside ``pack_dir``.

    ``pack_dir`` must be an absolute path to a directory containing the
    tracker workbook and dashboard CSV. Raises FileNotFoundError if either
    file is missing.
    """
    base = Path(pack_dir)
    if not base.is_absolute():
        raise ValueError(f"pack_dir must be an absolute path, got: {pack_dir!r}")
    if not base.is_dir():
        raise FileNotFoundError(f"pack_dir is not a directory: {base}")

    tracker_path = base / TRACKER_FILENAME
    dashboard_path = base / DASHBOARD_FILENAME

    missing = [p.name for p in (tracker_path, dashboard_path) if not p.is_file()]
    if missing:
        raise FileNotFoundError(f"missing expected file(s) in pack_dir: {', '.join(missing)}")

    return {"tracker": tracker_path, "dashboard": dashboard_path}
