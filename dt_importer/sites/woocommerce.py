"""WooCommerce (WordPress) – nền tảng bán hàng phổ biến; đường dẫn kiểu /danh-muc-san-pham/..., /san-pham/...

Đọc theo cấu trúc chuẩn của WooCommerce:
- tên h1.product_title, mã .sku, giá .summary .price (ưu tiên giá khuyến mãi <ins>)
- ảnh gốc từ .woocommerce-product-gallery (data-large_image / link ảnh lớn)
- mô tả từ tab "Mô tả" (#tab-description), thông số từ bảng "Thông tin bổ sung" (woocommerce-product-attributes)
- phiên bản (màu, kích cỡ...) từ dữ liệu data-product_variations của form chọn phiên bản
"""
from .base import SiteAdapter

DETECT_JS = r"""
() => /woocommerce|single-product|post-type-archive-product|tax-product_cat/.test(document.body.className || '')
      || !!document.querySelector('.woocommerce-product-gallery, form.variations_form, ul.products li.product, meta[name="generator"][content*="WooCommerce"]')
"""

WOO_JS = r"""
(sel) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const abs = u => { try { return u ? new URL(u, location.href).href : null; } catch (e) { return null; } };
  const q = (s) => { if (!s) return null; try { return document.querySelector(s); } catch (e) { return null; } };
  const summary = q('.summary, .entry-summary, .product-summary') || document;
  const out = {};
  const nameEl = q(sel.name) || q('h1.product_title, .product_title, .summary h1');
  if (nameEl) out.name = norm(nameEl.textContent);
  const skuEl = q(sel.sku) || q('.sku_wrapper .sku, .product_meta .sku, span.sku');
  if (skuEl) { const t = norm(skuEl.textContent); if (t && !/^(n\/a|không có|đang cập nhật)$/i.test(t)) out.sku = t; }
  // giá: ưu tiên giá đang bán (<ins>) khi có khuyến mãi; khoảng giá (biến thể) → lấy giá đầu
  const priceBox = q(sel.price) || summary.querySelector('p.price, span.price, .price');
  if (priceBox) {
    const cur = priceBox.querySelector('ins .woocommerce-Price-amount, ins .amount') || priceBox.querySelector('.woocommerce-Price-amount, .amount');
    out.price_text = norm((cur || priceBox).textContent);
    out.has_price_box = true;
  }
  // ảnh gốc của gallery
  const gal = [];
  const gbox = q(sel.gallery) || q('.woocommerce-product-gallery, .product-images, .images');
  if (gbox) {
    gbox.querySelectorAll('.woocommerce-product-gallery__image, [data-thumb], img').forEach(el => {
      const img = el.tagName === 'IMG' ? el : el.querySelector('img');
      const a = el.tagName === 'A' ? el : el.querySelector('a[href]');
      const c = [img && img.getAttribute('data-large_image'), a && /\.(jpe?g|png|webp|gif)(\?|$)/i.test(a.getAttribute('href') || '') ? a.getAttribute('href') : null,
                 img && img.getAttribute('data-src'), img && img.getAttribute('src')].filter(Boolean)
                 .filter(u => !u.startsWith('data:') && !/placeholder/i.test(u));
      if (c.length) gal.push(abs(c[0]));
    });
  }
  out.gallery = [...new Set(gal)];
  // mô tả gốc (tab Mô tả), mô tả ngắn
  const desc = q(sel.description) || q('#tab-description, .woocommerce-Tabs-panel--description, .woocommerce-product-details__description');
  if (desc) {
    const c = desc.cloneNode(true);
    c.querySelectorAll('h2:first-child').forEach(h => { if (/^(mô tả|description)/i.test(norm(h.textContent))) h.remove(); });
    out.description_html = c.innerHTML;
  }
  const short = q('.woocommerce-product-details__short-description');
  if (short) out.short_html = short.innerHTML;
  // bảng thông số (Thông tin bổ sung)
  out.attributes = [...document.querySelectorAll('table.woocommerce-product-attributes tr, table.shop_attributes tr')]
    .map(tr => [norm((tr.querySelector('th') || {}).textContent), norm((tr.querySelector('td') || {}).textContent)])
    .filter(r => r[0] && r[1]);
  // danh mục (breadcrumb)
  const bc = q('.woocommerce-breadcrumb, nav.breadcrumb, .breadcrumbs');
  if (bc) out.breadcrumb = [...bc.querySelectorAll('a, span:last-child')].map(e => norm(e.textContent)).filter(Boolean);
  // phiên bản
  const form = q('form.variations_form');
  if (form) {
    let vars = null;
    try { vars = JSON.parse(form.getAttribute('data-product_variations')); } catch (e) {}
    const labels = {};
    form.querySelectorAll('select[name^="attribute_"]').forEach(s => {
      const m = {}; s.querySelectorAll('option').forEach(o => { if (o.value) m[o.value] = norm(o.textContent); });
      const lab = form.querySelector(`label[for="${s.id}"]`);
      labels[s.name] = { title: lab ? norm(lab.textContent) : s.name.replace(/^attribute_(pa_)?/, ''), opts: m };
    });
    out.variation_form = true;
    out.variation_titles = Object.values(labels).map(l => l.title);
    if (Array.isArray(vars)) {
      out.variations = vars.map(v => {
        const parts = Object.entries(v.attributes || {}).map(([k, val]) => (labels[k] && labels[k].opts[val]) || val || '');
        const img = v.image || {};
        return { label: parts.filter(Boolean).join(' / '), sku: norm(v.sku || ''), price: v.display_price,
                 image: abs(img.full_src || img.url || img.src || ''), in_stock: v.is_in_stock !== false };
      });
    }
  }
  return out;
}
"""


