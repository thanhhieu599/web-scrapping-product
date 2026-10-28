"""WooCommerce (WordPress) – nền tảng bán hàng phổ biến; đường dẫn kiểu /danh-muc-san-pham/..., /san-pham/...
Hỗ trợ giao diện mặc định và theme Flatsome (rất phổ biến ở VN, vd delivietnam.com.vn).

Đọc theo cấu trúc chuẩn của WooCommerce:
- tên h1.product_title, mã .sku, giá .summary .price (ưu tiên giá khuyến mãi <ins>; "Liên hệ" → không giá)
- ảnh gốc từ .woocommerce-product-gallery (data-large_image / link ảnh lớn)
- mô tả từ tab "Mô tả" (#tab-description), thông số từ bảng "Thông tin bổ sung" (woocommerce-product-attributes)
- phiên bản (màu, kích cỡ...) – lần lượt thử:
    1) dữ liệu data-product_variations (giá, mã, ảnh từng phiên bản)
    2) danh sách chọn / ô màu (swatch) của form phiên bản
    3) dòng chữ "Màu sắc: Đen, Xanh" trong phần thông tin, hoặc dòng cùng tên trong bảng thuộc tính
"""
import re

from .base import SiteAdapter

DETECT_JS = r"""
() => /woocommerce|single-product|post-type-archive-product|tax-product_cat/.test(document.body.className || '')
      || !!document.querySelector('.woocommerce-product-gallery, form.variations_form, ul.products li.product, .product-small.box, meta[name="generator"][content*="WooCommerce"]')
"""

