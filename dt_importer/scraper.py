"""Cào dữ liệu sản phẩm từ trang nhà cung cấp.

Không phụ thuộc class CSS của trang nguồn: dùng "chữ neo" hiển thị trên trang
(QUY CÁCH, Đặc điểm, Thông Số, BAO GỒM TRONG SẢN PHẨM...) để định vị dữ liệu.
Nếu trang nguồn đổi giao diện, có thể chỉ định CSS selector trong config.json
(mục "source_selectors") để ghi đè.
"""
import io
import re
from pathlib import Path
from urllib.parse import urlparse, urlencode, parse_qsl, urlunparse

from .browser import goto
from .utils import parse_vnd, slugify

COMMON_JS = r"""
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const low = s => norm(s).toLowerCase();
const qs = sel => { if (!sel) return null; try { return document.querySelector(sel); } catch (e) { return null; } };
const qsa = (root, sel) => { if (!sel) return []; try { return [...root.querySelectorAll(sel)]; } catch (e) { return []; } };
const abs = u => { try { return u ? new URL(u, location.href).href : null; } catch (e) { return null; } };
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'TEMPLATE', 'svg', 'SVG', 'PATH']);
const inChrome = e => !!e.closest('header, footer, nav');
"""

SCRAPE_JS = COMMON_JS + r"""
(cfg) => {
  const sel = cfg.selectors || {};
  const PRICE_RE = /^(\d{1,3}([.,\s]\d{3})+|\d{4,})\s*(₫|đ|vnđ|vnd)$/i;
  const all = [...document.body.querySelectorAll('*')].filter(e => !SKIP_TAGS.has(e.tagName));

  // ---------- GIÁ ----------
  let priceEl = qs(sel.price);
  if (!priceEl) {
    const m = all.filter(e => PRICE_RE.test(norm(e.textContent)) && !inChrome(e)
                     && !e.closest('del, s, strike, [class*=old], [class*=compare]'));
    const leaf = m.filter(e => ![...e.children].some(c => m.includes(c)));
    priceEl = leaf[0] || null;
  }
  const priceText = priceEl ? norm(priceEl.textContent) : '';

  // ---------- KHỐI THÔNG TIN (chứa tên + giá) ----------
  let info = null;
  if (priceEl) {
    let n = priceEl.parentElement;
    while (n && n !== document.body) {
      if (n.querySelector('h1, h2, h3')) { info = n; break; }
      n = n.parentElement;
    }
  }

  // ---------- TÊN ----------
  let nameEl = qs(sel.name);
  if (!nameEl && info) nameEl = info.querySelector('h1, h2, h3');
  if (!nameEl) nameEl = document.querySelector('h1');
  const name = nameEl ? norm(nameEl.textContent) : '';

  // ---------- MÃ SẢN PHẨM (chuỗi nhỏ ngay dưới tên) ----------
  const SKU_RE = /^(?=.*\d)[A-Z0-9]{1,10}([-./][A-Z0-9]{1,12})+$|^(?=.*\d)(?=.*[A-Z])[A-Z0-9]{5,20}$/i;
  let sku = '';
  const skuEl = qs(sel.sku);
  if (skuEl) sku = norm(skuEl.textContent);
  if (!sku && nameEl) {
    const root = info || document.body;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT);
    let started = false, steps = 0;
    while (walker.nextNode() && steps < 400) {
      const e = walker.currentNode;
      if (e === nameEl) { started = true; continue; }
      if (!started || nameEl.contains(e)) continue;
      steps++;
      const t = norm(e.textContent).replace(/^(mã|mã sp|mã sản phẩm|sku|model)\s*[:：]?\s*/i, '');
      if (e.children.length === 0 && t.length <= 40 && SKU_RE.test(t) && !PRICE_RE.test(t)) { sku = t; break; }
    }
  }
  if (!sku) {
    const m = (info || document.body).textContent.match(/(?:mã sản phẩm|mã sp|sku)\s*[:：]\s*([A-Z0-9][A-Z0-9\-./]{2,})/i);
    if (m) sku = m[1];
  }

  // ---------- Tìm "nhãn" theo chữ hiển thị ----------
  const findLabels = (texts) => {
    const t2 = texts.map(t => t.toLowerCase());
    const m = all.filter(e => {
      const t = low(e.textContent).replace(/[:：]$/, '').trim();
      return t.length < 40 && t2.includes(t);
    });
    return m.filter(e => ![...e.children].some(c => m.includes(c)));
  };
  // Nội dung đi sau 1 nhãn (accordion / tab / khối kế tiếp)
  const contentAfter = (label, test) => {
    let node = label;
    for (let lvl = 0; lvl < 6 && node && node !== document.body; lvl++) {
      for (let s = node.nextElementSibling; s; s = s.nextElementSibling) {
        if (test(s)) return s;
      }
      node = node.parentElement;
    }
    return null;
  };

  // ---------- ẢNH ----------
  const bestSrc = (img) => {
    const c = [];
    const a = img.closest('a');
    if (a && /\.(jpe?g|png|webp|gif|avif)(\?|$)/i.test(a.getAttribute('href') || '')) c.push(a.getAttribute('href'));
    ['data-zoom-image', 'data-large_image', 'data-large', 'data-full', 'data-original', 'data-zoom'].forEach(k => c.push(img.getAttribute(k)));
    const ss = img.getAttribute('srcset') || img.getAttribute('data-srcset');
    if (ss) {
      const best = ss.split(',').map(x => x.trim().split(/\s+/))
        .map(([u, w]) => ({ u, w: parseInt(w) || 0 })).sort((x, y) => y.w - x.w)[0];
      if (best) c.push(best.u);
    }
    c.push(img.getAttribute('data-src'), img.getAttribute('data-lazy-src'), img.currentSrc, img.getAttribute('src'));
    for (const u of c) { if (u && !u.startsWith('data:')) return abs(u); }
    return null;
  };
  const bgSrc = (e) => {
    const m = (e.getAttribute('style') || '').match(/background(?:-image)?\s*:\s*url\(['"]?([^'")]+)/i);
    return m ? abs(m[1]) : null;
  };
  const collectImgs = (root) => {
    const out = [];
    root.querySelectorAll('img').forEach(i => { const u = bestSrc(i); if (u) out.push(u); });
    if (!out.length) root.querySelectorAll('[style*="background"]').forEach(e => { const u = bgSrc(e); if (u) out.push(u); });
    return out;
  };

  let variantImages = [];
  const viRoot = qs(sel.variant_images);
  if (viRoot) variantImages = collectImgs(viRoot);
  if (!variantImages.length) {
    for (const lab of findLabels(['quy cách', 'quy cach', 'phân loại', 'kiểu'])) {
      const box = contentAfter(lab, s => s.querySelector('img') || s.tagName === 'IMG' || s.querySelector('[style*="background"]'));
      if (box) { variantImages = box.tagName === 'IMG' ? [bestSrc(box)] : collectImgs(box); break; }
    }
  }

  // Ảnh gallery (cột ảnh bên trái)
  let galleryImages = [];
  if (info) {
    let n = info.parentElement;
    while (n && n !== document.body) {
      const imgs = [...n.querySelectorAll('img')].filter(i => !info.contains(i));
      if (imgs.length) {
        galleryImages = imgs.filter(i => !/icon|logo|heart|wish/i.test((i.className || '') + (i.getAttribute('src') || '')))
                            .map(bestSrc).filter(Boolean);
        break;
      }
      n = n.parentElement;
    }
  }

  // ---------- ĐẶC ĐIỂM ----------
  let features = [];
  let featRoot = qs(sel.features);
  if (!featRoot) {
    for (const lab of findLabels(['đặc điểm', 'đặc điểm nổi bật', 'tính năng', 'tính năng nổi bật'])) {
      featRoot = contentAfter(lab, s => s.querySelector('li') || norm(s.textContent).length > 20);
      if (featRoot) break;
    }
  }
  if (featRoot) {
    const lis = [...featRoot.querySelectorAll('li')].map(li => norm(li.textContent)).filter(Boolean);
    features = lis.length ? lis
      : (featRoot.innerText || featRoot.textContent).split(/\n+/).map(norm).filter(Boolean);
  }

  // ---------- THÔNG SỐ ----------
  let specRoot = qs(sel.specs);
  if (!specRoot) {
    for (const lab of findLabels(['thông số', 'thông số kỹ thuật', 'thông số kĩ thuật'])) {
      specRoot = contentAfter(lab, s => s.querySelector('table, tr') || norm(s.textContent).length > 20);
      if (specRoot) break;
    }
  }
  const spec = { headers: [], rows: [], text: [] };
  if (specRoot) {
    const tables = specRoot.tagName === 'TABLE' ? [specRoot] : [...specRoot.querySelectorAll('table')];
    if (tables.length) {
      let skipQty = false;
      for (const tb of tables) {
        for (const tr of tb.querySelectorAll('tr')) {
          const cells = [...tr.children].filter(c => /^T[DH]$/.test(c.tagName)).map(c => norm(c.textContent));
          if (!cells.length || cells.every(c => !c)) continue;              // hàng ảnh / hàng trống
          const first = cells[0].toLowerCase();
          if (first.startsWith('bao gồm')) {                                 // KHÔNG lấy khối "Bao gồm trong sản phẩm"
            if (!spec.headers.length) spec.headers = cells.slice(1).map(c => c.replace(/\s*\(\d+\)\s*$/, ''));
            skipQty = true;
            continue;
          }
          if (skipQty && !cells[0] && cells.slice(1).some(c => /\(\d+\)\s*$/.test(c))) { skipQty = false; continue; }
          skipQty = false;
          if (!cells[0] && !spec.headers.length && cells.length > 1) { spec.headers = cells.slice(1); continue; }
          const filled = cells.filter(Boolean).length;
          if (filled === 1 && cells[0]) { spec.rows.push({ section: cells[0] }); continue; }
          spec.rows.push({ label: cells[0], values: cells.slice(1) });
        }
      }
    } else {
      spec.text = (specRoot.innerText || specRoot.textContent).split(/\n+/).map(norm).filter(Boolean)
                   .filter(t => !/^bao gồm/i.test(t));
    }
  }

  return {
    url: location.href, name, sku, price_text: priceText,
    variant_images: [...new Set(variantImages)].filter(Boolean),
    gallery_images: [...new Set(galleryImages)].filter(Boolean),
    features, spec,
    found: { price: !!priceEl, name: !!name, features: !!featRoot, specs: !!specRoot }
  };
}
"""

