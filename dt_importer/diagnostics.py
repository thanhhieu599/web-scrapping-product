"""Gom file chẩn đoán thành 1 file ZIP nhỏ để gửi người hỗ trợ (không kèm ảnh sản phẩm)."""
import zipfile
from datetime import datetime
from pathlib import Path

KEEP = {".txt", ".json", ".html", ".png", ".csv"}


def build_zip(output_dir, max_mb=45):
    out = Path(output_dir)
    zpath = out / f"chan-doan-{datetime.now():%Y%m%d-%H%M%S}.zip"
    files = [f for f in out.rglob("*")
             if f.is_file() and f.suffix.lower() in KEEP and "images" not in f.parts
             and not f.name.startswith("chan-doan-")]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)       # mới nhất trước
    total, limit = 0, max_mb * 1024 * 1024
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            size = f.stat().st_size
            if total + size > limit:
                continue
            z.write(f, f.relative_to(out))
            total += size
    return zpath
