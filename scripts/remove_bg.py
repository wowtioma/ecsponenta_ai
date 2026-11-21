#!/usr/bin/env python
"""Убирает однотонный фон у изображения и сохраняет PNG с прозрачностью.

Алгоритм: оценивает цвет фона по углам, считает расстояние каждого пикселя до
фона, переводит его в альфу (0 — фон, 255 — объект, между — сглаженные края).
Цвет полупрозрачных пикселей восстанавливается (un-blend), чтобы не осталось
серой каймы от фона.

Использование:
    python scripts/remove_bg.py <src> <dst>
    python scripts/remove_bg.py in.jpg out.png --tol-min 6 --tol-max 70
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
from PIL import Image


def _estimate_bg(rgb: np.ndarray, inset: int = 12) -> np.ndarray:
    """Цвет фона — медиана по рамке, отступя от края (углы часто зашумлены JPEG)."""
    h, w = rgb.shape[:2]
    m = min(inset, h // 4, w // 4)
    band = np.concatenate(
        [
            rgb[m, m : w - m].reshape(-1, 3),
            rgb[h - m - 1, m : w - m].reshape(-1, 3),
            rgb[m : h - m, m].reshape(-1, 3),
            rgb[m : h - m, w - m - 1].reshape(-1, 3),
        ]
    )
    return np.median(band, axis=0)


def remove_bg(
    src: str, dst: str, tol_min: float = 15.0, tol_max: float = 70.0, edge_clear: int = 3
) -> dict:
    img = Image.open(src).convert("RGBA")
    arr = np.array(img)
    rgb = arr[:, :, :3].astype(np.float32)

    # 1. Цвет фона по внутренней рамке.
    bg = _estimate_bg(rgb)

    # 2. Расстояние до фона -> альфа.
    dist = np.sqrt(((rgb - bg[None, None, :]) ** 2).sum(axis=2))
    alpha255 = np.clip((dist - tol_min) / max(tol_max - tol_min, 1e-6), 0.0, 1.0) * 255.0
    alpha = alpha255 / 255.0

    # 3. Un-blend: pixel = a*fg + (1-a)*bg  =>  fg = (pixel - (1-a)*bg) / a
    fg = rgb.copy()
    mask = alpha > 0.02
    a = alpha[mask][:, None]
    fg[mask] = np.clip((rgb[mask] - (1.0 - a) * bg[None, :]) / a, 0.0, 255.0)

    out = arr.copy()
    out[:, :, :3] = fg.astype(np.uint8)
    out[:, :, 3] = alpha255.astype(np.uint8)

    # 4. Чистим шумную кромку по краю кадра.
    if edge_clear > 0:
        e = edge_clear
        out[:e, :, 3] = 0
        out[-e:, :, 3] = 0
        out[:, :e, 3] = 0
        out[:, -e:, 3] = 0

    Image.fromarray(out, "RGBA").save(dst, format="PNG", optimize=True)

    alpha_final = out[:, :, 3] / 255.0
    total = alpha_final.size
    return {
        "bg_rgb": tuple(int(x) for x in bg),
        "transparent_pct": round(float((alpha_final == 0).sum()) / total * 100, 1),
        "opaque_pct": round(float((alpha_final == 1).sum()) / total * 100, 1),
        "edge_pct": round(float(((alpha_final > 0) & (alpha_final < 1)).sum()) / total * 100, 1),
        "size": img.size,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Убрать однотонный фон -> прозрачный PNG")
    p.add_argument("src")
    p.add_argument("dst")
    p.add_argument("--tol-min", type=float, default=8.0)
    p.add_argument("--tol-max", type=float, default=60.0)
    args = p.parse_args()

    stats = remove_bg(args.src, args.dst, args.tol_min, args.tol_max)
    print(f"размер: {stats['size']}")
    print(f"фон: rgb{stats['bg_rgb']}")
    print(f"прозрачных: {stats['transparent_pct']}%  "
          f"непрозрачных: {stats['opaque_pct']}%  края: {stats['edge_pct']}%")
    print(f"сохранено: {args.dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
