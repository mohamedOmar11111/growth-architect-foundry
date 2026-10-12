import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "core" / "engine"
sys.path.insert(0, str(ENGINE))
