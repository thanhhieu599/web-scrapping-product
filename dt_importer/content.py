"""Dựng HTML cho ô "Nội dung" của Sapo: Đặc điểm + Thông số kỹ thuật.

Dùng inline style để hiển thị đẹp ở mọi theme Sapo (không phụ thuộc CSS theme).
"""
from html import escape

# Chữ màu đen, không gạch chân tiêu đề; bảng kẻ khung xám, dòng tiêu đề nền xám nhạt
BLACK = "#000"
TH = f"background:#f2f2f2;color:{BLACK};font-weight:700;padding:8px 10px;border:1px solid #d9d9d9;text-align:center;"
TD_LABEL = f"color:{BLACK};padding:8px 10px;border:1px solid #d9d9d9;font-weight:600;"
TD = f"color:{BLACK};padding:8px 10px;border:1px solid #d9d9d9;text-align:center;"
SECTION = f"color:{BLACK};padding:8px 10px;border:1px solid #d9d9d9;background:#fafafa;font-weight:700;text-transform:uppercase;"
H2 = f"font-size:20px;font-weight:700;color:{BLACK};margin:24px 0 12px;"


IMG = "max-width:100%;height:auto;max-height:220px;"


def _img(url, alt=""):
    return f'<img src="{escape(url, quote=True)}" alt="{escape(alt, quote=True)}" style="{IMG}">'


def _features_html(features, images=None, name=""):
    if not features and not images:
        return ""
    out = [f'<h2 style="{H2}">Đặc điểm nổi bật</h2>']
    if features:
        items = "".join(f'<li style="margin:4px 0;">{escape(f)}</li>' for f in features)
        out.append(f'<ul style="padding-left:20px;line-height:1.7;color:#000;">{items}</ul>')
    if images:
        out.append('<p style="text-align:center;">' + " ".join(_img(u, name) for u in images) + "</p>")
    return "".join(out)


def _spec_html(spec, sku=""):
    if not spec:
        return ""
    rows, headers, text = spec.get("rows") or [], spec.get("headers") or [], spec.get("text") or []
    if not rows and not text:
        return ""
    out = [f'<h2 style="{H2}">Thông số kỹ thuật</h2>']
    if not rows:
        out.append("".join(f"<p>{escape(t)}</p>" for t in text))
        return "".join(out)

    ncol = max([len(headers)] + [len(r.get("values") or []) for r in rows])
    ncol = max(ncol, 1)
    if not headers:
        headers = ["Giá trị"] if ncol == 1 else [f"Model {i + 1}" for i in range(ncol)]
    headers = (headers + [""] * ncol)[:ncol]

    sku_l = (sku or "").lower()
    images = ((spec.get("images") or []) + [""] * ncol)[:ncol]
    ths = "".join(
        f'<th style="{TH}">{"<strong>" if sku_l and sku_l in h.lower() else ""}{escape(h)}'
        f'{"</strong>" if sku_l and sku_l in h.lower() else ""}</th>' for h in headers)
    out.append('<table style="width:100%;border-collapse:collapse;font-size:14px;" border="1" cellpadding="6">')
    out.append("<thead>")
    if any(images):
        # hàng ảnh sản phẩm phía trên các cột model (giống trang gốc)
        tds = "".join(f'<td style="{TD}background:#fff;">{_img(u, h) if u else ""}</td>' for u, h in zip(images, headers))
        out.append(f'<tr><td style="{TD}background:#fff;"></td>{tds}</tr>')
    out.append(f'<tr><th style="{TH}text-align:left;">Thông số</th>{ths}</tr></thead><tbody>')
    zebra = 0
    for r in rows:
        if "section" in r:
            out.append(f'<tr><td colspan="{ncol + 1}" style="{SECTION}">{escape(r["section"])}</td></tr>')
            zebra = 0
            continue
        vals = ((r.get("values") or []) + [""] * ncol)[:ncol]
        bg = "background:#fafafa;" if zebra % 2 else ""
        zebra += 1
        tds = "".join(f'<td style="{TD}{bg}">{escape(v)}</td>' for v in vals)
        out.append(f'<tr><td style="{TD_LABEL}{bg}">{escape(r.get("label", ""))}</td>{tds}</tr>')
    out.append("</tbody></table>")
    return "".join(out)




