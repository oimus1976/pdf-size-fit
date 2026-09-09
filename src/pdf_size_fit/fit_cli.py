from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .fit import FitStatus, fit_pdf


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose a PDF and fit it through an existing supported safe route."
        )
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-bytes", type=int, default=10_000_000)
    parser.add_argument("--min-quality", type=int, default=70)
    parser.add_argument(
        "--min-scale",
        type=float,
        default=1.0,
        help=(
            "minimum image scale allowed for the image-route downsampling fallback; "
            "default 1.0 keeps downsampling disabled"
        ),
    )
    parser.add_argument(
        "--allow-small-searchable-text-rasterization",
        action="store_true",
        help=(
            "explicitly allow the monochrome route to rasterize a searchable text "
            "layer only within its existing conservative bounds"
        ),
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    result = fit_pdf(
        args.pdf,
        args.output,
        target_bytes=args.target_bytes,
        min_quality=args.min_quality,
        min_scale=args.min_scale,
        allow_small_searchable_text_rasterization=(
            args.allow_small_searchable_text_rasterization
        ),
    )

    if args.as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status.value}")
        print(f"route: {result.route.value}")
        print(f"input: {result.input_size_bytes} bytes")
        print(f"target: {result.target_bytes} bytes")
        if result.output_size_bytes is not None:
            print(f"output: {result.output_size_bytes} bytes")
        if result.delegated_route_status is not None:
            print(f"delegated route status: {result.delegated_route_status}")
        print("reasons:")
        for reason in result.reasons:
            print(f"- {reason}")

    return (
        0
        if result.status
        in {
            FitStatus.FITTED,
            FitStatus.ALREADY_BELOW_TARGET,
        }
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
