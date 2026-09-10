from __future__ import annotations

import argparse
import json
from pathlib import Path

from .diagnose import diagnose_pdf


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose an oversized PDF and propose a PoC routing class."
    )
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--target-bytes", type=int, default=10_000_000)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    diagnosis = diagnose_pdf(args.pdf, target_bytes=args.target_bytes)
    if args.as_json:
        print(json.dumps(diagnosis.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(f"route: {diagnosis.route.value}")
        print(f"file: {diagnosis.file_size_bytes} bytes")
        print(f"target: {diagnosis.target_bytes} bytes")
        print(f"pages: {diagnosis.page_count}")
        print(
            f"image streams: {diagnosis.image_stream_bytes} bytes ({diagnosis.image_ratio:.1%})"
        )
        print(
            f"vector/content streams: {diagnosis.vector_stream_bytes} bytes ({diagnosis.vector_ratio:.1%})"
        )
        if diagnosis.rendered_color_fraction is not None:
            print(f"rendered color fraction: {diagnosis.rendered_color_fraction:.1%}")
        print("reasons:")
        for reason in diagnosis.reasons:
            print(f"- {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
