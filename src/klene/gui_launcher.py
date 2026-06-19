from __future__ import annotations

import sys

from klene.gui import launch_gui


def main() -> int:
    launch_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
