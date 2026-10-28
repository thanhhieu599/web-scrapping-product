"""Danh bạ nhà cung cấp + bộ đọc theo nền tảng web.

THÊM NHÀ CUNG CẤP MỚI: thêm 1 mục vào sites.json (cạnh file chạy), ví dụ
    "tenmien.vn": {"name": "Tên NCC", "platform": "woocommerce", "vendor": "Tên NCC"}
Các khoá dùng được (đều tuỳ chọn):
    name            tên hiển thị trong log
    platform        "auto" (tự nhận) | "magento" | "woocommerce" | "generic"
    vendor          Nhà cung cấp mặc định (dùng khi ô Nhà cung cấp để trống)
    product_type    Loại sản phẩm mặc định (dùng khi ô Loại để trống)
    content         "auto" | "features_specs" (Đặc điểm + Thông số) | "description" (mô tả gốc + bảng thuộc tính)
                    | "description_only" (chỉ mô tả gốc)
    description_images  false = bỏ ảnh trong mô tả gốc (mặc định true)
    name_cut        ["–", " - "] = tên lấy đến trước ký tự này (bỏ phần quảng cáo phía sau)
    variant_attribute   tên thuộc tính phiên bản mặc định (vd "Màu sắc") khi ô "Tên thuộc tính" để trống
    image_mode, product_link_pattern, listing_max_pages, image_url_strip_params   (ghi đè config.json)
    selectors       CSS selector riêng: name, sku, price, variant_images, features, specs, description, gallery
Web chưa có trong sites.json vẫn chạy được: tự nhận nền tảng (Magento / WooCommerce / web thường).
"""
import json
from pathlib import Path
from urllib.parse import urlparse

from ..utils import ROOT
from .base import SiteAdapter
from .magento import MagentoAdapter
from .woocommerce import WooCommerceAdapter

ADAPTERS = {"generic": SiteAdapter, "magento": MagentoAdapter, "woocommerce": WooCommerceAdapter}
OVERRIDABLE = ("image_mode", "product_link_pattern", "listing_max_pages", "image_url_strip_params", "max_images")


def load_sites(path=None):
    path = Path(path) if path else ROOT / "sites.json"
    if not path.is_absolute():
        path = ROOT / path
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        return {k.lower().strip(): v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}
    except (OSError, ValueError):
        return {}


def profile_for(url, sites):
    """Hồ sơ nhà cung cấp theo tên miền của link (khớp cả tên miền con, bỏ www)."""
    host = (urlparse(url).hostname or "").lower()
    host = host[4:] if host.startswith("www.") else host
    best = None
    for dom, prof in sites.items():
        d = dom[4:] if dom.startswith("www.") else dom
        if host == d or host.endswith("." + d):
            if not best or len(d) > len(best[0]):
                best = (d, prof)
    prof = dict(best[1]) if best else {}
    prof.setdefault("name", host or "web")
    prof.setdefault("platform", "auto")
    prof.setdefault("content", "auto")
    prof["_domain"] = best[0] if best else host
    return prof


def merged_cfg(cfg, profile):
    """config.json + phần ghi đè của nhà cung cấp."""
    out = dict(cfg)
    for k in OVERRIDABLE:
        if k in profile:
            out[k] = profile[k]
    sel = dict(cfg.get("source_selectors") or {})
    sel.update({k: v for k, v in (profile.get("selectors") or {}).items() if v})
    out["source_selectors"] = sel
    return out


def adapter_for(page, profile):
    """Bộ đọc theo nền tảng khai báo, hoặc tự nhận nền tảng từ trang đang mở."""
    plat = (profile.get("platform") or "auto").lower()
    if plat in ADAPTERS:
        return ADAPTERS[plat](profile)
    for cls in (WooCommerceAdapter, MagentoAdapter):
        try:
            if cls.detect(page):
                return cls(profile)
        except Exception:
            pass
    return SiteAdapter(profile)
