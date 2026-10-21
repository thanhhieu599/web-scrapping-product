import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config(path=None):
    path = Path(path) if path else ROOT / "config.json"
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    # Đường dẫn tương đối tính từ thư mục ứng dụng
    for key in ("profile_dir", "output_dir"):
        p = Path(cfg.get(key) or key)
        cfg[key] = str(p if p.is_absolute() else ROOT / p)
    return cfg


def parse_vnd(text):
    """'2.940.000 ₫' -> 2940000. Trả None nếu không đọc được."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text)
    # bỏ phần thập phân kiểu ',00' hoặc '.00' ở cuối (nếu có)
    s = re.sub(r"[.,]00\s*(₫|đ|vnđ|vnd)?\s*$", r" \1", s, flags=re.I)
    digits = re.sub(r"\D", "", s)
    return int(digits) if digits else None


def format_vnd(value):
    if value is None:
        return ""
    return f"{int(value):,}".replace(",", ".") + " ₫"


def slugify(text, max_len=60):
    text = unicodedata.normalize("NFD", str(text or ""))
    text = text.replace("đ", "d").replace("Đ", "D")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return (text or "san-pham")[:max_len]


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
