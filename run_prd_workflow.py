from __future__ import annotations

import argparse
import json
from pathlib import Path

from prd.workflow import run_from_file


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the sequential PRD to QE agent workflow.")
    parser.add_argument("--input", default="sample_prd.md", help="Path to PRD markdown or text file.")
    parser.add_argument("--output", default="output", help="Folder where artifacts will be written.")
    parser.add_argument(
        "--framework",
        default="playwright",
        choices=["playwright", "selenium"],
        help="Automation framework for high priority journeys.",
    )
    args = parser.parse_args()

    result = run_from_file(args.input, args.output, automation_framework=args.framework)
    print(json.dumps({"status": result["status"], "output": str(Path(args.output).resolve())}, indent=2))
    return 0 if result["status"] == "APPROVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
