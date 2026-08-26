from __future__ import annotations

import argparse
import math
import random
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


def generate_image_heavy(path: Path, *, pages: int = 3, image_size: int = 1000) -> None:
    random.seed(260826)
    image = Image.new("RGB", (image_size, image_size))
    pixels = image.load()
    for y in range(image_size):
        for x in range(image_size):
            z = (x * 2654435761 + y * 2246822519) & 0xFFFFFFFF
            pixels[x, y] = ((z >> 16) & 255, (z >> 8) & 255, z & 255)

    w, h = A4
    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    for _ in range(pages):
        c.drawImage(ImageReader(image), 0, 0, width=w, height=h, preserveAspectRatio=False)
        c.showPage()
    c.save()


def generate_vector(path: Path, *, color: bool, pages: int = 4, repeats: int = 4500) -> None:
    w, h = A4
    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    palette = [(0.1, 0.35, 0.7), (0.65, 0.15, 0.55), (0.05, 0.55, 0.4), (0.9, 0.45, 0.1)]

    for pageno in range(pages):
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, w, h, stroke=0, fill=1)
        for i in range(repeats):
            z = (i * 2654435761 + pageno * 2246822519) & 0xFFFFFFFF
            x = 30 + (i % 30) * 18 + (z % 101) / 1000
            y = 40 + ((i // 30) % 40) * 18 + ((z >> 8) % 101) / 1000
            a = 9.0 + ((z >> 16) % 31) / 31.0
            d = 6.0 + ((z >> 21) % 29) / 29.0
            if color:
                r, g, b = palette[i & 3]
            else:
                shade = 0.05 + ((i & 3) * 0.04)
                r = g = b = shade
            c.setStrokeColorRGB(r, g, b)
            c.setLineWidth(0.28 + ((z >> 26) % 7) * 0.01)
            p = c.beginPath()
            p.moveTo(x, y)
            p.curveTo(x + a * 0.25, y + d * 1.8, x + a * 0.75, y - d * 0.4, x + a, y + d)
            p.curveTo(x + a * 0.78, y + d * 1.9, x + a * 0.15, y + d * 1.5, x, y)
            p.close()
            c.drawPath(p, stroke=1, fill=0)
        c.showPage()
    c.save()


def generate_small(path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
    c.drawString(72, 760, "small synthetic PDF")
    c.save()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    generate_small(args.out_dir / "small.pdf")
    generate_image_heavy(args.out_dir / "image_heavy.pdf", pages=max(1, round(3 * args.scale)))
    repeats = max(500, round(4500 * args.scale))
    pages = max(1, round(4 * args.scale))
    generate_vector(args.out_dir / "vector_mono.pdf", color=False, pages=pages, repeats=repeats)
    generate_vector(args.out_dir / "vector_color.pdf", color=True, pages=pages, repeats=repeats)

    for path in sorted(args.out_dir.glob("*.pdf")):
        print(f"{path.name}: {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