class WooCommerceAdapter(SiteAdapter):
    platform = "woocommerce"

    @staticmethod
    def detect(page):
        return bool(page.evaluate(DETECT_JS))

    def enrich(self, page, data):
        from ..utils import parse_vnd
        w = page.evaluate(WOO_JS, self.profile.get("selectors") or {}) or {}
        self._woo = w
        if w.get("name"):
            data["name"] = w["name"]
        if w.get("sku"):
            data["sku"] = w["sku"]
        if w.get("has_price_box"):
            data["price_text"] = w.get("price_text") or ""
            data["price"] = parse_vnd(data["price_text"])
            data.setdefault("found", {})["price"] = bool(data["price"])
        if w.get("gallery"):
            data["gallery_images"] = w["gallery"]
            data["variant_images"] = []          # WooCommerce: ảnh phiên bản lấy từ dữ liệu phiên bản
        if w.get("description_html"):
            data["description_html"] = w["description_html"]
            data.setdefault("found", {})["features"] = True
        if w.get("attributes") and not (data.get("spec") or {}).get("rows"):
            data["spec"] = {"headers": [], "rows": [{"label": k, "values": [v]} for k, v in w["attributes"]],
                            "text": [], "images": [], "source": "woocommerce"}
            data.setdefault("found", {})["specs"] = True
        if w.get("breadcrumb"):
            data["breadcrumb"] = w["breadcrumb"]
        if self._woo.get("name") and (w.get("description_html") or w.get("attributes") or w.get("has_price_box")):
            data.setdefault("found", {})["product_view"] = True
        return data

    def extra_images(self, data):
        # WooCommerce: ảnh phiên bản thường chỉ là 1 phần bộ ảnh → giữ thêm ảnh gallery phía sau
        return list(data.get("gallery_images") or [])

    def variants(self, scraper, base_url, base):
        w = getattr(self, "_woo", None) or {}
        if not w.get("variation_form"):
            return None
        vs = w.get("variations")
        if not vs:
            scraper.log("    ! Sản phẩm có phiên bản nhưng web không đưa sẵn dữ liệu phiên bản → không tạo phiên bản")
            return []
        from ..utils import parse_vnd
        out = []
        for v in vs:
            if not v.get("label") and not v.get("sku"):
                continue
            value = v.get("sku") or v.get("label")
            out.append({"label": v.get("label") or "", "sku": v.get("sku") or v.get("label"), "value": value,
                        "price": parse_vnd(v.get("price")) if v.get("price") not in (None, "") else base.get("price"),
                        "image": v.get("image") or None})
        titles = ", ".join(w.get("variation_titles") or [])
        scraper.log(f"    · Đọc {len(out)} phiên bản WooCommerce ({titles})")
        return out
