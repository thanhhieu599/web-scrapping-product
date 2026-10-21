"""Tự điền form "Thêm mới sản phẩm" trong Sapo Admin bằng trình duyệt thật.

- Dùng hồ sơ trình duyệt riêng (browser_profile/) → chỉ cần đăng nhập Sapo 1 lần.
- Định vị ô nhập theo placeholder / nhãn tiếng Việt hiển thị trên form.
"""
import re
import time
from pathlib import Path

from .browser import goto, launch as launch_browser

MARK_INPUT_JS = r"""
([labels, mark]) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const want = labels.map(norm);
  const own = e => norm([...e.childNodes].filter(n => n.nodeType === 3).map(n => n.textContent).join(' '))
                   || (e.children.length === 0 ? norm(e.textContent) : '');
  const cands = [...document.querySelectorAll('label, span, div, p, h3, h4, h5, strong, b, legend')]
     .filter(e => vis(e) && want.includes(own(e).replace(/[:*]$/, '').trim()));
  for (const lab of cands) {
    let inp = null;
    if (lab.tagName === 'LABEL' && lab.htmlFor) inp = document.getElementById(lab.htmlFor);
    let node = lab;
    for (let k = 0; !inp && k < 5 && node; k++) {
      inp = [...node.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), textarea')]
              .find(i => vis(i) && (lab.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING));
      node = node.parentElement;
    }
    if (inp) { document.querySelectorAll(`[data-dt-mark="${mark}"]`).forEach(x => x.removeAttribute('data-dt-mark'));
               inp.setAttribute('data-dt-mark', mark); return true; }
  }
  return false;
}
"""

CHECKBOX_JS = r"""
([text, mark]) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const t = norm(text);
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const cands = [...document.querySelectorAll('label, span, div, p')]
     .filter(e => norm(e.textContent) === t && vis(e));
  const leaf = cands.filter(e => ![...e.children].some(c => cands.includes(c)));
  for (const lab of leaf) {
    let cb = (lab.tagName === 'LABEL' && lab.control) || lab.querySelector('input[type=checkbox]');
    let node = lab;
    for (let k = 0; !cb && k < 4 && node; k++) { node = node.parentElement; cb = node && node.querySelector('input[type=checkbox]'); }
    if (!cb) continue;
    cb.setAttribute('data-dt-mark', mark);
    lab.setAttribute('data-dt-mark', mark + '-label');
    return { found: true, checked: cb.checked };
  }
  return { found: false, checked: false };
}
"""

EDITOR_JS = r"""
(html) => {
  try {
    if (window.FroalaEditor && FroalaEditor.INSTANCES && FroalaEditor.INSTANCES.length) {
      const ed = FroalaEditor.INSTANCES[0];
      ed.html.set(html); ed.events.trigger('contentChanged'); if (ed.undo) ed.undo.saveStep();
      return 'froala';
    }
  } catch (e) {}
  try {
    if (window.jQuery && jQuery.fn.froalaEditor) {
      const el = jQuery('*').filter(function () { return jQuery(this).data('froala.editor'); }).first();
      if (el.length) { el.froalaEditor('html.set', html); el.froalaEditor('events.trigger', 'contentChanged'); return 'froala-v2'; }
    }
  } catch (e) {}
  try {
    if (window.CKEDITOR && CKEDITOR.instances) {
      for (const k in CKEDITOR.instances) { CKEDITOR.instances[k].setData(html); CKEDITOR.instances[k].updateElement(); return 'ckeditor'; }
    }
  } catch (e) {}
  try {
    if (window.tinymce && tinymce.activeEditor) {
      tinymce.activeEditor.setContent(html); tinymce.activeEditor.save(); tinymce.activeEditor.fire('change');
      return 'tinymce';
    }
  } catch (e) {}
  const fire = el => ['input', 'keyup', 'change', 'blur'].forEach(ev => el.dispatchEvent(new Event(ev, { bubbles: true })));
  const ce = [...document.querySelectorAll('[contenteditable=true], .fr-element')]
      .filter(e => e.offsetHeight > 40)[0];
  if (ce) {
    ce.focus(); ce.innerHTML = html; fire(ce);
    const box = ce.closest('.fr-box, .editor, form') || document;
    const ta = box.querySelector('textarea');
    if (ta) { ta.value = html; fire(ta); }
    return 'contenteditable';
  }
  for (const f of document.querySelectorAll('iframe')) {
    try {
      const b = f.contentDocument && f.contentDocument.body;
      if (b && (b.isContentEditable || f.contentDocument.designMode === 'on')) { b.innerHTML = html; fire(b); return 'iframe'; }
    } catch (e) {}
  }
  return 'none';
}
"""

