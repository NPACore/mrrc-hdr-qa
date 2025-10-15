import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
# prefer local sources
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root))