# ---------- Chế độ "description": dùng mô tả gốc của nhà cung cấp (đã làm sạch) ----------
from html.parser import HTMLParser  # noqa: E402
from urllib.parse import urljoin  # noqa: E402

ALLOWED = {"p", "br", "ul", "ol", "li", "strong", "b", "em", "i", "u", "h2", "h3", "h4", "table", "thead",
           "tbody", "tr", "th", "td", "img", "span", "div", "blockquote", "sub", "sup", "hr", "figure", "figcaption"}
DROP_WITH_CONTENT = {"script", "style", "noscript", "iframe", "form", "button", "svg", "template", "object", "embed"}
VOID = {"br", "img", "hr"}
TAG_STYLE = {"h2": H2, "h3": f"font-size:17px;font-weight:700;color:{BLACK};margin:18px 0 8px;",
             "h4": f"font-size:15px;font-weight:700;color:{BLACK};margin:14px 0 6px;",
             "table": "width:100%;border-collapse:collapse;font-size:14px;",
             "th": TH, "td": f"color:{BLACK};padding:8px 10px;border:1px solid #d9d9d9;",
             "img": "max-width:100%;height:auto;", "p": f"color:{BLACK};", "li": f"color:{BLACK};"}


class _Clean(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base, self.out, self.skip, self.open = base, [], 0, []

    def handle_starttag(self, tag, attrs):
        if tag in DROP_WITH_CONTENT:
            self.skip += tag not in VOID
            return
        if self.skip:
            return
        if tag == "h1":
            tag = "h2"
        if tag not in ALLOWED:
            return
        a = dict(attrs)
        keep = []
        if tag == "img":
            src = a.get("data-src") or a.get("data-lazy-src") or a.get("src") or ""
            if not src or src.startswith("data:"):
                return
            src = urljoin(self.base, src)
            if not src.startswith(("http://", "https://")):
                return
            keep.append(("src", src))
            if a.get("alt"):
                keep.append(("alt", a["alt"]))
        if tag in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if (a.get(k) or "").isdigit():
                    keep.append((k, a[k]))
        if tag in TAG_STYLE:
            keep.append(("style", TAG_STYLE[tag]))
        attr = "".join(f' {k}="{escape(v, quote=True)}"' for k, v in keep)
        self.out.append(f"<{tag}{attr}>")
        if tag not in VOID:
            self.open.append(tag)

    def handle_endtag(self, tag):
        if tag in DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        tag = "h2" if tag == "h1" else tag
        if tag in ALLOWED and tag not in VOID and tag in self.open:
            while self.open:                               # đóng các thẻ còn mở bên trong
                t = self.open.pop()
                self.out.append(f"</{t}>")
                if t == tag:
                    break

    def handle_data(self, data):
        if not self.skip:
            self.out.append(escape(data, quote=False))

    def result(self):
        while self.open:
            self.out.append(f"</{self.open.pop()}>")
        return "".join(self.out)


def clean_description(html, base_url=""):
    """Mô tả gốc → HTML an toàn: chỉ giữ thẻ định dạng cơ bản, bỏ script/style/sự kiện, ảnh link tuyệt đối, chữ đen."""
    if not html:
        return ""
    p = _Clean(base_url)
    p.feed(html)
    p.close()
    out = p.result().strip()
    import re
    out = re.sub(r"<(p|div|span|li|h[234])[^>]*>\s*</\1>", "", out)        # bỏ khối rỗng
    return out


def _description_html(data):
    desc = clean_description(data.get("description_html"), data.get("url") or "")
    if not desc:
        return ""
    return f'<div style="color:{BLACK};line-height:1.7;">{desc}</div>'


def build_content_html(data, mode="features_specs"):
    """mode: "features_specs" = Đặc điểm + Thông số (mặc định);
             "description"   = mô tả gốc của web (làm sạch) + bảng thông số/thuộc tính."""
    if mode == "description" and data.get("description_html"):
        parts = [_description_html(data), _spec_html(data.get("spec"), data.get("sku"))]
        html = "".join(p for p in parts if p)
        if html:
            return html
    parts = [_features_html(data.get("features"), data.get("feature_images"), data.get("name", "")),
             _spec_html(data.get("spec"), data.get("sku"))]
    return "".join(p for p in parts if p)
