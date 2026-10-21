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
([html, label]) => {
  // Điền vào ĐÚNG trình soạn thảo nằm ngay dưới nhãn (mặc định "Nội dung"),
  // KHÔNG đụng tới trình soạn thảo "Mô tả ngắn" (có thể đã được tạo sẵn nhưng đang ẩn).
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const EDITOR_SEL = '.fr-box, .fr-element, .cke, .tox, .tox-tinymce, [contenteditable=true], iframe';
  const lab = [...document.querySelectorAll('label, div, span, p, strong, h3, h4')]
    .find(e => vis(e) && e.children.length === 0 && norm(e.textContent) === norm(label));
  if (!lab) return { how: 'none', why: 'no-label' };
  // trình soạn thảo ĐẦU TIÊN đứng sau nhãn (theo thứ tự trên trang)
  let target = null;
  for (let n = lab.parentElement, k = 0; !target && n && k < 6; n = n.parentElement, k++)
    target = [...n.querySelectorAll(EDITOR_SEL)].find(e => vis(e) && (lab.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING));
  if (!target) return { how: 'none', why: 'no-editor' };
  const box = target.closest('.fr-box, .cke, .tox, .tox-tinymce') || target;
  const inBox = el => !!el && (box === el || box.contains(el) || el.contains(box));
  const fire = el => ['input', 'keyup', 'change', 'blur'].forEach(ev => el.dispatchEvent(new Event(ev, { bubbles: true })));
  try {
    if (window.FroalaEditor && FroalaEditor.INSTANCES) {
      const ed = FroalaEditor.INSTANCES.find(i => inBox(i.el) || (i.$box && inBox(i.$box[0])));
      if (ed) { ed.html.set(html); ed.events.trigger('contentChanged'); if (ed.undo) ed.undo.saveStep(); return { how: 'froala' }; }
    }
  } catch (e) {}
  try {
    if (window.jQuery && jQuery.fn.froalaEditor) {
      const el = jQuery('*').filter(function () { return jQuery(this).data('froala.editor') && inBox(this); }).first();
      if (el.length) { el.froalaEditor('html.set', html); el.froalaEditor('events.trigger', 'contentChanged'); return { how: 'froala-v2' }; }
    }
  } catch (e) {}
  try {
    if (window.CKEDITOR && CKEDITOR.instances) {
      const ed = Object.values(CKEDITOR.instances).find(i => i.container && inBox(i.container.$));
      if (ed) { ed.setData(html); ed.updateElement(); return { how: 'ckeditor' }; }
    }
  } catch (e) {}
  try {
    if (window.tinymce && tinymce.editors) {
      const ed = [...tinymce.editors].find(i => inBox(i.getContainer()));
      if (ed) { ed.setContent(html); ed.save(); ed.fire('change'); return { how: 'tinymce' }; }
    }
  } catch (e) {}
  const ce = target.matches('[contenteditable=true]') ? target : box.querySelector('[contenteditable=true], .fr-element');
  if (ce) {
    ce.focus(); ce.innerHTML = html; fire(ce);
    const ta = box.parentElement && box.parentElement.querySelector('textarea');
    if (ta) { ta.value = html; fire(ta); }
    return { how: 'contenteditable' };
  }
  const f = target.tagName === 'IFRAME' ? target : box.querySelector('iframe');
  try {
    const b = f && f.contentDocument && f.contentDocument.body;
    if (b) { b.innerHTML = html; fire(b); return { how: 'iframe' }; }
  } catch (e) {}
  return { how: 'none', why: 'no-api' };
}
"""

EDITOR_TEXT_JS = r"""
(label) => {
  // đọc chữ trong trình soạn thảo đứng sau nhãn (để kiểm tra / dọn ô Mô tả ngắn)
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const vis = e => !!(e && (e.offsetWidth || e.offsetHeight || e.getClientRects().length));
  const lab = [...document.querySelectorAll('label, div, span, p, strong, h3, h4')]
    .find(e => e.children.length === 0 && norm(e.textContent) === norm(label));
  if (!lab) return null;
  for (let n = lab.parentElement, k = 0; n && k < 6; n = n.parentElement, k++) {
    const ed = [...n.querySelectorAll('.fr-element, [contenteditable=true], .cke_editable')]
      .find(e => lab.compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING);
    if (ed) { ed.setAttribute('data-dt-editor', norm(label)); return norm(ed.textContent); }
  }
  return null;
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


MARK_IN_ROOT_JS = r"""
([rootSel, labels, mark]) => {
  // giống MARK_INPUT_JS nhưng chỉ tìm trong 1 vùng (vd hộp thoại)
  const root = document.querySelector(rootSel) || document;
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase().replace(/[:*]$/, '').trim();
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const want = labels.map(norm);
  const labs = [...root.querySelectorAll('label, span, div, p, strong, b, th')]
    .filter(e => vis(e) && e.children.length <= 1 && want.includes(norm(e.textContent)));
  for (const lab of labs) {
    let inp = lab.tagName === 'LABEL' && lab.htmlFor ? document.getElementById(lab.htmlFor) : null;
    for (let n = lab, k = 0; !inp && n && k < 5; n = n.parentElement, k++)
      inp = [...n.querySelectorAll('input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=file]), textarea')]
              .find(i => vis(i) && (lab.compareDocumentPosition(i) & Node.DOCUMENT_POSITION_FOLLOWING));
    if (inp) { inp.setAttribute('data-dt-mark', mark); return true; }
  }
  return false;
}
"""

MODAL_JS = r"""
() => {
  const vis = e => !!(e.offsetWidth || e.offsetHeight) && getComputedStyle(e).visibility !== 'hidden'
                   && getComputedStyle(e).display !== 'none';
  document.querySelectorAll('[data-dt-modal]').forEach(e => e.removeAttribute('data-dt-modal'));
  const c = [...document.querySelectorAll('.modal.show .modal-content, .modal.in .modal-content, .modal-dialog, [role=dialog], .ui-modal, .ui-modal-content, .popup-content, .modal .modal-content, .modal')]
              .filter(vis);
  if (!c.length) return false;
  // ưu tiên phần tử trong cùng (nội dung hộp thoại), không lấy lớp nền phủ ngoài
  const inner = c.filter(e => !c.some(o => o !== e && e.contains(o)));
  inner[inner.length - 1].setAttribute('data-dt-modal', '1');
  return true;
}
"""

VARIANT_ROWS_JS = r"""
(values) => {
  // tìm dòng của từng phiên bản trong bảng phiên bản (dòng có chữ = giá trị thuộc tính)
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  document.querySelectorAll('[data-dt-vrow]').forEach(e => e.removeAttribute('data-dt-vrow'));
  const cellText = c => norm(c.textContent) || norm((c.querySelector('input') || {}).value);
  let head = [];
  const tables = [...document.querySelectorAll('table')].filter(t => vis(t) && /sku/i.test(t.textContent));
  const t = tables.find(t => values.every(v => [...t.querySelectorAll('td')].some(c => cellText(c) === norm(v))));
  let rows = [];
  if (t) {
    const hr = t.querySelector('thead tr') || t.querySelector('tr');
    head = [...hr.children].map(c => norm(c.textContent));
    rows = [...t.querySelectorAll('tr')].filter(r => r !== hr);
  } else {
    rows = [...document.querySelectorAll('button, a')].filter(b => vis(b) && norm(b.textContent) === 'sửa')
             .map(b => b.closest('tr, li, [class*=row], [class*=item]')).filter(Boolean);
  }
  return { head, found: values.map((v, i) => {
    const r = rows.find(r => [...r.querySelectorAll('td, div, span, a, input')].some(c => cellText(c) === norm(v)));
    if (!r) return false;
    r.setAttribute('data-dt-vrow', String(i));
    return true;
  }) };
}
"""


STATUS_JS = r"""
(want) => {
  // Mục "Trạng thái": chọn ô Hiển thị / Ẩn
  const norm = s => (s || '').replace(/\s+/g, ' ').trim().toLowerCase();
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const head = [...document.querySelectorAll('h1,h2,h3,h4,h5,label,span,div,p,strong')]
    .find(e => vis(e) && e.children.length === 0 && norm(e.textContent) === 'trạng thái');
  let card = head;
  for (let k = 0; card && k < 6 && card.querySelectorAll('input[type=radio]').length < 2; k++) card = card.parentElement;
  if (!card) return { found: false };
  for (const r of card.querySelectorAll('input[type=radio]')) {
    const lab = r.closest('label') || (r.id && document.querySelector(`label[for="${r.id}"]`)) || r.parentElement;
    if (norm(lab.textContent) === norm(want)) {
      document.querySelectorAll('[data-dt-status]').forEach(e => e.removeAttribute('data-dt-status'));
      lab.setAttribute('data-dt-status', 'label'); r.setAttribute('data-dt-status', 'radio');
      return { found: true, checked: r.checked };
    }
  }
  return { found: false };
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
        """Đặc điểm + Thông số → CHỈ vào ô "Nội dung" chính, không vào "Mô tả ngắn"."""
        res = self.page.evaluate(EDITOR_JS, [html, "Nội dung"])
        how = res.get("how", "none")
        if how == "none":
            # Phương án cuối: nút "Mã HTML" ĐẦU TIÊN (thuộc ô Nội dung) và dán mã
            btn = self.page.locator('button:has-text("Mã HTML"), [title="Mã HTML"], [data-cmd="html"]').first
            if btn.count():
                btn.click()
                ta = self.page.locator("textarea:visible").first
                ta.fill(html)
                btn.click()
                how = "code-view"
        # kiểm tra: ô Nội dung có dữ liệu, ô Mô tả ngắn KHÔNG bị điền nhầm
        probe = re.sub(r"<[^>]+>", " ", html)
        probe = re.sub(r"\s+", " ", probe).strip().lower()[:25]
        main_txt = self.page.evaluate(EDITOR_TEXT_JS, "Nội dung") or ""
        short_txt = self.page.evaluate(EDITOR_TEXT_JS, "Mô tả ngắn") or ""
        if probe and probe in short_txt:
            self.page.evaluate("""() => { const e = document.querySelector('[data-dt-editor="mô tả ngắn"]');
                if (e) { e.innerHTML = ''; ['input','keyup','change'].forEach(ev => e.dispatchEvent(new Event(ev, {bubbles:true}))); } }""")
            self.log("    ! Đã xoá nội dung lỡ điền vào ô Mô tả ngắn")
        ok = (not probe) or probe in main_txt or how in ("froala", "froala-v2", "ckeditor", "tinymce")
        self.log(f"    · Nội dung (ô chính): đã điền ({how})" + ("" if ok else " – ! chưa kiểm tra được, hãy xem lại"))
        if how == "none":
            self.log(f"    ! Không tìm thấy trình soạn thảo Nội dung ({res.get('why')}) – cần dán nội dung thủ công.")

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

    def _set_status(self, visible):
        want = "Hiển thị" if visible else "Ẩn"
        st = self.page.evaluate(STATUS_JS, want)
        if not st.get("found"):
            self.log(f"    ! Không tìm thấy ô Trạng thái '{want}'")
            return
        if not st["checked"]:
            self.page.locator('[data-dt-status="label"]').first.click()
            if not self.page.evaluate(STATUS_JS, want).get("checked"):
                self.page.locator('[data-dt-status="radio"]').first.click(force=True)
        ok = self.page.evaluate(STATUS_JS, want).get("checked")
        self.log(f"    · Trạng thái: {want}" + ("" if ok else " (! chưa chọn được)"))

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

        self._set_status(opts.get("visible", True))
        name_input = self._by_placeholder(self.NAME_PH) or self._by_label(["Tên sản phẩm"], "name")
        if not name_input:
            raise SapoError("Không tìm thấy ô 'Tên sản phẩm' trên form Sapo (giao diện Sapo có thể đã đổi)")
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

        issues = []
        if opts.get("variant_attr") and len(p.get("variants") or []) >= 2:
            issues = self._add_variants(opts["variant_attr"], p["variants"], int(p.get("variant_images") or 0))
            for msg in issues:
                self.log(f"    ! {msg}")

        self._fill_combo(self.TYPE_PH, ["Loại"], opts.get("product_type"), "Loại")
        self._fill_combo(self.VENDOR_PH, ["Nhà cung cấp"], opts.get("vendor"), "Nhà cung cấp")
        self._pick_collections(opts.get("collections") or [])
        self._add_tags(opts.get("tags") or [])

        if issues and opts.get("auto_save", True):
            # không lưu khi phiên bản chưa đầy đủ → để người dùng hoàn tất, tránh đăng sai giá/ảnh
            if self.cfg.get("output_dir"):
                logs = Path(self.cfg["output_dir"]) / "logs"
                logs.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d-%H%M%S")
                self.dump_html(logs / f"sapo-form-{stamp}.html")
                self.screenshot(logs / f"sapo-form-{stamp}.png")
                self.log(f"    ! Đã lưu form Sapo vào output/logs/sapo-form-{stamp}.html (gửi file này để chỉnh công cụ)")
            self.wait_user("Phiên bản chưa đầy đủ (xem log). Hãy hoàn tất phần Thuộc tính trên trình duyệt "
                           "rồi bấm Lưu, sau đó bấm Tiếp tục.")
            return self._saved_url()
        if opts.get("auto_save", True):
            url = self._save()
            self.log(f"    ✓ Đã lưu: {url}")
            return url
        self.wait_user("Kiểm tra form trên trình duyệt rồi tự bấm Lưu. Xong thì bấm Tiếp tục.")
        return self._saved_url()

    def _saved_url(self):
        """Sau khi người dùng tự xử lý: còn ở trang 'tạo mới' nghĩa là CHƯA lưu → trả None."""
        try:
            self.page.wait_for_timeout(500)
            url = self.page.url
        except Exception:
            return None
        return None if "/products/create" in url else url

    # ---------------- phiên bản (thuộc tính) ----------------
    def _modal(self, timeout=5000):
        end = time.time() + timeout / 1000
        while time.time() < end:
            if self.page.evaluate(MODAL_JS):
                return self.page.locator('[data-dt-modal]').first
            self.page.wait_for_timeout(250)
        return None

    def _click_text(self, root, texts):
        for t in texts:
            loc = root.get_by_role("button", name=re.compile(rf"^\s*{re.escape(t)}\s*$", re.I))
            vis = [loc.nth(i) for i in range(loc.count()) if loc.nth(i).is_visible()]
            if not vis:
                loc = root.get_by_text(t, exact=True)
                vis = [loc.nth(i) for i in range(loc.count()) if loc.nth(i).is_visible()]
            if vis:
                vis[-1].click()
                return True
        return False

    def _fill_in(self, root_sel, labels, value, mark):
        if self.page.evaluate(MARK_IN_ROOT_JS, [root_sel, labels, mark]):
            self._type(self.page.locator(f'[data-dt-mark="{mark}"]').first, value)
            return True
        return False

    def _add_variants(self, attr_name, variants, n_images):
        """Tạo thuộc tính + giá trị, rồi đặt Giá / SKU / Ảnh cho từng phiên bản. Trả danh sách việc chưa làm được."""
        issues = []
        values = [v["value"] for v in variants]
        # 1) mở khung Thuộc tính
        if not self.page.locator('input[placeholder="Nhập giá trị thuộc tính"]:visible').count():
            if not self._click_text(self.page, ["Thêm thuộc tính"]):
                return ["Không thấy nút 'Thêm thuộc tính'"]
            self.page.wait_for_timeout(600)
        # 2) tên thuộc tính
        if not self._fill_in("body", ["Tên thuộc tính"], attr_name, "attr-name"):
            issues.append("Không điền được 'Tên thuộc tính'")
        # 3) giá trị (gõ từng giá trị rồi Enter)
        val_in = self._by_placeholder(["Nhập giá trị thuộc tính"])
        if not val_in:
            return issues + ["Không thấy ô 'Giá trị' thuộc tính"]
        for v in values:
            val_in.click()
            val_in.press_sequentially(v, delay=15)
            val_in.press("Enter")
            self.page.wait_for_timeout(350)
            if val_in.input_value().strip():          # ô kiểu "tag" dùng dấu phẩy
                val_in.press(",")
                self.page.wait_for_timeout(300)
        val_in.press("Tab")
        self.page.wait_for_timeout(1500)
        self.log(f"    · Thuộc tính '{attr_name}': {', '.join(values)}")
        # 4) từng phiên bản
        info = self.page.evaluate(VARIANT_ROWS_JS, values)
        head = info.get("head") or []
        col = lambda *names: next((i for i, h in enumerate(head) if any(h == n or h.startswith(n) for n in names)), None)
        c_price, c_sku = col("giá"), col("sku", "mã sản phẩm")
        for i, v in enumerate(variants):
            if not info["found"][i]:
                issues.append(f"Không thấy dòng phiên bản '{v['value']}'")
                continue
            row = self.page.locator(f'[data-dt-vrow="{i}"]').first
            ok_price = ok_sku = False
            # 4a) ô nhập ngay trên dòng (nếu bảng cho sửa trực tiếp)
            cells = row.locator("td")
            for c_idx, val, kind in ((c_price, v.get("price"), "price"), (c_sku, v.get("sku"), "sku")):
                if c_idx is None or val in (None, "") or c_idx >= cells.count():
                    continue
                inp = cells.nth(c_idx).locator("input:visible")
                if inp.count():
                    self._type(inp.first, val)
                    ok_price |= kind == "price"
                    ok_sku |= kind == "sku"
            # 4b) không sửa trực tiếp được → nút "Sửa" mở hộp thoại
            if (not ok_price and v.get("price")) or (not ok_sku and v.get("sku")):
                btn = row.get_by_text("Sửa", exact=True)
                if btn.count():
                    btn.first.click()
                    modal = self._modal()
                    if modal:
                        if v.get("price") and not ok_price:
                            ok_price = self._fill_in("[data-dt-modal]", ["Giá", "Giá bán"], v["price"], f"vp{i}")
                        if v.get("sku") and not ok_sku:
                            ok_sku = self._fill_in("[data-dt-modal]", ["Mã sản phẩm / SKU", "Mã sản phẩm/SKU", "SKU", "Mã sản phẩm"], v["sku"], f"vs{i}")
                        if not self._click_text(modal, ["Lưu", "Cập nhật", "Xong", "Đồng ý", "Áp dụng"]):
                            issues.append(f"Không đóng được hộp thoại Sửa của '{v['value']}'")
                            self.page.keyboard.press("Escape")
                        self.page.wait_for_timeout(600)
                        self.page.evaluate(VARIANT_ROWS_JS, values)
                        row = self.page.locator(f'[data-dt-vrow="{i}"]').first
            if v.get("price") and not ok_price:
                issues.append(f"Chưa đặt được giá cho '{v['value']}'")
            if v.get("sku") and not ok_sku:
                issues.append(f"Chưa đặt được SKU cho '{v['value']}'")
            # 4c) ảnh: bấm ô ảnh trên dòng → chọn ảnh thứ i trong hộp thoại
            if i < n_images:
                try:
                    pic = row.locator("img, [class*=image], [class*=thumb], [class*=photo]").first
                    pic.click(timeout=3000)
                    modal = self._modal()
                    if not modal:
                        raise SapoError("không mở hộp chọn ảnh")
                    thumbs = modal.locator("img")
                    if thumbs.count() <= i:
                        raise SapoError(f"hộp thoại chỉ có {thumbs.count()} ảnh")
                    thumbs.nth(i).click()
                    self.page.wait_for_timeout(300)
                    self._click_text(modal, ["Lưu", "Chọn", "Xong", "Đồng ý", "Áp dụng", "Cập nhật"])
                    self.page.wait_for_timeout(600)
                    self.page.evaluate(VARIANT_ROWS_JS, values)
                except Exception as e:
                    issues.append(f"Chưa gán ảnh cho '{v['value']}' ({str(e).splitlines()[0][:80]})")
                    self.page.keyboard.press("Escape")
            p = f"{v['price']:,}".replace(",", ".") if v.get("price") else "-"
            self.log(f"    · Phiên bản {v['value']}: giá {p} | SKU {v.get('sku') or '-'} | ảnh {i + 1 if i < n_images else '-'}")
        return issues

    def dump_html(self, path):
        try:
            Path(path).write_text(self.page.content(), encoding="utf-8")
        except Exception:
            pass

    def screenshot(self, path):
        try:
            self.page.screenshot(path=str(path), full_page=True)
        except Exception:
            pass