MARK_FILE_INPUT_JS = r"""
(mark) => {
  const inputs = [...document.querySelectorAll('input[type=file]')]
    .filter(i => !i.closest('.fr-popup, .fr-box, .fr-wrapper, .cke, .tox'));
  const score = i => {
    let n = i, k = 0;
    while (n && k < 10) { if (/ảnh sản phẩm/i.test(n.textContent || '')) return 10 - k; n = n.parentElement; k++; }
    return 0;
  };
  inputs.sort((a, b) => score(b) - score(a));
  const i = inputs.find(x => !x.accept || /image/i.test(x.accept));
  if (!i) return null;
  i.setAttribute('data-dt-mark', mark);
  return { multiple: i.multiple };
}
"""

CLICK_OPTION_JS = r"""
([value, allowAdd]) => {
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const v = norm(value);
  const vis = e => !!(e.offsetWidth || e.offsetHeight) && getComputedStyle(e).visibility !== 'hidden';
  const opts = [...document.querySelectorAll('li, a, [role=option], .dropdown-item, .item, label, span, div')]
     .filter(e => vis(e) && e.tagName !== 'INPUT' && e.children.length <= 3);
  let hit = opts.filter(e => norm(e.textContent) === v);
  if (!hit.length && allowAdd) hit = opts.filter(e => { const t = norm(e.textContent); return t.startsWith('thêm') && t.includes(v) && t.length < v.length + 30; });
  hit = hit.filter(e => !hit.some(o => o !== e && e.contains(o)));   // phần tử sâu nhất
  if (!hit.length) return false;
  hit[hit.length - 1].click();
  return true;
}
"""


class SapoError(Exception):
    pass


