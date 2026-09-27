"""One-command start for VideoLingo-MLX (mirrors upstream start.py bootstrap).

Picks an existing project environment, repairs it via run_installer.sh when
missing, then launches the Streamlit UI. The pip-import path is avoided so a
GUI/non-login shell outside conda still finds ffmpeg; st.py owns the managed
FFmpeg PATH setup (configure_ffmpeg).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONDA_ROOT = Path(os.environ.get("CONDA_PREFIX", "") or "/")


def python_candidates():
    """Ordered list of candidate interpreters for this project."""
    candidates = [ROOT / ".venv" / "bin" / "python"]
    if CONDA_ROOT.is_dir():
        candidates.append(CONDA_ROOT / "bin" / "python")
    return candidates


def pick_python():
    """Return the first usable interpreter, or None."""
    for python in python_candidates():
        if python.is_file():
            return python
    return None


def main() -> int:
    python = pick_python()
    if python is None:
        # No .venv and no active conda env: bootstrap via the existing installer.
        print("No project environment found; running run_installer.sh to set it up...")
        return subprocess.call(["bash", "run_installer.sh"], cwd=ROOT)

    # Preflight: make sure the managed FFmpeg pair is present (non-fatal, but
    # surfaces a clear error so a broken install is obvious before launch).
    subprocess.run(
        [str(python), "-c",
         "from runtime_libraries import configure_ffmpeg; configure_ffmpeg(required=False)"],
        cwd=ROOT, check=False)

    # Launch Streamlit; st.py calls configure_ffmpeg(required=True) for the session PATH.
    return subprocess.call([str(python), "-m", "streamlit", "run", "st.py"], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())