#!/usr/bin/env python3
"""Query registered Qwen voices without synthesis or model changes."""
import argparse
import json
import logging
import sys

from common import load_env
from qwen_tts_client import QwenTTSClient


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file")
    args = parser.parse_args(argv)
    load_env(env_file=args.env_file, logger=logging.getLogger("speech.voices"))
    data = QwenTTSClient().request("/v1/voices")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        raise SystemExit(1)
