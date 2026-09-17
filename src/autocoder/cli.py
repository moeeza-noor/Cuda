"""Command-line interface (spec sections 20, 27, 35)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .core.orchestrator import Orchestrator


def _confirm(command: str, reason: str) -> bool:
    """Interactive confirmation for REQUIRES_CONFIRMATION commands (spec 11, 24)."""
    if not sys.stdin.isatty():
        return False
    sys.stdout.write(f"\n[confirm] run sensitive command?\n  $ {command}\n"
                     f"  reason: {reason}\n  [y/N] ")
    sys.stdout.flush()
    return sys.stdin.readline().strip().lower() in {"y", "yes"}


def _print_report(report: dict) -> None:
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"Status:            {report['status']}")
    print(f"Project:           {report['project']}")
    tech = report.get("technology", {})
    if tech:
        print(f"Technology:        {tech.get('language', '')} / "
              f"{tech.get('backend', '')} / {tech.get('database', '')}")
    print(f"Tasks completed:   {report['tasks_completed']}")
    print(f"Tasks failed:      {report['tasks_failed']}")
    print(f"Tests:             {report['tests'].get('summary', 'n/a')}")
    acc = report["acceptance"]
    print(f"Acceptance:        {acc['met']}/{acc['total']} criteria met")
    for crit, ok in acc["detail"].items():
        print(f"    [{'x' if ok else ' '}] {crit}")
    if report.get("assumptions"):
        print("Assumptions:")
        for a in report["assumptions"]:
            print(f"    - {a}")
    print(f"Files ({len(report['files'])}):")
    for f in report["files"]:
        print(f"    - {f}")
    print(f"How to run:        {report['how_to_run']}")
    print("=" * 60)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="autocoder",
        description="Autonomous software-engineering agent.",
    )
    parser.add_argument("requirement", nargs="?",
                        help="natural-language application requirement")
    parser.add_argument("-w", "--workspace", default=None,
                        help="workspace directory (default: cwd)")
    parser.add_argument("--resume", action="store_true",
                        help="resume from persisted state")
    parser.add_argument("--json", action="store_true",
                        help="print the final report as JSON")
    parser.add_argument("--serve", action="store_true",
                        help="launch the developer web UI instead of running")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args(argv)

    config = Config.load(workspace=args.workspace)

    if args.serve:
        from .ui.server import serve

        serve(config, port=args.port)
        return 0

    if not args.requirement and not args.resume:
        parser.error("a requirement is required (or use --resume / --serve)")

    orch = Orchestrator(config, confirm=_confirm)
    report = orch.run(args.requirement or "", resume=args.resume)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)
    return 0 if report["status"] == "COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
