#!/usr/bin/env python3
import argparse
import json
import sys

from runner import run
from workflow import (
    fill,
    logs,
    prepare,
    shot,
    start,
    status,
    stop,
)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("prepare")
    sub.add_parser("run")
    sub.add_parser("start")
    sub.add_parser("logs")
    sub.add_parser("status")
    sub.add_parser("stop")

    p_fill = sub.add_parser("fill")
    p_fill.add_argument("name", choices=("recovery", "pin", "root"))

    p_shot = sub.add_parser("shot")
    p_shot.add_argument("name", nargs="?", default="latest")

    args = parser.parse_args()

    if args.command == "prepare":
        print(json.dumps(prepare(), indent=2))
    elif args.command == "run":
        result = run()
        print(json.dumps(result, indent=2))
        if result.get("status") != "PASS":
            sys.exit(1)
    elif args.command == "start":
        start()
    elif args.command == "fill":
        print(fill(args.name))
    elif args.command == "logs":
        print(logs())
    elif args.command == "shot":
        print(shot(args.name))
    elif args.command == "status":
        print(json.dumps(status(), indent=2))
    elif args.command == "stop":
        print(stop())


if __name__ == "__main__":
    main()
