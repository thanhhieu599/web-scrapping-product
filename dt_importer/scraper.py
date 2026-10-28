"""Cào dữ liệu sản phẩm từ trang nhà cung cấp.

Không phụ thuộc class CSS của trang nguồn: dùng "chữ neo" hiển thị trên trang
(QUY CÁCH, Đặc điểm, Thông Số, BAO GỒM TRONG SẢN PHẨM...) để định vị dữ liệu.
Nếu trang nguồn đổi giao diện, có thể chỉ định CSS selector trong config.json
(mục "source_selectors") để ghi đè.
"""
import hashlib
import io
import re
import time
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

  const visible = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const inPopup = e => !!e.closest('.modal, .modal-popup, [role=dialog], [class*=popup], [class*=store-locator], [class*=find-store], [class*=newsletter]');
  const firstOf = (sels) => { for (const s of sels) { const e = qsa(document, s).find(x => visible(x) && !inPopup(x)); if (e) return e; } return null; };

  // ---------- LOẠI TRANG: danh mục (nhiều sản phẩm) hay trang 1 sản phẩm ----------
  const pageType = () => {
    const body = document.body.className || '';
    const ldTypes = [];
    for (const sc of document.querySelectorAll('script[type="application/ld+json"]')) {
      try { const j = JSON.parse(sc.textContent); (Array.isArray(j) ? j : (j['@graph'] || [j]))
              .forEach(o => o && o['@type'] && ldTypes.push(String(o['@type']))); } catch (e) {}
    }
    const og = ((document.querySelector('meta[property="og:type"]') || {}).content || '').toLowerCase();
    const cards = qsa(document, '.product-item, li.product, .product-card, .product-grid-item, [class*="product-item"]')
                    .filter(e => !inChrome(e) && !e.closest('.related, .upsell, .crosssell, [class*=related], [class*=upsell]'));
    const prices = all.filter(e => PRICE_RE.test(norm(e.textContent)) && !inChrome(e) && visible(e)
                     && !e.closest('del, s, strike, [class*=old], .related, .upsell, [class*=related]'));
    const priceLeaves = prices.filter(e => ![...e.children].some(c => prices.includes(c))).length;
    return {
      product_view: /catalog-product-view|single-product|product-template/.test(body) || ldTypes.includes('Product') || og === 'product',
      listing: /catalog-category-view|catalogsearch-result|page-products|archive|product-list/.test(body)
               || cards.length >= 3 || priceLeaves >= 3 || ldTypes.includes('ItemList') || ldTypes.includes('CollectionPage'),
      cards: cards.length, price_count: priceLeaves,
    };
  };

  // ---------- GIÁ ----------
  // Ưu tiên cấu trúc Magento / schema.org, sau đó mới dò theo dạng "x.xxx.xxx ₫"
  let priceEl = qs(sel.price) || firstOf([
    '.product-info-main [data-price-type=finalPrice] .price', '.product-info-price .price',
    '.product-info-main .price-box .price', '[itemprop=offers] [itemprop=price]']);
  if (!priceEl) {
    const m = all.filter(e => PRICE_RE.test(norm(e.textContent)) && !inChrome(e) && !inPopup(e)
                     && visible(e) && !e.closest('del, s, strike, [class*=old], [class*=compare]'));
    const leaf = m.filter(e => ![...e.children].some(c => m.includes(c)));
    priceEl = leaf[0] || null;
  }
  const priceText = priceEl ? norm(priceEl.textContent) : '';

  // ---------- KHỐI THÔNG TIN (chứa tên + giá) ----------
  let info = qs('.product-info-main');
  if (!info && priceEl) {
    let n = priceEl.parentElement;
    while (n && n !== document.body) {
      if ([...n.querySelectorAll('h1, h2, h3')].some(h => visible(h) && !inPopup(h))) { info = n; break; }
      n = n.parentElement;
    }
  }

  // ---------- TÊN ----------
  // textContent (không phải innerText) để tránh chữ IN HOA do CSS của banner
  let nameEl = qs(sel.name) || firstOf([
    '.product-info-main .page-title .base', '.product-info-main .page-title', '[itemprop=name]',
    '.product-name h1', 'h1.page-title .base', '.page-title .base', 'h1']);
  if (!nameEl && info) nameEl = [...info.querySelectorAll('h1, h2, h3')].find(h => visible(h) && !inPopup(h));
  let name = nameEl ? norm(nameEl.textContent) : '';
  if (name && name === name.toUpperCase()) {
    // tên toàn chữ hoa → tìm bản viết thường cùng nội dung (tiêu đề khác trên trang / og:title)
    const alt = [...document.querySelectorAll('h1, h2, h3, [itemprop=name]')].map(h => norm(h.textContent))
      .concat([norm((document.querySelector('meta[property="og:title"]') || {}).content || '')])
      .find(t => t && t !== t.toUpperCase() && t.toLowerCase() === name.toLowerCase());
    if (alt) name = alt;
  }

  // ---------- MÃ SẢN PHẨM (chuỗi nhỏ ngay dưới tên) ----------
  // mã SP: 48-22-8450, ABC123, mã có khoảng trắng như Milwaukee "M18 FHX-0X0", hoặc dãy số 6–14 chữ số (vd Irwin 10505483)
  const SKU_RE = /^(?=.*\d)[A-Z0-9]{1,10}([-./][A-Z0-9]{1,12})+$|^(?=.*\d)(?=.*[A-Z])[A-Z0-9]{5,20}$|^(?=.*\d)(?=.*[A-Z])[A-Z0-9]{1,12}(?:[ \-./][A-Z0-9]{1,12}){1,4}$|^\d{6,14}$/i;
  const MONEY_RE = /^\d{1,3}([.,\s]\d{3})+$/;             // "2.940.000" (phần số của giá) – KHÔNG phải mã
  const cleanSku = t => norm(t).replace(/^(mã|mã sp|mã sản phẩm|sku|model)\s*[:：]?\s*/i, '');
  let sku = '';
  const skuEl = qs(sel.sku) || firstOf(['.product-info-main .product.attribute.sku .value',
    '.product.attribute.sku .value', '[itemprop=sku]', '.product-sku', '.sku .value']);
  if (skuEl) sku = cleanSku(skuEl.textContent || skuEl.getAttribute('content'));
  if (!sku) {
    // chuỗi dạng mã (vd 48-22-8450) nằm giữa tên và giá trong khối thông tin
    const root = info || document.body;
    const cands = [...root.querySelectorAll('*')].filter(e => e.children.length === 0 && visible(e) && !inPopup(e))
      .filter(e => { const t = cleanSku(e.textContent); return t.length <= 40 && SKU_RE.test(t) && !PRICE_RE.test(t)
        && !MONEY_RE.test(t) && !(priceEl && (priceEl.contains(e) || e.contains(priceEl))) && !e.closest('.price-box'); });
    const before = priceEl ? cands.filter(e => e.compareDocumentPosition(priceEl) & Node.DOCUMENT_POSITION_FOLLOWING) : cands;
    const pick = before[0] || cands[0];
    if (pick) sku = cleanSku(pick.textContent);
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
  // 1) Magento: danh sách ẢNH THẬT nằm trong cấu hình "mage/gallery/gallery" (ảnh <img> ban đầu chỉ là ảnh chờ)
  let galleryImages = [];
  const findGallery = (o, d) => { if (!o || typeof o !== 'object' || d > 8) return null;
    if (o['mage/gallery/gallery'] && Array.isArray(o['mage/gallery/gallery'].data)) return o['mage/gallery/gallery'].data;
    for (const k in o) { const r = findGallery(o[k], d + 1); if (r) return r; } return null; };
  for (const sc of document.querySelectorAll('script[type="text/x-magento-init"]')) {
    let data = null;
    try { data = findGallery(JSON.parse(sc.textContent), 0); } catch (e) {}
    if (data && data.length) {
      galleryImages = [...data].filter(x => !x.type || x.type === 'image')
        .sort((a, b) => (b.isMain ? 1 : 0) - (a.isMain ? 1 : 0) || (+a.position || 0) - (+b.position || 0))
        .map(x => abs(x.full || x.img || x.thumb)).filter(Boolean);
      break;
    }
  }
  // 2) Trang khác: ảnh quanh khối thông tin, LOẠI ảnh rác (nút chat nổi, logo, icon, ảnh chờ, ảnh quá nhỏ).
  //    Lưu ý: Magento đặt ẢNH CHÍNH THẬT trong <img class="gallery-placeholder__image"> – KHÔNG phải ảnh rác.
  const CLASS_JUNK = /chat|messenger|zalo|facebook|fb[-_]|hotline|logo|icon|heart|wish|badge|rating|star|spinner|loading/i;
  const SRC_JUNK = /\/placeholder\/|placeholder\.(png|jpe?g|gif|svg|webp)|loading|spinner|blank\.(gif|png)|pixel\.(gif|png)|sprite/i;
  const isFloating = el => { for (let n = el; n && n !== document.body; n = n.parentElement) {
      const pos = getComputedStyle(n).position; if (pos === 'fixed' || pos === 'sticky') return true; } return false; };
  const okImg = i => {
    const cls = ((i.className || '') + ' ' + (i.getAttribute('alt') || '') + ' ' + ((i.closest('[class]') || {}).className || ''))
                  .replace(/gallery-placeholder\w*/gi, ' ');
    const src = bestSrc(i) || '';
    if (CLASS_JUNK.test(cls) || SRC_JUNK.test(src) || isFloating(i) || i.closest('header, footer, nav, .modal, [role=dialog]')) return false;
    const w = Math.max(i.naturalWidth || 0, i.width || 0), h = Math.max(i.naturalHeight || 0, i.height || 0);
    return !(w && h && (w < 40 || h < 40));
  };
  if (!galleryImages.length) {
    const main = qsa(document, '.gallery-placeholder__image, [data-gallery-role=gallery-placeholder] img, .fotorama__stage img, .product.media img')
                   .filter(okImg).map(bestSrc).filter(Boolean);
    galleryImages = [...new Set(main)];
  }
  if (!galleryImages.length) {
    const box = qs('.product.media, .product-media, .product-gallery, .woocommerce-product-gallery, [class*=product-image], [class*=gallery]');
    if (box && !(info && box.contains(info))) galleryImages = [...box.querySelectorAll('img')].filter(okImg).map(bestSrc).filter(Boolean);
  }
  if (!galleryImages.length && info) {
    let n = info.parentElement;
    while (n && n !== document.body) {
      const imgs = [...n.querySelectorAll('img')].filter(i => !info.contains(i));
      if (imgs.length) { galleryImages = imgs.filter(okImg).map(bestSrc).filter(Boolean); break; }
      n = n.parentElement;
    }
  }
  // 3) Dự phòng: ảnh đại diện web khai báo cho Facebook/Google (og:image, itemprop=image) – trang SP nào cũng có
  if (!galleryImages.length) {
    const metas = [...document.querySelectorAll('meta[property="og:image"], meta[name="og:image"], meta[itemprop=image], link[rel=image_src]')]
      .map(m => abs(m.getAttribute('content') || m.getAttribute('href'))).filter(u => u && !SRC_JUNK.test(u));
    galleryImages = [...new Set(metas)];
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
  const featureImages = featRoot ? [...featRoot.querySelectorAll('img')].map(bestSrc).filter(Boolean) : [];

  // ---------- THÔNG SỐ ----------
  let specRoot = qs(sel.specs);
  if (!specRoot) {
    for (const lab of findLabels(['thông số', 'thông số kỹ thuật', 'thông số kĩ thuật'])) {
      specRoot = contentAfter(lab, s => s.querySelector('table, tr') || norm(s.textContent).length > 20);
      if (specRoot) break;
    }
  }
  const spec = { headers: [], rows: [], text: [], source: '', images: [] };

  // Lưới từ <table> thật
  const gridFromTables = (tables) => {
    const g = [];
    for (const tb of tables) for (const tr of tb.querySelectorAll('tr')) {
      const row = { t: [], im: [] };
      for (const c of [...tr.children].filter(c => /^T[DH]$/.test(c.tagName))) {
        row.t.push(norm(c.textContent));
        const img = c.querySelector('img');
        row.im.push(img ? bestSrc(img) : '');
        for (let k = 1; k < (c.colSpan || 1); k++) { row.t.push(''); row.im.push(''); }
      }
      g.push(row);
    }
    return g;
  };

  // Lưới dựng theo VỊ TRÍ HIỂN THỊ (trang xếp bảng bằng <div>): cùng hàng = cùng độ cao, cùng cột = cùng vị trí ngang
  const gridFromLayout = (root) => {
    const restore = [];
    for (let n = root; n && n !== document.body; n = n.parentElement) {     // mở accordion/tab đang ẩn
      const cs = getComputedStyle(n);
      if (cs.display === 'none') { restore.push([n, n.style.cssText]); n.style.display = 'block'; }
      if (cs.visibility === 'hidden') { restore.push([n, n.style.cssText]); n.style.visibility = 'visible'; }
      if (cs.maxHeight === '0px' || (cs.overflow === 'hidden' && n.offsetHeight === 0)) {
        restore.push([n, n.style.cssText]); n.style.maxHeight = 'none'; n.style.height = 'auto';
      }
    }
    // mỗi đoạn chữ = 1 mảnh, lấy toạ độ thật trên màn hình
    const pieces = [];
    const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    while (tw.nextNode()) {
      const tn = tw.currentNode, t = norm(tn.textContent);
      if (!t || !tn.parentElement || SKIP_TAGS.has(tn.parentElement.tagName)) continue;
      const r = document.createRange(); r.selectNodeContents(tn);
      const b = r.getBoundingClientRect();
      if (b.width < 1 || b.height < 1) continue;
      pieces.push({ t, el: tn.parentElement, l: b.left, r: b.right, top: b.top, bot: b.bottom });
    }
    // ảnh trong bảng (vd hàng ảnh sản phẩm phía trên các cột model)
    for (const img of root.querySelectorAll('img')) {
      let b = img.getBoundingClientRect();
      if (b.width < 2 || b.height < 2) { const p = img.parentElement; if (p) b = p.getBoundingClientRect(); }
      const u = bestSrc(img);
      if (!u || b.width < 2 || b.height < 2) continue;
      pieces.push({ t: '', img: u, el: img, l: b.left, r: b.right, top: b.top, bot: b.bottom });
    }
    // KHUNG Ô của mỗi mảnh: phần tử rộng nhất bao quanh nó mà KHÔNG chứa mảnh nào khác cùng hàng.
    // Dùng khung ô (thay vì vị trí chữ) để xác định cột → đúng cả khi chữ căn trái còn mã/ảnh căn giữa.
    const sameRow = (a, b) => a.top < b.bot - 1 && b.top < a.bot - 1;
    // e là 1 ô nếu bên cạnh nó (cùng hàng, khác vị trí ngang) có phần tử anh em – kể cả ô trống
    const hasSideSibling = (par, e) => {
      const b = e.getBoundingClientRect();
      return [...par.children].some(c => {
        if (c === e) return false;
        const r = c.getBoundingClientRect();
        return r.width > 0 && r.height > 0 && r.top < b.bottom - 1 && b.top < r.bottom - 1
               && (r.right <= b.left + 1 || r.left >= b.right - 1);
      });
    };
    for (const p of pieces) {
      let e = p.el;
      while (e && e !== root && e.parentElement) {
        const par = e.parentElement;
        if (pieces.some(q => q !== p && sameRow(p, q) && par.contains(q.el) && !e.contains(q.el))) break;
        if (hasSideSibling(par, e)) break;
        e = par;
      }
      const bb = (e || p.el).getBoundingClientRect();
      p.cl = Math.min(bb.left, p.l); p.cr = Math.max(bb.right, p.r);
    }
    restore.forEach(([n, css]) => { n.style.cssText = css; });
    if (pieces.filter(p => p.t).length < 4) return null;
    // ghép các mảnh liền nhau trên cùng dòng thành 1 ô (vd "Chiều dài" + "(mm)")
    pieces.sort((a, b) => a.top - b.top || a.l - b.l);
    const cells = [];
    for (const p of pieces) {
      const last = cells[cells.length - 1];
      if (last && p.t && last.t && Math.abs(last.top - p.top) < 4 && p.l - last.r < 8 && p.l >= last.l) {
        last.t += ' ' + p.t; last.r = Math.max(last.r, p.r); last.bot = Math.max(last.bot, p.bot);
        last.cl = Math.min(last.cl, p.cl); last.cr = Math.max(last.cr, p.cr);
      } else cells.push({ ...p });
    }
    // hàng: các ô có tâm dọc nằm trong cùng dải
    const rows = [];
    for (const c of [...cells].sort((a, b) => a.top - b.top)) {
      const mid = (c.top + c.bot) / 2, row = rows[rows.length - 1];
      if (row && mid < row.bot) { row.cells.push(c); row.bot = Math.max(row.bot, c.bot); }
      else rows.push({ top: c.top, bot: c.bot, cells: [c] });
    }
    // cột: gộp khoảng ngang của các KHUNG Ô (bỏ ô trải gần hết bề ngang như tiêu đề nhóm).
    // Không tách được ≥2 cột theo khung ô (trang không có ô rõ ràng) → dùng vị trí chữ như cũ.
    const width = root.getBoundingClientRect().width || 1000;
    const makeBands = (L, R, maxFrac) => {
      const iv = cells.filter(c => (c[R] - c[L]) < width * maxFrac).map(c => [c[L], c[R]]).sort((a, b) => a[0] - b[0]);
      const out = [];
      for (const [l, r] of iv) {
        const b = out[out.length - 1];
        if (b && l < b[1] - 1) b[1] = Math.max(b[1], r); else out.push([l, r]);
      }
      return out;
    };
    let L = 'cl', R = 'cr', wideFrac = 0.9;
    let bands = makeBands(L, R, wideFrac);
    if (bands.length < 2) { L = 'l'; R = 'r'; wideFrac = 0.45; bands = makeBands(L, R, wideFrac); }
    if (bands.length < 2) return null;
    const bandOf = c => {
      const mid = (c[L] + c[R]) / 2;
      let best = 0, d = Infinity;
      bands.forEach(([l, r], i) => { const dist = mid < l ? l - mid : mid > r ? mid - r : 0; if (dist < d) { d = dist; best = i; } });
      return best;
    };
    return rows.map(row => {
      const out = { t: Array(bands.length).fill(''), im: Array(bands.length).fill('') };
      const wide = row.cells.length === 1 && row.cells[0].t && (row.cells[0][R] - row.cells[0][L]) >= width * wideFrac;
      if (wide) { out.t[0] = row.cells[0].t; return out; }
      row.cells.sort((a, b) => a.l - b.l).forEach(c => {
        const i = bandOf(c);
        if (c.img) { if (!out.im[i]) out.im[i] = c.img; }
        else out.t[i] = out.t[i] ? out.t[i] + ' ' + c.t : c.t;
      });
      return out;
    });
  };

  if (specRoot) {
    const tables = specRoot.tagName === 'TABLE' ? [specRoot] : [...specRoot.querySelectorAll('table')];
    let grid = null;
    if (tables.length) { grid = gridFromTables(tables); spec.source = 'table'; }
    else { grid = gridFromLayout(specRoot); spec.source = grid ? 'layout' : 'text'; }
    if (grid) {
      let skipQty = false;
      for (const g of grid) {
        const cells = g.t;
        if (!cells.length || cells.every(c => !c)) {                         // hàng ảnh (giữ lại) / hàng trống
          if (g.im.some(Boolean) && !spec.images.length) spec.images = g.im.slice(1);
          continue;
        }
        const first = (cells[0] || '').toLowerCase();
        const isQty = c => /\(\d+\)\s*$/.test(c);
        if (first.startsWith('bao gồm')) {                                   // KHÔNG lấy khối "Bao gồm trong sản phẩm"
          const vals = cells.slice(1).filter(Boolean);
          if (!spec.headers.length && vals.length && !vals.every(isQty)) spec.headers = cells.slice(1).map(c => norm(c.replace(/\S+\s*\(\d+\)/g, '')) || c);
          skipQty = true;
          continue;
        }
        if (!cells[0] && cells.slice(1).some(Boolean) && cells.slice(1).filter(Boolean).every(isQty)) { skipQty = false; continue; } // dòng "48-22-xxxx (1)"
        skipQty = false;
        if (!cells[0] && !spec.headers.length && cells.length > 1) { spec.headers = cells.slice(1); continue; } // dòng mã model
        const filled = cells.filter(Boolean).length;
        if (filled === 1 && cells[0]) { spec.rows.push({ section: cells[0] }); continue; }
        spec.rows.push({ label: cells[0], values: cells.slice(1) });
      }
    } else {
      spec.text = (specRoot.innerText || specRoot.textContent).split(/\n+/).map(norm).filter(Boolean)
                   .filter(t => !/^bao gồm/i.test(t) && !/\(\d+\)\s*$/.test(t));
    }
  }

  return {
    url: location.href, name, sku, price_text: priceText,
    variant_images: [...new Set(variantImages)].filter(Boolean),
    gallery_images: [...new Set(galleryImages)].filter(Boolean),
    features, feature_images: [...new Set(featureImages)], spec,
    found: { price: !!priceEl, name: !!name, features: !!featRoot, specs: !!specRoot, spec_source: spec.source,
             ...pageType() }
  };
}
"""

SWATCH_JS = COMMON_JS + r"""
(cfg) => {
  // Các ô lựa chọn dưới chữ QUY CÁCH → đánh dấu data-dt-sw để bấm lần lượt
  const sel = cfg.selectors || {};
  document.querySelectorAll('[data-dt-sw]').forEach(e => e.removeAttribute('data-dt-sw'));
  const all = [...document.body.querySelectorAll('*')].filter(e => !SKIP_TAGS.has(e.tagName));
  let box = qs(sel.variant_images);
  if (!box) {
    const labs = all.filter(e => { const t = low(e.textContent).replace(/[:：]$/, '').trim();
      return t.length < 40 && ['quy cách', 'quy cach', 'phân loại', 'kiểu'].includes(t); });
    const lab = labs.filter(e => ![...e.children].some(c => labs.includes(c)))[0];
    if (!lab) return [];
    let node = lab;
    for (let lvl = 0; !box && lvl < 6 && node && node !== document.body; lvl++) {
      for (let sb = node.nextElementSibling; sb; sb = sb.nextElementSibling)
        if (sb.querySelector('img, [option-id], .swatch-option') || sb.tagName === 'IMG') { box = sb; break; }
      node = node.parentElement;
    }
  }
  if (!box) return [];
  let items = [...box.querySelectorAll('.swatch-option, [option-id], [role=option]')];
  if (!items.length) items = [...box.querySelectorAll('img')].map(i => i.closest('a, button, li, label, [onclick]') || i.parentElement || i);
  items = items.filter((e, i, a) => a.indexOf(e) === i && !items.some(o => o !== e && o.contains(e)));
  return items.map((e, i) => {
    e.setAttribute('data-dt-sw', String(i));
    const a = e.closest('a[href]');
    const href = a ? abs(a.getAttribute('href')) : null;
    const img = e.querySelector('img') || (e.tagName === 'IMG' ? e : null);
    const label = norm(e.getAttribute('option-label') || e.getAttribute('aria-label') || e.getAttribute('title')
                  || e.getAttribute('data-value') || (img && img.getAttribute('alt')) || e.textContent);
    return { i, label, href: href && !/^javascript:|#$/.test(href) ? href.split('#')[0] : null,
             option_id: e.getAttribute('option-id') || '', selected: /selected|active|checked/i.test(e.className) };
  });
}
"""

MAGENTO_JS = r"""
() => {
  // Magento: dữ liệu phiên bản (giá, ảnh) có sẵn trong jsonConfig của swatch-renderer / configurable
  const find = (o, d) => { if (!o || typeof o !== 'object' || d > 8) return null;
    if (o.jsonConfig && o.jsonConfig.attributes) return o.jsonConfig;
    if (o.spConfig && o.spConfig.attributes) return o.spConfig;
    for (const k in o) { const r = find(o[k], d + 1); if (r) return r; } return null; };
  let cfg = null;
  for (const sc of document.querySelectorAll('script[type="text/x-magento-init"]')) {
    try { cfg = find(JSON.parse(sc.textContent), 0); } catch (e) {}
    if (cfg) break;
  }
  if (!cfg) return null;
  const attrs = Object.values(cfg.attributes || {});
  if (!attrs.length) return null;
  const a = attrs[0];
  return (a.options || []).map(o => {
    const pid = (o.products || [])[0];
    const pr = pid && cfg.optionPrices && cfg.optionPrices[pid];
    const imgs = (pid && cfg.images && cfg.images[pid]) || [];
    const main = imgs.find(x => x.isMain) || imgs[0];
    const skus = cfg.skus || cfg.sku || cfg.productSkus || {};
    return { option_id: String(o.id), label: o.label, attribute: a.label,
             price: pr && pr.finalPrice ? pr.finalPrice.amount : null,
             image: main ? new URL(main.full || main.img, location.href).href : null, sku: (pid && skus[pid]) || null };
  });
}
"""

LINKS_JS = COMMON_JS + r"""
(cfg) => {
  const pat = cfg.pattern ? new RegExp(cfg.pattern, 'i') : null;
  const here = location.href.split('#')[0];
  const out = [];
  // Ưu tiên link trong THẺ SẢN PHẨM (Magento/WooCommerce/Haravan...) – chính xác hơn dò mọi link có ảnh
  const CARD_LINKS = 'a.product-item-link, a.product-item-photo, .product-item-name a, .product-item a.photo, '
                   + 'li.product a.woocommerce-LoopProduct-link, .product-card a, .product-grid-item a, .product-item a';
  if (!pat) {
    for (const a of qsa(document, CARD_LINKS)) {
      if (inChrome(a) || a.closest('.related, .upsell, .crosssell, [class*=related], [class*=upsell], .pages, .toolbar')) continue;
      const u = abs(a.getAttribute('href'));
      if (!u || !u.startsWith(location.origin) || u.split('#')[0] === here || /\.(jpe?g|png|webp|gif|pdf)(\?|$)/i.test(u)) continue;
      if (/[?&](p|page)=\d+|\/page\/\d+|add-to-cart|wishlist|compare/i.test(u)) continue;
      out.push(u.split('#')[0]);
    }
  }
  for (const a of (out.length ? [] : document.querySelectorAll('a[href]'))) {
    const u = abs(a.getAttribute('href'));
    if (!u || !u.startsWith(location.origin) || u.split('#')[0] === here) continue;
    if (/\.(jpe?g|png|webp|gif|pdf)(\?|$)/i.test(u)) continue;
    if (pat) { if (!pat.test(u)) continue; }
    else if (!a.querySelector('img') || inChrome(a)) continue;   // mặc định: link có ảnh, ngoài menu
    out.push(u.split('#')[0]);
  }
  // Trang kế tiếp: <link rel=next> (Magento để trong <head>), a[rel=next], nút "Tiếp/›/Next" trong khối phân trang
  let next = document.querySelector('link[rel=next], a[rel=next]');
  if (!next) next = document.querySelector('.pages a.action.next, .pages-item-next a, a.next.page-numbers, li.next a, .pagination .next a');
  if (!next) next = [...document.querySelectorAll('.pagination a, .pages a, [class*=paging] a, [class*=pagination] a, [class*=pager] a')]
      .find(a => /^(›|»|>|sau|next|tiếp|trang tiếp|trang sau|tiếp theo)$/i.test(norm(a.textContent))
                 || /(^|\s)next(\s|$)/i.test(a.className) || /next/i.test(a.getAttribute('aria-label') || ''));
  const nh = next ? abs(next.getAttribute('href')) : null;
  return { links: [...new Set(out)], next: nh && nh.split('#')[0] !== here ? nh : null };
}
"""


def code_from_url(url):
    """'.../48-22-8425-hero01.png' -> '48-22-8425' (dùng khi ô quy cách không có chữ)."""
    name = (url or "").split("?")[0].rsplit("/", 1)[-1]
    m = re.search(r"\d{2,}-\d{2,}-\d{3,}[A-Z]?|[A-Z]{1,4}\d{3,}[A-Z0-9]*", name, re.I)
    return m.group(0).upper() if m else ""


def upgrade_image_url(url, strip_params):
    """Bỏ tham số thu nhỏ ảnh (?width=..) để lấy ảnh gốc."""
    url = re.sub(r"/media/catalog/product/cache/[0-9a-f]{32}/", "/media/catalog/product/", url)
    try:
        p = urlparse(url)
        q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if k.lower() not in strip_params]
        return urlunparse(p._replace(query=urlencode(q)))
    except ValueError:
        return url


class Scraper:
    def __init__(self, browser, cfg, log=print):
        from .sites import load_sites
        self.base_cfg = cfg
        self.cfg = cfg
        self.log = log
        self.sites = load_sites(cfg.get("sites_file"))
        self.profile = {"name": "web", "platform": "auto", "content": "auto"}
        self.adapter = None
        # Dùng đúng User-Agent của trình duyệt, chỉ bỏ chữ "Headless" (một số web chặn bot theo chữ này)
        probe = browser.new_page()
        ua = probe.evaluate("navigator.userAgent").replace("HeadlessChrome", "Chrome")
        probe.close()
        self.ctx = browser.new_context(viewport={"width": 1366, "height": 900}, locale="vi-VN", user_agent=ua)
        self.page = self.ctx.new_page()
        self.img_page = None
        self.last_fetch_url = None
        self.last_index = []

    def close(self):
        self.ctx.close()

    def _open(self, url):
        goto(self.page, url, self.log)
        try:
            self.page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        # cuộn để ảnh lazy-load hiện ra (tối đa 40 lần, tránh trang "cuộn vô hạn")
        try:
            self.page.evaluate("""async () => {
                for (let y = 0, k = 0; k < 40 && y < document.body.scrollHeight; y += 700, k++) {
                    window.scrollTo(0, y); await new Promise(r => setTimeout(r, 120)); }
                window.scrollTo(0, 0);
            }""")
        except Exception:      # trang tự chuyển hướng trong lúc cuộn → đợi trang mới ổn định
            try:
                self.page.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
        self.page.wait_for_timeout(500)

    def use_site(self, url):
        """Chọn hồ sơ nhà cung cấp (sites.json) theo tên miền của link → cấu hình + bộ đọc tương ứng."""
        from .sites import merged_cfg, profile_for
        prof = profile_for(url, self.sites)
        if prof.get("_domain") != self.profile.get("_domain"):
            self.profile = prof
            self.cfg = merged_cfg(self.base_cfg, prof)
            self.adapter = None
        return self.profile

    def scrape_current(self):
        from .sites import adapter_for
        data = self.page.evaluate(SCRAPE_JS, {"selectors": self.cfg.get("source_selectors", {})})
        data["price"] = parse_vnd(data.get("price_text"))
        self.adapter = adapter_for(self.page, self.profile)          # bộ đọc theo nền tảng của web
        data = self.adapter.enrich(self.page, data)
        data["platform"] = self.adapter.platform
        data["url"] = self.page.url
        return data

    @staticmethod
    def is_product(data):
        """Trang sản phẩm: có tên và (có giá + mã/thông số/đặc điểm) – hoặc sản phẩm 'Liên hệ'
        (không có giá) nhưng có mã SP và có Đặc điểm/Thông số."""
        f = data.get("found", {})
        detail = f.get("specs") or f.get("features")
        if not data.get("name"):
            return False
        if f.get("product_view"):                       # trang khai báo rõ là trang sản phẩm
            return bool(f.get("price") or data.get("sku") or detail)
        if detail:                                      # có Đặc điểm / Thông số → trang chi tiết
            return bool(f.get("price") or data.get("sku"))
        if f.get("listing"):                            # nhiều thẻ SP / nhiều giá → trang danh mục
            return False
        return bool(f.get("price") and data.get("sku"))

    def _check_variants(self, variants, base):
        """Chuẩn hoá danh sách phiên bản: giá là số nguyên; mỗi phiên bản phải có mã riêng, không trùng."""
        if len(variants or []) < 2:
            return []
        for v in variants:
            v["value"] = (v.get("value") or v.get("sku") or v.get("label") or "").strip()
            v["price"] = parse_vnd(v["price"]) if v.get("price") not in (None, "") else base.get("price")
        vals = [v["value"] for v in variants]
        if not all(vals) or len(set(vals)) != len(vals):
            self.log(f"    ! Không xác định được mã riêng cho từng phiên bản ({vals}) → bỏ qua phần phiên bản")
            return []
        return variants

    def scrape_variants(self, base_url, base):
        """Đọc từng phiên bản dưới QUY CÁCH: nhãn, mã SP, giá, ảnh. Trả [] nếu không có."""
        sel = {"selectors": self.cfg.get("source_selectors", {})}
        direct = self.adapter.variants(self, base_url, base) if self.adapter else None
        if direct is not None:                       # nền tảng có sẵn dữ liệu phiên bản (vd WooCommerce)
            return self._check_variants(direct, base)
        sw = self.page.evaluate(SWATCH_JS, sel)
        if len(sw) < 2:                              # không có ô Quy cách để bấm → bộ đọc nền tảng thử cách khác
            return self._check_variants(self.adapter.variants_fallback(self, base) if self.adapter else [], base)
        mg = None
        try:
            mg = self.page.evaluate(MAGENTO_JS)
        except Exception:
            pass
        variants, changed = [], False
        for k in range(len(sw)):
            info = sw[k]
            v = {"label": info["label"], "sku": "", "price": None, "image": None}
            try:
                here = self.page.url.split("#")[0]
                if info.get("href") and info["href"] != here and info["href"] != base_url:
                    goto(self.page, info["href"], self.log)          # ô quy cách là link sang trang khác
                    self.page.wait_for_timeout(800)
                    d = self.scrape_current()
                    goto(self.page, base_url, self.log)
                    self.page.wait_for_timeout(500)
                else:
                    self.page.locator(f'[data-dt-sw="{k}"]').first.click(timeout=5000)
                    self.page.wait_for_timeout(1200)
                    d = self.scrape_current() if (info.get("href") is None or info["href"] != here) else base
                    changed = True
                v["sku"], v["price"] = d.get("sku") or "", d.get("price")
            except Exception as e:
                self.log(f"    ! Không đọc được phiên bản {k + 1}: {str(e).splitlines()[0][:100]}")
            sw = self.page.evaluate(SWATCH_JS, sel) or sw              # đánh dấu lại sau khi trang đổi
            variants.append(v)
        if changed:                                                     # trả trang về trạng thái ban đầu
            goto(self.page, base_url, self.log)
        # ghép dữ liệu Magento (giá, ảnh gốc, nhãn) theo option-id hoặc thứ tự
        if mg:
            by_id = {m["option_id"]: m for m in mg}
            for i, v in enumerate(variants):
                m = by_id.get(sw[i]["option_id"] if i < len(sw) else "") or (mg[i] if len(mg) == len(variants) else None)
                if not m:
                    continue
                v["label"] = v["label"] or m["label"]
                v["price"] = m["price"] if m["price"] else v["price"]
                v["image"] = m["image"] or v["image"]
                v["sku"] = m["sku"] or v["sku"]
        imgs = base.get("variant_images") or []
        for i, v in enumerate(variants):
            if not v["image"] and i < len(imgs):
                v["image"] = imgs[i]
        # mã SP mỗi phiên bản phải khác nhau; nếu trang không đổi mã khi bấm → dùng nhãn của ô
        counts = {}
        for v in variants:
            counts[v["sku"]] = counts.get(v["sku"], 0) + 1
        for v in variants:
            if not v["sku"] or counts[v["sku"]] > 1:
                v["sku"] = v["label"] or code_from_url(v["image"]) or v["sku"]
        for v in variants:
            v["value"] = (v["sku"] or v["label"] or "").strip()
            v["price"] = parse_vnd(v["price"]) if v["price"] not in (None, "") else base.get("price")
        # (4) giá trị rỗng / trùng → không tạo phiên bản (tránh thuộc tính sai trên Sapo)
        vals = [v["value"] for v in variants]
        if not all(vals) or len(set(vals)) != len(vals):
            self.log(f"    ! Không xác định được mã riêng cho từng phiên bản ({vals}) → bỏ qua phần phiên bản")
            return []
        return variants

    def scrape_url(self, url):
        self.use_site(url)
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

    def _fetch_bytes(self, url, tries=3):
        """Tải 1 file qua CHÍNH trình duyệt (cùng đường mạng, cookie, chứng chỉ với trang) – có thử lại."""
        last = None
        for k in range(tries):
            try:
                if self.img_page is None:
                    self.img_page = self.ctx.new_page()
                resp = self.img_page.goto(url, wait_until="load", timeout=45000)
                if resp and resp.ok:
                    self.last_fetch_url = resp.url
                    return resp.body()
                last = f"HTTP {resp.status if resp else '?'}"
                if resp and resp.status in (403, 404, 410):
                    break
            except Exception as e:
                last = str(e).splitlines()[0]
                self.img_page = None if "closed" in last.lower() else self.img_page
            time.sleep(1.5 * (k + 1))
        # phương án phụ: kênh request riêng của Playwright
        try:
            r = self.ctx.request.get(url, timeout=30000, headers={"Referer": self.page.url})
            if r.ok:
                self.last_fetch_url = r.url
                return r.body()
            last = f"HTTP {r.status}"
        except Exception as e:
            last = str(e).splitlines()[0]
        raise RuntimeError(last)

    def download_images(self, urls, folder, max_images=15, alternates=None, keep_small="if_none"):
        """Tải ảnh về (JPG nền trắng), MỖI HÌNH CHỈ 1 LẦN.
        - Mỗi ảnh thử lần lượt: ảnh gốc → ảnh CÙNG TÊN cỡ lớn trong dữ liệu trang (gallery...) → link ban đầu.
        - Ảnh nhỏ (< 100px, vd ảnh thu nhỏ ô quy cách): keep_small="always" → vẫn dùng (ảnh phiên bản);
          "if_none" → chỉ dùng khi không có ảnh lớn nào.
        - Hình trùng (cùng hình dù khác link/kích thước) chỉ giữ 1; self.last_index[i] = vị trí ảnh của urls[i]
          trong danh sách trả về (None nếu không có) – dùng để gán ảnh cho từng phiên bản."""
        from PIL import Image
        folder = Path(folder)
        folder.mkdir(parents=True, exist_ok=True)
        strip = [s.lower() for s in self.cfg.get("image_url_strip_params", [])]
        max_side = int(self.cfg.get("image_max_side", 2000))
        base = lambda u: (u or "").split("?")[0].split("#")[0].rsplit("/", 1)[-1].lower()
        alts = {}
        for a in alternates or []:
            if a:
                alts.setdefault(base(a), [])
                if a not in alts[base(a)]:
                    alts[base(a)].append(a)
        files, sigs, digests = [], [], set()
        index = [None] * len(urls)
        pending_small = []                                   # (vị trí url, ảnh) – ảnh nhỏ chờ quyết định

        def keep(pos, img, digest):
            sig = _image_signature(img)
            for k, other in enumerate(sigs):                 # cùng hình (khác link/kích thước) → dùng lại ảnh đã có
                if _same_image(sig, other):
                    index[pos] = k
                    return False
            path = folder / f"{len(files) + 1:02d}.jpg"
            self._save_jpg(img, path, max_side)
            files.append(str(path))
            sigs.append(sig)
            digests.add(digest)
            index[pos] = len(files) - 1
            return True

        for pos, u in enumerate(urls[:max_images]):
            if not u:
                continue
            errs, best_small, got = [], None, False
            for cand in dict.fromkeys([upgrade_image_url(u, strip)] + alts.get(base(u), []) + [u]):
                try:
                    self.last_fetch_url = cand
                    raw = self._fetch_bytes(cand)
                    if "placeholder" in (self.last_fetch_url or "").lower():
                        raise ValueError("web trả về ảnh chờ (placeholder) thay vì ảnh thật")
                    digest = hashlib.md5(raw).hexdigest()
                    img = Image.open(io.BytesIO(raw))
                    img.load()
                    lo, hi = img.convert("L").getextrema()
                    if hi - lo < 8:
                        raise ValueError("ảnh trống một màu")
                    if min(img.size) < 100:
                        if min(img.size) >= 40 and (not best_small or img.size[0] * img.size[1] > best_small[0].size[0] * best_small[0].size[1]):
                            best_small = (img, digest)
                        raise ValueError(f"ảnh nhỏ {img.size[0]}x{img.size[1]}px")
                    if keep(pos, img, digest) and min(img.size) < 300:
                        self.log(f"    ! Ảnh {pos + 1} nhỏ ({img.size[0]}x{img.size[1]}px)")
                    got = True
                    break
                except Exception as e:  # thử link khác
                    errs.append(str(e).splitlines()[0][:100])
            if got:
                continue
            if best_small:
                if keep_small == "always":
                    keep(pos, *best_small)
                    self.log(f"    ! Ảnh {pos + 1}: chỉ có ảnh nhỏ {best_small[0].size[0]}x{best_small[0].size[1]}px – vẫn dùng")
                else:
                    pending_small.append((pos, best_small))
            else:
                self.log(f"    ! Không tải được ảnh {pos + 1}: {u} ({'; '.join(errs)})")
        if not files and pending_small:                      # không có ảnh lớn nào → dùng ảnh nhỏ còn hơn bỏ trống
            for pos, (img, digest) in pending_small:
                keep(pos, img, digest)
            self.log(f"    ! Chỉ có ảnh nhỏ cho sản phẩm này – vẫn dùng {len(files)} ảnh")
        dup = sum(1 for i, k in enumerate(index) if k is not None and index.index(k) != i)
        if dup:
            self.log(f"    · Bỏ {dup} ảnh trùng (cùng hình) – mỗi hình chỉ tải 1 lần")
        self.last_index = index
        return files

    @staticmethod
    def _save_jpg(img, path, max_side):
        from PIL import Image
        if img.mode not in ("RGB", "L"):
            rgba = img.convert("RGBA")
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(rgba, mask=rgba.split()[-1])
            img = bg
        if max(img.size) > max_side:
            img = img.copy()
            img.thumbnail((max_side, max_side))
        img.convert("RGB").save(path, "JPEG", quality=92)

    def save_source_html(self, path):
        try:
            Path(path).write_text(self.page.content(), encoding="utf-8")
        except Exception:
            pass


def pick_images(data, mode):
    v, g = data.get("variant_images", []), data.get("gallery_images", [])
    if mode == "gallery":
        imgs = g or v
    elif mode == "both":
        imgs = v + [x for x in g if x not in v]
    else:  # quycach (chỉ 1 ô quy cách = SP 1 model → dùng ảnh gallery thật nếu có)
        imgs = v if len(v) >= 2 or not g else g
    return list(dict.fromkeys(imgs))


def _image_signature(img):
    """Dấu vân tay hình ảnh: thu nhỏ về 32x32 màu (nền trắng) → so sánh được dù khác kích thước/định dạng."""
    from PIL import Image
    im = img
    if im.mode not in ("RGB", "L"):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.split()[-1])
        im = bg
    w, h = im.size
    return (round(w / h, 2), im.convert("RGB").resize((32, 32)).tobytes())


def _same_image(a, b, tol=1.5):
    """Cùng hình nếu tỉ lệ khung gần bằng và chênh lệch màu trung bình rất nhỏ."""
    if abs(a[0] - b[0]) > 0.05:
        return False
    da, db = a[1], b[1]
    return sum(abs(x - y) for x, y in zip(da, db)) / len(da) < tol


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
