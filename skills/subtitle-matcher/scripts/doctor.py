#!/usr/bin/env python3
from __future__ import annotations

import sys

from subtitle_matcher import main


if __name__ == "__main__":
    raise SystemExit(main(["doctor", *sys.argv[1:]]))
