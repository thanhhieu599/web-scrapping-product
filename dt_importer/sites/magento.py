"""Magento (vd milwaukeetool.com.vn)."""
from .base import SiteAdapter

DETECT_JS = r"""
() => /catalog-product-view|catalog-category-view|page-products/.test(document.body.className || '')
      || !!document.querySelector('script[type="text/x-magento-init"]')
"""


class MagentoAdapter(SiteAdapter):
    platform = "magento"

    @staticmethod
    def detect(page):
        return bool(page.evaluate(DETECT_JS))

    def variants_fallback(self, scraper, base):
        """Quy cách là DANH SÁCH THẢ XUỐNG (không có ô để bấm) → đọc thẳng dữ liệu cấu hình phiên bản
        (jsonConfig / spConfig) có sẵn trong trang: tên model, giá, ảnh từng model."""
        from ..scraper import MAGENTO_JS
        from ..utils import parse_vnd
        try:
            mg = scraper.page.evaluate(MAGENTO_JS) or []
        except Exception:
            mg = []
        spec = base.get("spec") or {}
        heads = [h for h in (spec.get("headers") or []) if h]
        if not heads:                      # bảng không có dòng tiêu đề → dòng "Model / Mã sản phẩm" đầu bảng
            import re
            row = next((r for r in spec.get("rows") or [] if re.match(r"^(model|mã( sản phẩm| sp)?|quy cách)\b",
                                                                     (r.get("label") or "").strip(), re.I)), None)
            heads = [v for v in (row or {}).get("values") or [] if v]
        if len(mg) < 2:
            if len(heads) >= 2:
                scraper.log(f"    ! Bảng thông số có {len(heads)} model ({', '.join(heads)}) nhưng không đọc được ô Quy "
                            "cách / dữ liệu phiên bản → không tạo phiên bản. Gửi gói chẩn đoán để chỉnh.")
            return []
        out = []
        for m in mg:
            value = (m.get("sku") or m.get("label") or "").strip()
            price = parse_vnd(m.get("price")) if m.get("price") not in (None, "") else base.get("price")
            out.append({"label": m.get("label") or "", "sku": value, "value": value, "price": price, "image": m.get("image")})
        scraper.log(f"    · Đọc {len(out)} phiên bản từ dữ liệu cấu hình Magento (Quy cách dạng danh sách chọn)")
        return out