WOO_JS = r"""
(sel) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim();
  const abs = u => { try { return u ? new URL(u, location.href).href : null; } catch (e) { return null; } };
  const q = (s) => { if (!s) return null; try { return document.querySelector(s); } catch (e) { return null; } };
  const summary = q('.product-info.summary, .summary.entry-summary, .entry-summary, .summary, .product-summary') || document;
  const out = {};
  const nameEl = q(sel.name) || q('h1.product_title, h1.product-title, .product_title, .summary h1');
  if (nameEl) out.name = norm(nameEl.textContent);
  const skuEl = q(sel.sku) || q('.product_meta .sku, .sku_wrapper .sku, span.sku');
  if (skuEl) { const t = norm(skuEl.textContent); if (t && !/^(n\/a|không có|đang cập nhật)$/i.test(t)) out.sku = t; }
  // giá: ưu tiên giá đang bán (<ins>) khi có khuyến mãi; khoảng giá (biến thể) → lấy giá đầu; "Liên hệ" → không có giá
  const priceBox = q(sel.price) || summary.querySelector('p.price, span.price, .price-wrapper .price, .price');
  out.has_price_box = !!priceBox;
  if (priceBox) {
    const cur = priceBox.querySelector('ins .woocommerce-Price-amount, ins .amount') || priceBox.querySelector('.woocommerce-Price-amount, .amount');
    out.price_text = cur ? norm(cur.textContent) : (/\d/.test(priceBox.textContent) ? norm(priceBox.textContent) : '');
  }
  // ảnh gốc của gallery (mỗi ô ảnh lớn 1 ảnh; không lấy ảnh thu nhỏ bên dưới)
  const pick = (el) => {
    const img = el.tagName === 'IMG' ? el : el.querySelector('img');
    const a = el.tagName === 'A' ? el : el.querySelector('a[href]');
    const ahref = a && /\.(jpe?g|png|webp|gif)(\?|$)/i.test(a.getAttribute('href') || '') ? a.getAttribute('href') : null;
    const c = [img && img.getAttribute('data-large_image'), ahref, img && img.getAttribute('data-src'),
               img && img.getAttribute('data-lazy-src'), img && img.getAttribute('src')]
      .filter(u => u && !u.startsWith('data:') && !/placeholder|lazy[-_]?load|blank\.gif/i.test(u));
    return c.length ? abs(c[0]) : null;
  };
  const gbox = q(sel.gallery) || q('.woocommerce-product-gallery, .product-gallery, .product-images, .images');
  let cells = gbox ? [...gbox.querySelectorAll('.woocommerce-product-gallery__image')] : [];
  if (!cells.length && gbox) cells = [...gbox.querySelectorAll('[data-thumb], img')];
  out.gallery = [...new Set(cells.map(pick).filter(Boolean))];
  // mô tả gốc (tab Mô tả)
  const desc = q(sel.description) || q('#tab-description, .woocommerce-Tabs-panel--description, .product-page-description, .woocommerce-product-details__description');
  if (desc) {
    const c = desc.cloneNode(true);
    const first = c.firstElementChild;
    if (first && /^h[1-6]$/i.test(first.tagName) && /^(mô tả|description)$/i.test(norm(first.textContent))) first.remove();
    out.description_html = c.innerHTML;
  }
  const short = q('.woocommerce-product-details__short-description, .product-short-description');
  if (short) out.short_html = short.innerHTML;
  // bảng thông số (Thông tin bổ sung)
  out.attributes = [...document.querySelectorAll('table.woocommerce-product-attributes tr, table.shop_attributes tr')]
    .filter(tr => !tr.closest('.related, .related-products-wrapper, .upsells'))
    .map(tr => [norm((tr.querySelector('th') || {}).textContent), norm((tr.querySelector('td') || {}).textContent)])
    .filter(r => r[0] && r[1]);
  // dòng chữ "Tên: giá trị 1, giá trị 2" trong phần thông tin sản phẩm (vd "Màu sắc: Đen, Xanh")
  out.text_attrs = [];
  if (summary !== document) {
    for (const el of summary.querySelectorAll('p, div, li, span, td')) {
      if (el.closest('form.variations_form, .product_meta, .price, .woocommerce-product-details__short-description, .product-short-description')) continue;
      if ([...el.children].some(c => /^(P|DIV|LI|TD|UL|TABLE)$/.test(c.tagName))) continue;
      const m = norm(el.textContent).match(/^([^:]{2,30}):\s*(.{1,200})$/);
      if (!m || /^(sku|mã|thẻ|tags?|danh mục|categor|giá)/i.test(m[1])) continue;
      out.text_attrs.push([norm(m[1]), m[2].split(/\s*[,;\/|]\s*/).map(norm).filter(Boolean)]);
    }
  }
  // danh mục (breadcrumb)
  const bc = q('.woocommerce-breadcrumb, nav.breadcrumbs, .breadcrumbs');
  if (bc) out.breadcrumb = [...bc.querySelectorAll('a')].map(e => norm(e.textContent)).filter(Boolean);
  // phiên bản
  const form = q('form.variations_form');
  out.options = [];                 // [{title, name, values:[{value, label}]}] – từ danh sách chọn / ô màu
  if (form) {
    out.variation_form = true;
    let vars = null;
    try { vars = JSON.parse(form.getAttribute('data-product_variations')); } catch (e) {}
    const groups = {};
    form.querySelectorAll('select[name^="attribute_"], select[data-attribute_name]').forEach(s => {
      const name = s.getAttribute('data-attribute_name') || s.name;
      const lab = (s.id && form.querySelector(`label[for="${s.id}"]`)) || (s.closest('tr') || {}).querySelector?.('th, .label');
      const g = groups[name] = groups[name] || { name, title: lab ? norm(lab.textContent) : '', values: [] };
      s.querySelectorAll('option').forEach(o => { if (o.value && !g.values.some(v => v.value === o.value)) g.values.push({ value: o.value, label: norm(o.textContent) }); });
    });
    // ô màu / swatch (Variation Swatches, Flatsome ux-swatch...)
    document.querySelectorAll('[data-attribute_name]:not(select)').forEach(box => {
      const name = box.getAttribute('data-attribute_name');
      const g = groups[name] = groups[name] || { name, title: '', values: [] };
      box.querySelectorAll('[data-value]').forEach(o => {
        const val = o.getAttribute('data-value'); if (!val) return;
        const label = norm(o.getAttribute('data-title') || o.getAttribute('data-name') || o.getAttribute('title') || o.getAttribute('aria-label') || o.textContent) || val;
        const ex = g.values.find(v => v.value === val);
        if (ex) { if (!ex.label || ex.label === val) ex.label = label; } else g.values.push({ value: val, label });
      });
    });
    for (const g of Object.values(groups)) {
      if (!g.title) g.title = decodeURIComponent(g.name.replace(/^attribute_(pa_)?/, '')).replace(/[-_]/g, ' ');
      out.options.push(g);
    }
    out.variation_titles = out.options.map(g => g.title);
    if (Array.isArray(vars)) {
      const labelOf = (k, val) => { const g = groups[k]; const o = g && g.values.find(v => v.value === val); return (o && o.label) || val || ''; };
      out.variations = vars.map(v => {
        const parts = Object.entries(v.attributes || {}).map(([k, val]) => labelOf(k, val));
        const img = v.image || {};
        return { label: parts.filter(Boolean).join(' / '), sku: norm(v.sku || ''), price: v.display_price,
                 image: abs(img.full_src || img.url || img.src || ''), in_stock: v.is_in_stock !== false };
      });
    }
  }
  return out;
}
"""


def _code(label):
    """'Xanh lá' → 'XANH-LA' (để ghép mã phiên bản)."""
    from ..utils import slugify
    return slugify(label).upper()


def _same(a, b):
    from ..utils import slugify
    return bool(a) and bool(b) and slugify(a) == slugify(b)


