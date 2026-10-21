"""Ghép danh mục nhà cung cấp (nhiều cấp) → danh mục Sapo của D&T.

Bảng ghép: file danh_muc.csv (mở bằng Excel), 2 cột:
    Danh mục nguồn                         | Danh mục Sapo
    Dụng cụ cầm tay > Kìm                  | Dụng cụ cầm tay, Kìm
    Dụng cụ cầm tay > Kìm > Kìm cắt        | Dụng cụ cầm tay, Kìm, Kìm cắt
    Jobsite Enhancement > Storage          | Lưu trữ dụng cụ
    Tin tức                                | -            (dấu "-" = không gán danh mục)

Tra theo cấp sâu nhất trước: sản phẩm ở "Dụng cụ cầm tay > Kìm > Kìm mỏ nhọn" chưa có dòng riêng
sẽ dùng dòng "Dụng cụ cầm tay > Kìm". Đường dẫn chưa có trong bảng được tự thêm vào cuối file
(cột Sapo để trống) để bạn điền dần.
"""
import csv
import io
import unicodedata
from pathlib import Path

HEADER = ["Danh mục nguồn", "Danh mục Sapo"]
SEP = " > "


def _key(text):
    """So khớp không phân biệt hoa/thường, dấu tiếng Việt, khoảng trắng."""
    t = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    t = "".join(c for c in t if unicodedata.category(c) != "Mn").lower()
    parts = [" ".join(p.split()) for p in t.replace("›", ">").replace("»", ">").replace("/", ">").split(">")]
    return SEP.join(p for p in parts if p)


def split_names(text):
    return [x.strip() for x in str(text or "").replace(";", ",").split(",") if x.strip()]


class CategoryMap:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = {}          # key -> (đường dẫn gốc, [danh mục Sapo] hoặc None nếu chưa điền)
        self.order = []
        self.new_paths = []
        self.load()

    def load(self):
        if not self.path.exists():
            return
        raw = self.path.read_bytes().decode("utf-8-sig", errors="replace")
        first = raw.splitlines()[0] if raw.strip() else ""
        delim = max([",", ";", "\t"], key=first.count) if first else ","
        for i, row in enumerate(csv.reader(io.StringIO(raw), delimiter=delim)):
            if not row or not row[0].strip():
                continue
            if i == 0 and _key(row[0]) == _key(HEADER[0]):
                continue
            src = row[0].strip()
            dst = row[1].strip() if len(row) > 1 else ""
            k = _key(src)
            if k not in self.rows:
                self.order.append(k)
            self.rows[k] = (src, None if dst == "" else ([] if dst == "-" else split_names(dst)))

    def lookup(self, path):
        """→ (danh sách danh mục Sapo, dòng khớp) hoặc (None, None) nếu chưa có dòng nào đã điền."""
        for depth in range(len(path), 0, -1):
            k = _key(SEP.join(path[:depth]))
            if k in self.rows and self.rows[k][1] is not None:
                return self.rows[k][1], self.rows[k][0]
        return None, None

    def remember(self, path):
        """Ghi đường dẫn chưa có vào bảng (cột Sapo để trống) để người dùng điền."""
        if not path:
            return
        k = _key(SEP.join(path))
        if k not in self.rows:
            self.rows[k] = (SEP.join(path), None)
            self.order.append(k)
            self.new_paths.append(SEP.join(path))

    def save(self):
        if not self.new_paths and self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(HEADER)
        for k in self.order:
            src, dst = self.rows[k]
            w.writerow([src, "" if dst is None else ("-" if dst == [] else ", ".join(dst))])
        # utf-8-sig để Excel hiển thị đúng tiếng Việt
        self.path.write_text(buf.getvalue(), encoding="utf-8-sig", newline="")


def resolve(path, cmap, auto_levels=True):
    """Danh mục Sapo cho 1 sản phẩm → (danh sách, cách xác định)."""
    names, row = cmap.lookup(path) if cmap else (None, None)
    if names is not None:
        return names, f"theo bảng: {row}"
    if cmap:
        cmap.remember(path)
    if auto_levels and path:
        return list(path), "tự động theo tên từng cấp (chưa có trong bảng ghép)"
    return [], "chưa có trong bảng ghép"
