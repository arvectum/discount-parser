from __future__ import annotations

import argparse
import json

from src.sources.runner import run_all


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discount-parser")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="Collect configured discount sources")
    parse_cmd.add_argument("--source", default=None, help="Run only one source key")
    parse_cmd.add_argument("--config", default="config/sources.yaml", help="Path to sources YAML")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "parse":
        results = run_all(path=args.config, only=args.source)
        print(json.dumps([result.__dict__ for result in results], ensure_ascii=False, indent=2, default=str))
        return 1 if any(result.errors and result.fetched == 0 for result in results) else 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
