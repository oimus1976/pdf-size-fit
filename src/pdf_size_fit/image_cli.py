from __future__ import annotations

import argparse
import json
from pathlib import Path

from .image_fit import ImageFitStatus, fit_image_heavy_pdf


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fit an image-heavy PDF under a target byte size by recompressing image XObjects."
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--target-bytes", type=int, default=10_000_000)
    parser.add_argument("--min-quality", type=int, default=70)
    parser.add_argument(
        "--min-scale",
        type=float,
        default=0.50,
        help="minimum image scale allowed for the downsampling fallback (default: 0.50)",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    result = fit_image_heavy_pdf(
        args.pdf,
        args.output,
        target_bytes=args.target_bytes,
        min_quality=args.min_quality,
        min_scale=args.min_scale,
    )

    if args.as_json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"status: {result.status.value}")
        print(f"input: {result.input_size_bytes} bytes")
        print(f"target: {result.target_bytes} bytes")
        if result.output_size_bytes is not None:
            print(f"output: {result.output_size_bytes} bytes")
        if result.selected_scale is not None:
            print(f"selected image scale: {result.selected_scale:.0%}")
        if result.selected_quality is not None:
            print(f"selected JPEG quality: {result.selected_quality}")
        print(f"unique image XObjects replaced: {result.images_replaced}")
        if result.attempts:
            print("attempts:")
            for attempt in result.attempts:
                print(
                    f"- scale {attempt.scale:.0%}, quality {attempt.quality}: "
                    f"{attempt.size_bytes} bytes"
                )
        print("reasons:")
        for reason in result.reasons:
            print(f"- {reason}")

    return 0 if result.status in {ImageFitStatus.FITTED, ImageFitStatus.ALREADY_BELOW_TARGET} else 2


if __name__ == "__main__":
    raise SystemExit(main())
