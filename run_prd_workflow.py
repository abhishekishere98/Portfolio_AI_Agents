from __future__ import annotations

import argparse
import json
from pathlib import Path

from prd_pipeline import PipelineOptions, run_prd_pipeline


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
    parser.add_argument(
        "--provider",
        default="local",
        choices=["local", "cloud"],
        help="Model provider for pipeline execution.",
    )
    parser.add_argument(
        "--cloud-model",
        default="",
        help="Optional cloud model identifier when provider is cloud.",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="Optional file path to persist full pipeline JSON output.",
    )
    args = parser.parse_args()

    prd_path = Path(args.input)
    prd_text = prd_path.read_text(encoding="utf-8")
    options = PipelineOptions(
        automation_framework=args.framework,
        provider=args.provider,
        cloud_model=args.cloud_model,
    )
    result = run_prd_pipeline(prd_text, options)

    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": result["status"],
                "input": str(prd_path.resolve()),
                "output_json": str(Path(args.output_json).resolve()) if args.output_json else "",
            },
            indent=2,
        )
    )
    return 0 if result["status"] == "APPROVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
