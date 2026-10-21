"""Dựng HTML cho ô "Nội dung" của Sapo: Đặc điểm + Thông số kỹ thuật.

Dùng inline style để hiển thị đẹp ở mọi theme Sapo (không phụ thuộc CSS theme).
"""
from html import escape

RED = "#c8102e"
TH = f"background:{RED};color:#fff;padding:8px 10px;border:1px solid #e5e5e5;text-align:center;"
TD_LABEL = "padding:8px 10px;border:1px solid #e5e5e5;font-weight:600;"
TD = "padding:8px 10px;border:1px solid #e5e5e5;text-align:center;"
SECTION = "padding:8px 10px;border:1px solid #e5e5e5;background:#f2f2f2;font-weight:700;text-transform:uppercase;"
H2 = f"font-size:20px;color:{RED};border-bottom:2px solid {RED};padding-bottom:6px;margin:24px 0 12px;"


IMG = "max-width:100%;height:auto;max-height:220px;"


def _img(url, alt=""):
    return f'<img src="{escape(url, quote=True)}" alt="{escape(alt, quote=True)}" style="{IMG}">'


def _features_html(features, images=None, name=""):
    if not features and not images:
        return ""
    out = [f'<h2 style="{H2}">Đặc điểm nổi bật</h2>']
    if features:
        items = "".join(f'<li style="margin:4px 0;">{escape(f)}</li>' for f in features)
        out.append(f'<ul style="padding-left:20px;line-height:1.7;">{items}</ul>')
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


def build_content_html(data):
    parts = [_features_html(data.get("features"), data.get("feature_images"), data.get("name", "")),
             _spec_html(data.get("spec"), data.get("sku"))]
    return "".join(p for p in parts if p)
