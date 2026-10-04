#!/usr/bin/env python3
import argparse
import json
import sys

from runner import run
from media import build_release_oemdrv
from workflow import static_check, status


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    sub.add_parser("build-release")
    sub.add_parser("run")
    sub.add_parser("status")
    args = parser.parse_args()

    if args.command == "check":
        print(json.dumps(static_check(), indent=2))
    elif args.command == "build-release":
        print(json.dumps(build_release_oemdrv(), indent=2, default=str))
    elif args.command == "run":
        result = run()
        print(json.dumps(result, indent=2))
        if result.get("status") != "PASS":
            sys.exit(1)
    elif args.command == "status":
        print(json.dumps(status(), indent=2))


if __name__ == "__main__":
    main()