class SapoUploader:
    NAME_PH = ["Nhập tên sản phẩm"]
    TYPE_PH = ["Nhập loại sản phẩm"]
    VENDOR_PH = ["Nhập nhà cung cấp"]
    COLLECTION_PH = ["Tìm kiếm danh mục"]
    TAG_PH = ["Nhập tag cho sản phẩm"]

    def __init__(self, pw, cfg, log=print, wait_user=None):
        self.cfg, self.log = cfg, log
        self.wait_user = wait_user or (lambda msg: input(msg + " [Enter để tiếp tục] "))
        Path(cfg["profile_dir"]).mkdir(parents=True, exist_ok=True)
        self.ctx = launch_browser(pw, cfg, log, headless=bool(cfg.get("sapo_headless", False)),
                                  profile_dir=cfg["profile_dir"], viewport={"width": 1400, "height": 900},
                                  locale="vi-VN")
        self.page = self.ctx.pages[0] if self.ctx.pages else self.ctx.new_page()
        self.page.set_default_timeout(20000)
        self.create_url = cfg["sapo_admin_url"].rstrip("/") + "/products/create"

    def close(self):
        try:
            self.ctx.close()
        except Exception:
            pass

    # ---------------- tiện ích định vị ----------------
    def _by_placeholder(self, placeholders):
        for ph in placeholders:
            loc = self.page.locator(f'input[placeholder="{ph}"]:visible, textarea[placeholder="{ph}"]:visible')
            if loc.count():
                return loc.first
        return None

    def _by_label(self, labels, mark):
        if self.page.evaluate(MARK_INPUT_JS, [labels, mark]):
            return self.page.locator(f'[data-dt-mark="{mark}"]').first
        return None

    def _type(self, loc, value):
        loc.scroll_into_view_if_needed()
        loc.click()
        loc.press("Control+A")
        loc.press("Backspace")
        loc.press_sequentially(str(value), delay=15)

    def _wait_form(self, timeout=15000):
        try:
            self.page.locator(f'input[placeholder="{self.NAME_PH[0]}"]').first.wait_for(state="visible", timeout=timeout)
            return True
        except Exception:
            return False

    # ---------------- đăng nhập ----------------
    def ensure_login(self):
        goto(self.page, self.create_url, self.log)
        if self._wait_form():
            return
        self.log("⚠ Chưa đăng nhập Sapo. Hãy đăng nhập trong cửa sổ trình duyệt vừa mở (chỉ cần làm 1 lần).")
        deadline = time.time() + 600
        while time.time() < deadline:
            self.page.wait_for_timeout(3000)
            url = self.page.url
            if "/admin" in url and "login" not in url.lower():
                if "/products/create" not in url:
                    goto(self.page, self.create_url, self.log)
                if self._wait_form(8000):
                    self.log("✓ Đã đăng nhập Sapo.")
                    return
        raise SapoError("Hết thời gian chờ đăng nhập Sapo (10 phút).")

    # ---------------- các bước điền form ----------------
    def _set_content(self, html):
        how = self.page.evaluate(EDITOR_JS, html)
        if how == "none":
            # Phương án cuối: bật chế độ "Mã HTML" và dán mã
            btn = self.page.locator('button:has-text("Mã HTML"), [title="Mã HTML"], [data-cmd="html"]').first
            if btn.count():
                btn.click()
                ta = self.page.locator("textarea:visible").first
                ta.fill(html)
                btn.click()
                how = "code-view"
        self.log(f"    · Nội dung: đã điền ({how})")
        if how == "none":
            self.log("    ! Không tìm thấy trình soạn thảo – cần dán nội dung thủ công.")

    def _upload_images(self, files):
        if not files:
            self.log("    ! Không có ảnh để tải lên")
            return
        info = self.page.evaluate(MARK_FILE_INPUT_JS, "img-input")
        if info:
            inp = self.page.locator('[data-dt-mark="img-input"]')
            if info.get("multiple"):
                inp.set_input_files(files)
            else:
                for f in files:
                    self.page.evaluate(MARK_FILE_INPUT_JS, "img-input")
                    self.page.locator('[data-dt-mark="img-input"]').set_input_files(f)
                    self.page.wait_for_timeout(1500)
        else:
            link = self.page.get_by_text("Thêm ảnh sản phẩm", exact=False).first
            with self.page.expect_file_chooser(timeout=8000) as fc:
                link.click()
            fc.value.set_files(files)
        # chờ ảnh tải lên xong
        self.page.wait_for_timeout(min(2000 + 1200 * len(files), 20000))
        try:
            self.page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        self.log(f"    · Ảnh: đã tải lên {len(files)} ảnh")

    def _ensure_checkbox(self, text, want=True):
        mark = "cb-" + re.sub(r"\W+", "", text.lower())[:20]
        st = self.page.evaluate(CHECKBOX_JS, [text, mark])
        if not st["found"]:
            self.log(f"    ! Không tìm thấy ô tick '{text}'")
            return
        if st["checked"] != want:
            try:
                self.page.locator(f'[data-dt-mark="{mark}-label"]').click()
            except Exception:
                self.page.locator(f'[data-dt-mark="{mark}"]').click(force=True)
            st = self.page.evaluate(CHECKBOX_JS, [text, mark])
            if st["checked"] != want:
                self.page.locator(f'[data-dt-mark="{mark}"]').click(force=True)
        self.log(f"    · Tick '{text}': {'✓' if want else '✗'}")

    def _fill_combo(self, placeholders, labels, value, what):
        if not value:
            return
        loc = self._by_placeholder(placeholders) or self._by_label(labels, "combo-" + what)
        if not loc:
            self.log(f"    ! Không tìm thấy ô {what}")
            return
        self._type(loc, value)
        self.page.wait_for_timeout(1000)
        self.page.evaluate(CLICK_OPTION_JS, [value, True])
        self.page.wait_for_timeout(300)
        # đảm bảo giá trị vẫn còn trong ô (một số combobox xoá khi blur)
        if loc.input_value().strip() == "":
            self._type(loc, value)
        loc.press("Tab")
        self.log(f"    · {what}: {value}")

    def _pick_collections(self, names):
        for name in names:
            loc = self._by_placeholder(self.COLLECTION_PH)
            if not loc:
                self.log("    ! Không tìm thấy ô Danh mục")
                return
            self._type(loc, name)
            self.page.wait_for_timeout(1500)
            ok = self.page.evaluate(CLICK_OPTION_JS, [name, False])
            self.log(f"    · Danh mục '{name}': {'✓' if ok else '! không có trong Sapo – hãy tạo danh mục trước'}")
            self.page.keyboard.press("Escape")

    def _add_tags(self, tags):
        loc = self._by_placeholder(self.TAG_PH)
        if not loc or not tags:
            return
        for t in tags:
            self._type(loc, t)
            loc.press("Enter")
            self.page.wait_for_timeout(200)
        self.log(f"    · Tags: {', '.join(tags)}")

    def _save(self):
        btn = self.page.get_by_role("button", name=re.compile(r"^\s*Lưu( sản phẩm)?\s*$"))
        if not btn.count():
            btn = self.page.locator('button:has-text("Lưu"), a.btn:has-text("Lưu")')
        visible = [btn.nth(i) for i in range(btn.count()) if btn.nth(i).is_visible()]
        if not visible:
            raise SapoError("Không thấy nút Lưu")
        visible[-1].click()
        try:
            self.page.wait_for_url(lambda u: "/products/create" not in u, timeout=60000)
        except Exception:
            raise SapoError("Bấm Lưu nhưng Sapo không chuyển trang – có thể thiếu dữ liệu bắt buộc, xem ảnh chụp lỗi.")
        return self.page.url

    # ---------------- tạo 1 sản phẩm ----------------
    def create_product(self, p, opts):
        """p: dict gồm name, sku, price, content_html, image_files, weight_g."""
        goto(self.page, self.create_url, self.log)
        if not self._wait_form(30000):
            self.ensure_login()

        name_input = self._by_placeholder(self.NAME_PH) or self._by_label(["Tên sản phẩm"], "name")
        self._type(name_input, p["name"])
        self.log(f"    · Tên: {p['name']}")

        self._set_content(p["content_html"])
        self._upload_images(p.get("image_files") or [])

        if p.get("price"):
            price = self._by_label(["Giá"], "price")
            if price:
                self._type(price, p["price"])
                self.log(f"    · Giá: {p['price']:,}".replace(",", "."))
            else:
                self.log("    ! Không tìm thấy ô Giá")
        self._ensure_checkbox("Giá đã bao gồm VAT", True)

        if p.get("sku"):
            sku = self._by_label(["Mã sản phẩm / SKU", "Mã sản phẩm/SKU", "Mã sản phẩm", "SKU"], "sku")
            if sku:
                self._type(sku, p["sku"])
                self.log(f"    · Mã SP/SKU: {p['sku']}")
            else:
                self.log("    ! Không tìm thấy ô Mã sản phẩm / SKU")

        self._ensure_checkbox("Sản phẩm yêu cầu vận chuyển", True)
        if p.get("weight_g"):
            w = self._by_label(["Khối lượng"], "weight")
            if w:
                self._type(w, p["weight_g"])
                self.log(f"    · Khối lượng: {p['weight_g']} g")

        self._fill_combo(self.TYPE_PH, ["Loại"], opts.get("product_type"), "Loại")
        self._fill_combo(self.VENDOR_PH, ["Nhà cung cấp"], opts.get("vendor"), "Nhà cung cấp")
        self._pick_collections(opts.get("collections") or [])
        self._add_tags(opts.get("tags") or [])

        if opts.get("auto_save", True):
            url = self._save()
            self.log(f"    ✓ Đã lưu: {url}")
            return url
        self.wait_user("Kiểm tra form trên trình duyệt rồi tự bấm Lưu. Xong thì bấm Tiếp tục.")
        return self.page.url

    def screenshot(self, path):
        try:
            self.page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass
