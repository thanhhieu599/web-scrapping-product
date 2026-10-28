"""Bộ đọc mặc định (web thường). Bộ đọc của từng nền tảng kế thừa lớp này và chỉ ghi đè chỗ khác biệt."""
import re


class SiteAdapter:
    platform = "generic"

    def __init__(self, profile):
        self.profile = profile

    @staticmethod
    def detect(page):
        """True nếu trang đang mở thuộc nền tảng này (dùng khi platform = auto)."""
        return False

    def enrich(self, page, data):
        """Bổ sung / sửa dữ liệu sau khi bộ đọc chung đã đọc trang (tên, giá, mã, ảnh, mô tả...)."""
        return data

    def variants(self, scraper, base_url, base):
        """Danh sách phiên bản đọc trực tiếp từ dữ liệu của nền tảng, hoặc None để dùng cách bấm ô Quy cách."""
        return None

    def variants_fallback(self, scraper, base):
        """Khi không tìm được ô Quy cách để bấm."""
        return []

    def apply_rules(self, data):
        """Quy tắc khai báo trong sites.json, dùng được cho MỌI nền tảng:
        name_cut: ["–", " - "]  → tên lấy đến trước ký tự này (bỏ phần quảng cáo phía sau)."""
        cuts = self.profile.get("name_cut")
        if cuts and data.get("name"):
            name = data["name"]
            for sep in ([cuts] if isinstance(cuts, str) else cuts):
                pat = r"\s+" + re.escape(sep.strip()) + r"\s+" if sep.strip() else None
                parts = re.split(pat, name, maxsplit=1) if pat else [name]
                if len(parts) == 2 and len(parts[0].strip()) >= 3:
                    data["full_name"] = name
                    data["name"] = parts[0].strip()
                    break
        return data

    def extra_images(self, data):
        """Ảnh thêm vào sau ảnh của các phiên bản (khi đăng theo phiên bản)."""
        return []

    def content_mode(self, data):
        mode = (self.profile.get("content") or "auto").lower()
        if mode != "auto":
            return mode
        has_struct = bool(data.get("features")) or bool((data.get("spec") or {}).get("rows"))
        return "features_specs" if has_struct or not data.get("description_html") else "description"