LINKS_JS = COMMON_JS + r"""
(cfg) => {
  const pat = cfg.pattern ? new RegExp(cfg.pattern, 'i') : null;
  const here = location.href.split('#')[0];
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const u = abs(a.getAttribute('href'));
    if (!u || !u.startsWith(location.origin) || u.split('#')[0] === here) continue;
    if (/\.(jpe?g|png|webp|gif|pdf)(\?|$)/i.test(u)) continue;
    if (pat) { if (!pat.test(u)) continue; }
    else if (!a.querySelector('img') || inChrome(a)) continue;   // mặc định: link có ảnh, ngoài menu
    out.push(u.split('#')[0]);
  }
  let next = document.querySelector('a[rel=next]');
  if (!next) next = [...document.querySelectorAll('.pagination a, [class*=paging] a, [class*=pagination] a')]
      .find(a => /^(›|»|>|sau|next|tiếp)$/i.test(norm(a.textContent)) || /next/i.test(a.className));
  return { links: [...new Set(out)], next: next ? abs(next.getAttribute('href')) : null };
}
"""


def upgrade_image_url(url, strip_params):
    """Bỏ tham số thu nhỏ ảnh (?width=..) để lấy ảnh gốc."""
    try:
        p = urlparse(url)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in strip_params]
        return urlunparse(p._replace(query=urlencode(q)))
    except ValueError:
        return url


