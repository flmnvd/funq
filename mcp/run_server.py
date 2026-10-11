"""Run from this checkout without installing Funq's legacy nose test runner."""

import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from funq_mcp.__main__ import main

if __name__ == "__main__":
    main()
