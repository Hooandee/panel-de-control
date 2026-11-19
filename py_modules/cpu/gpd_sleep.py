"""Restore Panel-owned CPUs before sleep on the GPD Win 5."""
from pathlib import Path
import sys


def restore(root="/"):
    from cpu.gpd_win5 import GpdWin5Cores, is_gpd_win5

    if not is_gpd_win5(root):
        return True
    cores = GpdWin5Cores(root)
    with cores.transaction():
        return cores.release()


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    sys.exit(0 if restore() else 1)
