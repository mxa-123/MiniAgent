# -*- coding: utf-8 -*-
"""MiniAgent 入口：python run.py [--web] [-p "问题"]"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from miniagent.cli import main  # noqa: E402

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
