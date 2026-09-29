import sys
from pathlib import Path

# Make `src/` importable without an editable install.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