class WooCommerceAdapter(SiteAdapter):
    platform = "woocommerce"

    @staticmethod
    def detect(page):
        return bool(page.evaluate(DETECT_JS))

    def enrich(self, page, data):
        from ..utils import parse_vnd
        w = page.evaluate(WOO_JS, self.profile.get("selectors") or {}) or {}
        self._woo = w
        found = data.setdefault("found", {})
        if w.get("name"):
            data["name"] = w["name"]
        if w.get("sku"):
            data["sku"] = w["sku"]
        elif w.get("name"):
            data["sku"] = ""                     # web có ô SKU nhưng để trống / "N/A" → không đoán mã
        if w.get("has_price_box") or w.get("name"):
            data["price_text"] = w.get("price_text") or ""
            price = parse_vnd(data["price_text"])
            data["price"] = price or None        # "Liên hệ" / 0 ₫ → không có giá
            found["price"] = bool(data["price"])
        if w.get("gallery"):
            data["gallery_images"] = w["gallery"]
            data["variant_images"] = []          # WooCommerce: ảnh phiên bản lấy từ dữ liệu phiên bản
        if w.get("description_html"):
            data["description_html"] = w["description_html"]
            found["features"] = True
        if w.get("attributes"):
            data["spec"] = {"headers": [], "rows": [{"label": k, "values": [v]} for k, v in w["attributes"]],
                            "text": [], "images": [], "source": "woocommerce"}
            found["specs"] = True
            found["spec_source"] = "woocommerce"
        if w.get("breadcrumb"):
            data["breadcrumb"] = w["breadcrumb"]
        if w.get("name") and (w.get("description_html") or w.get("attributes") or w.get("sku")
                              or w.get("has_price_box") or w.get("gallery")):
            found["product_view"] = True
            found["listing"] = False
        return data

    # ---------- phiên bản ----------
    def _wanted(self, scraper):
        return (getattr(scraper, "variant_attr", "") or self.profile.get("variant_attribute") or "").strip()

    def variants(self, scraper, base_url, base):
        w = getattr(self, "_woo", None) or {}
        want = self._wanted(scraper)
        sku = (base.get("sku") or "").strip()
        out, how = [], ""
        vs = [v for v in (w.get("variations") or []) if v.get("label") or v.get("sku")]
        if vs:
            from ..utils import parse_vnd
            for v in vs:
                price = parse_vnd(v.get("price")) if v.get("price") not in (None, "") else None
                out.append({"label": v.get("label") or "", "sku": v.get("sku") or "", "value": v.get("label") or v.get("sku"),
                            "price": price or base.get("price"), "image": v.get("image") or None})
            how = "dữ liệu phiên bản"
        else:
            labels, title = self._option_labels(w, want)
            if labels:
                out = [{"label": l, "sku": "", "value": l, "price": base.get("price"), "image": None} for l in labels]
                how = f"thuộc tính '{title}'"
        if not out:
            if w.get("variation_form"):
                scraper.log("    ! Sản phẩm có phiên bản nhưng không đọc được danh sách → không tạo phiên bản")
                return []
            return [] if w.get("name") else None
        # mã từng phiên bản: dùng mã của web; trống / trùng → MÃ SP + tên phiên bản (vd EG057-DEN)
        skus = [v["sku"] for v in out]
        for v in out:
            if not v["sku"] or skus.count(v["sku"]) > 1 or v["sku"] == sku:
                v["sku"] = f"{sku}-{_code(v['label'])}" if sku else _code(v["label"])
        scraper.log(f"    · Đọc {len(out)} phiên bản WooCommerce từ {how}: {', '.join(v['value'] for v in out)}")
        return out

    def _option_labels(self, w, want):
        """Danh sách giá trị của thuộc tính phiên bản (ưu tiên đúng tên thuộc tính đang tạo)."""
        groups = [(g.get("title") or "", [v.get("label") or v.get("value") for v in g.get("values") or []])
                  for g in w.get("options") or []]
        groups = [(t, [x for x in vals if x]) for t, vals in groups if vals]
        if groups:
            hit = next((g for g in groups if _same(g[0], want)), None) if want else None
            return (hit or groups[0])[1], (hit or groups[0])[0]
        if not want:
            return [], ""
        for title, vals in list(w.get("text_attrs") or []) + [(k, re.split(r"\s*[,;/|]\s*", v)) for k, v in w.get("attributes") or []]:
            vals = [x.strip() for x in vals if x and x.strip()]
            if _same(title, want) and len(vals) >= 2:
                return vals, title
        return [], ""

    def extra_images(self, data):
        # WooCommerce: ảnh phiên bản thường chỉ là 1 phần bộ ảnh → giữ thêm ảnh gallery phía sau
        return list(data.get("gallery_images") or [])
