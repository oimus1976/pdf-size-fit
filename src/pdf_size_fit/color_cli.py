from __future__ import annotations

import argparse
import json
from pathlib import Path

from .color_fit import ColorFitStatus, fit_color_vector_pdf


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fit a diagnosed color vector PDF by destructive fixed-200-dpi "
            "1-bit CCITT Group 4 rasterization."
        )
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-bytes", type=int, default=10_000_000)
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Fixed whole-page rasterization DPI (must be 200)",
    )
    parser.add_argument(
        "--jpeg-quality",
        type=int,
        default=90,
        help="Fixed JPEG encoding quality (must be 90)",
    )
    parser.add_argument(
        "--allow-small-searchable-text-rasterization",
        action="store_true",
        help=(
            "explicitly allow rasterizing a searchable text layer only within the "
            "provisional PoC bounds"
        ),
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = fit_color_vector_pdf(
        args.pdf,
        args.output,
        target_bytes=args.target_bytes,
        dpi=args.dpi,
        jpeg_quality=args.jpeg_quality,
        allow_small_searchable_text_rasterization=(
            args.allow_small_searchable_text_rasterization
        ),
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
        print(
            f"rasterization: {result.dpi} dpi, {result.bits_per_pixel}-bit, {result.compression}"
        )
        print(f"pages: {result.page_count}")
        print("reasons:")
        for reason in result.reasons:
            print(f"- {reason}")

    return 0 if result.status in {ColorFitStatus.FITTED, ColorFitStatus.SKIP} else 2


if __name__ == "__main__":
    raise SystemExit(main())