class Scraper:
    def __init__(self, browser, cfg, log=print):
        self.cfg = cfg
        self.log = log
        # Dùng đúng User-Agent của trình duyệt, chỉ bỏ chữ "Headless" (một số web chặn bot theo chữ này)
        probe = browser.new_page()
        ua = probe.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
        probe.close()
        self.ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="vi-VN", user_agent=ua)
        self.page = self.ctx.new_page()

    def close(self):
        self.ctx.close()

    def _open(self, url):
        goto(self.page, url, self.log)
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        # cuộn để ảnh lazy-load hiện ra
        self.page.evaluate("""async () => {
            for (let y = 0; y < document.body.scrollHeight; y += 700) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); }
            window.scrollTo(0, 0);
        }""")
        self.page.wait_for_timeout(500)

    def scrape_current(self):
        data = self.page.evaluate(SCRAPE_JS, {"selectors": self.cfg.get("source_selectors", {})})
        data["price"] = parse_vnd(data.get("price_text"))
        return data

    @staticmethod
    def is_product(data):
        return bool(data.get("name") and data["found"].get("price") and
                    (data.get("sku") or data["found"].get("specs") or data["found"].get("features")))

    def scrape_url(self, url):
        self._open(url)
        return self.scrape_current()

    def expand(self, url):
        """Trả về danh sách URL sản phẩm từ 1 URL (trang sản phẩm hoặc trang danh mục)."""
        data = self.scrape_url(url)
        if self.is_product(data):
            return [url], {url: data}
        self.log(f"  → Đây là trang danh mục, đang lấy danh sách sản phẩm...")
        links, seen_pages, page_url = [], set(), url
        for _ in range(int(self.cfg.get("listing_max_pages", 10))):
            if page_url in seen_pages:
                break
            seen_pages.add(page_url)
            if page_url != url:
                self._open(page_url)
            res = self.page.evaluate(LINKS_JS, {"pattern": self.cfg.get("product_link_pattern", "")})
            links += [l for l in res["links"] if l not in links]
            self.log(f"  → Trang {len(seen_pages)}: tổng {len(links)} link")
            if not res.get("next"):
                break
            page_url = res["next"]
        return links, {}

    def download_images(self, urls, folder, max_images=15):
        from PIL import Image
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        strip = [s.lower() for s in self.cfg.get("image_url_strip_params", [])]
        files = []
        for i, u in enumerate(urls[:max_images], 1):
            for cand in dict.fromkeys([upgrade_image_url(u, strip), u]):
                try:
                    r = self.ctx.request.get(cand, timeout=30000, headers={"Referer": self.page.url})
                    if not r.ok:
                        continue
                    img = Image.open(io.BytesIO(r.body()))
                    img.load()
                    if img.mode not in ("RGB", "L"):
                        bg = Image.new("RGB", img.size, (255, 255, 255))
                        bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[-1])
                        img = bg
                    path = folder / f"{i:02d}.jpg"
                    img.convert("RGB").save(path, "JPEG", quality=92)
                    if min(img.size) < 300:
                        self.log(f"    ! Ảnh {i} nhỏ ({img.size[0]}x{img.size[1]}px)")
                    files.append(str(path))
                    break
                except Exception as e:  # ảnh lỗi thì bỏ qua, thử link khác
                    self.log(f"    ! Không tải được ảnh {cand}: {e}")
        return files


