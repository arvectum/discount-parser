from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from src.jobs.lifecycle import maintenance
from src.jobs.scheduler import run_scheduler
from src.qa.doctor import build_doctor_report
from src.qa.report import write_smoke_report
from src.runtime import run_all as run_runtime
from src.shared.config import get_settings
from src.sources.runner import run_all
from src.telegram.runner import run_bot
from src.web.launcher import run_web_panel


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="discount-parser")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_cmd = subparsers.add_parser("parse", help="Collect configured discount sources")
    parse_cmd.add_argument("--source", default=None, help="Run only one source key")
    parse_cmd.add_argument("--config", default=None, help="Path to sources YAML")

    subparsers.add_parser("maintenance", help="Expire and review stale offers")
    subparsers.add_parser("scheduler", help="Run collection, maintenance and autopost scheduler")
    subparsers.add_parser("bot", help="Run Telegram control bot")
    subparsers.add_parser("run", help="Run Telegram bot and scheduler together")
    subparsers.add_parser("web", help="Open local web control panel")
    subparsers.add_parser("doctor", help="Run local preflight checks before live testing")

    report_cmd = subparsers.add_parser("smoke-report", help="Write JSON delivery evidence from the current database")
    report_cmd.add_argument("--output", default="output/smoke_report.json", help="Destination JSON path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()

    if args.command == "parse":
        results = run_all(path=args.config or settings.sources_config_path, only=args.source)
        print(json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2, default=str))
        return 1 if any(result.errors and result.fetched == 0 for result in results) else 0

    if args.command == "maintenance":
        result = maintenance(stale_after_days=settings.stale_after_days)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "scheduler":
        run_scheduler()
        return 0

    if args.command == "bot":
        run_bot()
        return 0

    if args.command == "run":
        run_runtime()
        return 0

    if args.command == "web":
        run_web_panel()
        return 0

    if args.command == "doctor":
        report = build_doctor_report()
        print(report.to_json())
        return 0 if report.ok else 1

    if args.command == "smoke-report":
        path = write_smoke_report(args.output)
        print(path)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
