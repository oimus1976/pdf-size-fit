from __future__ import annotations

import argparse
import json
from pathlib import Path

from .monochrome_fit import MonochromeFitStatus, fit_monochrome_vector_pdf


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fit a diagnosed monochrome vector PDF by destructive fixed-300-dpi "
            "1-bit CCITT Group 4 rasterization."
        )
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-bytes", type=int, default=10_000_000)
    parser.add_argument(
        "--dpi",
        type=int,
        default=300,
        help="fixed validated resolution; values other than 300 are rejected",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = fit_monochrome_vector_pdf(
        args.pdf,
        args.output,
        target_bytes=args.target_bytes,
        dpi=args.dpi,
    )

    if args.as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status.value}")
        print(f"input: {result.input_size_bytes} bytes")
        print(f"target: {result.target_bytes} bytes")
        if result.output_size_bytes is not None:
            print(f"output: {result.output_size_bytes} bytes")
        print(f"route: {result.route}")
        print(f"rasterization: {result.dpi} dpi, {result.bits_per_pixel}-bit, {result.compression}")
        print(f"pages: {result.page_count}")
        print("reasons:")
        for reason in result.reasons:
            print(f"- {reason}")

    return 0 if result.status in {MonochromeFitStatus.FITTED, MonochromeFitStatus.SKIP} else 2


if __name__ == "__main__":
    raise SystemExit(main())
