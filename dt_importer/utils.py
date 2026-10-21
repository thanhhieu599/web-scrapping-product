import json
import re
import sys
import unicodedata
from pathlib import Path

# Bản đóng gói (.exe): dữ liệu/cấu hình nằm cạnh file .exe
FROZEN = getattr(sys, "frozen", False)
ROOT = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent


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


_CODE_TOKEN = re.compile(r"^[(\[]?(?=(?:\D*\d){3})[A-Z0-9]+(?:[-./][A-Z0-9]+)*[,;)\]]?$|^[A-Z]{1,4}\d{2,}[A-Z0-9-]*[,;]?$", re.I)


# ký hiệu tiêu chuẩn / cấp độ – không phải mã sản phẩm
_STANDARD = re.compile(r"^(IP\d{2}|EN\d+|ISO\d+|ANSI|TCVN\d*|ASTM\w*|CE|UV\d*|S[1-5]P?|SRC|ESD)[,;]?$", re.I)


def name_with_vendor(name, vendor):
    """Chèn nhà cung cấp vào tên sản phẩm.
    - Tên có mã SP  → chèn ngay trước mã đầu tiên: 'Hộp đựng dụng cụ 8450, 8424' → 'Hộp đựng dụng cụ Milwaukee 8450, 8424'
    - Tên không mã  → thêm vào cuối:              'Găng tay chống cắt' → 'Găng tay chống cắt Milwaukee'
    - Tên đã có nhà cung cấp → giữ nguyên.
    """
    name, vendor = (name or "").strip(), (vendor or "").strip()
    if not vendor or not name or vendor.lower() in name.lower():
        return name
    words = name.split()
    for i, w in enumerate(words):
        if i > 0 and _CODE_TOKEN.match(w) and not _STANDARD.match(w):
            return " ".join(words[:i] + [vendor] + words[i:])
    return f"{name} {vendor}"