def pick_images(data, mode):
    v, g = data.get("variant_images", []), data.get("gallery_images", [])
    if mode == "gallery":
        imgs = g or v
    elif mode == "both":
        imgs = v + [x for x in g if x not in v]
    else:  # quycach
        imgs = v or g
    return list(dict.fromkeys(imgs))


def product_folder(output_dir, data):
    return Path(output_dir) / slugify(data.get("sku") or data.get("name"))


def weight_grams(data):
    """Lấy 'Trọng lượng (kg)' trong bảng thông số, đúng cột của mã sản phẩm."""
    spec = data.get("spec") or {}
    headers = spec.get("headers") or []
    sku = (data.get("sku") or "").lower()
    col = 0
    for i, h in enumerate(headers):
        if sku and sku in h.lower():
            col = i
            break
    else:
        if len(headers) > 1:
            return None
    for row in spec.get("rows", []):
        label = (row.get("label") or "").lower()
        if "trọng lượng" in label or "khối lượng" in label:
            vals = row.get("values") or []
            if col < len(vals):
                m = re.search(r"\d+(?:[.,]\d+)?", vals[col])
                if not m:
                    return None
                num = float(m.group(0).replace(",", "."))
                return round(num * 1000) if "kg" in label or "kg" in vals[col].lower() else round(num)
    return None
