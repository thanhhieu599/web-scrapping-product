"""Kiểm thử từng hàm xử lý dữ liệu (không cần trình duyệt, không cần Internet).

    python tests/test_units.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dt_importer.content import build_content_html  # noqa: E402
from dt_importer.scraper import Scraper, code_from_url, pick_images, upgrade_image_url, weight_grams  # noqa: E402
from dt_importer.utils import format_vnd, name_with_vendor, parse_vnd, slugify  # noqa: E402

fails = 0


def eq(got, want, msg):
    global fails
    ok = got == want
    fails += not ok
    print(("  PASS " if ok else "  FAIL ") + msg + ("" if ok else f"\n        nhận: {got!r}\n        cần:  {want!r}"))


print("=== Đọc giá ===")
for text, want in [("2.940.000 ₫", 2940000), ("2,940,000đ", 2940000), ("2 940 000 VND", 2940000),
                   ("1.234.567,00 ₫", 1234567), ("Liên hệ", None), ("", None), (None, None),
                   (2820000, 2820000), (2700000.0, 2700000), (2699999.6, 2700000), (True, None)]:
    eq(parse_vnd(text), want, f"parse_vnd({text!r})")
eq(format_vnd(2940000), "2.940.000 ₫", "format_vnd")
eq(format_vnd(None), "", "format_vnd(None)")

print("=== Chèn nhà cung cấp vào tên ===")
for name, vendor, want in [
    ("Hộp đựng dụng cụ 8450, 8424, 8425", "milwaukeetool", "Hộp đựng dụng cụ milwaukeetool 8450, 8424, 8425"),
    ("Hộp đựng dụng cụ 8424 (Màu đen)", "Milwaukeetool", "Hộp đựng dụng cụ Milwaukeetool 8424 (Màu đen)"),
    ("Găng tay chống cắt", "TOWA", "Găng tay chống cắt TOWA"),
    ("Găng tay chống cắt cấp độ 5", "TOWA", "Găng tay chống cắt cấp độ 5 TOWA"),
    ("Máy khoan M18 FPD3", "Milwaukee", "Máy khoan Milwaukee M18 FPD3"),
    ("Hộp PACKOUT 48-22-8450", "Milwaukee", "Hộp PACKOUT Milwaukee 48-22-8450"),
    ("Kính IP65 chống bụi", "3M", "Kính IP65 chống bụi 3M"),
    ("Găng tay EN388 4X43C", "TOWA", "Găng tay EN388 4X43C TOWA"),
    ("Giày bảo hộ EN ISO 20345 S3", "Jogger", "Giày bảo hộ EN ISO 20345 S3 Jogger"),
    ("Găng tay TOWA 371 chống dầu", "TOWA", "Găng tay TOWA 371 chống dầu"),
    ("Găng tay chống dầu 371 EN388 4121", "TOWA", "Găng tay chống dầu TOWA 371 EN388 4121"),
    ("Giày Jogger 123456", "Jogger", "Giày Jogger 123456"),              # đã có nhà cung cấp → giữ nguyên
    ("Găng tay", "", "Găng tay"),                                         # không nhập nhà cung cấp
    ("8450 hộp dụng cụ", "Milwaukee", "8450 hộp dụng cụ Milwaukee"),      # mã ở đầu tên → thêm cuối
]:
    eq(name_with_vendor(name, vendor), want, f"{name!r} + {vendor!r}")

print("=== Mã từ tên file ảnh / link ảnh gốc ===")
eq(code_from_url("https://x/media/catalog/product/4/8/48-22-8425-hero01.png"), "48-22-8425", "code_from_url Milwaukee")
eq(code_from_url("https://x/img/p2.jpg"), "", "code_from_url không có mã")
eq(upgrade_image_url("https://x/media/catalog/product/cache/5c7627f362bdde1179db0676ee17f90a/4/8/a.png", []),
   "https://x/media/catalog/product/4/8/a.png", "Magento: bỏ /cache/<mã>/")
eq(upgrade_image_url("https://x/a.jpg?width=80&v=3", ["width"]), "https://x/a.jpg?v=3", "bỏ tham số thu nhỏ, giữ tham số khác")
eq(slugify("Hộp đựng 48-22-8450"), "hop-dung-48-22-8450", "slugify tiếng Việt")

print("=== Khối lượng theo đúng cột mã SP ===")
spec = {"headers": ["48-22-8424", "48-22-8425", "48-22-8450"],
        "rows": [{"label": "Trọng lượng (kg)", "values": ["4.6", "5.5", "2.58"]}]}
eq(weight_grams({"sku": "48-22-8450", "spec": spec}), 2580, "cột 8450 → 2580 g")
eq(weight_grams({"sku": "48-22-8424", "spec": spec}), 4600, "cột 8424 → 4600 g")
eq(weight_grams({"sku": "XYZ", "spec": spec}), None, "mã không có trong bảng nhiều cột → không đoán")
eq(weight_grams({"sku": "A1", "spec": {"headers": [], "rows": [{"label": "Khối lượng", "values": ["850 g"]}]}}), 850, "đơn vị gram")
eq(weight_grams({"sku": "A1", "spec": {"headers": [], "rows": [{"label": "Trọng lượng (kg)", "values": ["1,2"]}]}}), 1200, "dấu phẩy thập phân")
eq(weight_grams({"sku": "A1", "spec": {}}), None, "không có bảng")

print("=== Nội dung HTML ===")
html = build_content_html({"name": "X", "sku": "A1", "features": ["<script>alert(1)</script>", "Bền & nhẹ"],
                           "feature_images": ['https://x/a.jpg" onerror="alert(1)'],
                           "spec": {"headers": [], "rows": [{"label": "<b>Dài</b>", "values": ["1"]}], "images": []}})
eq("<script>" in html, False, "chặn mã độc trong Đặc điểm (escape)")
eq('onerror="alert' in html, False, "chặn mã độc trong link ảnh")
eq("Bền &amp; nhẹ" in html, True, "giữ đúng ký tự &")
eq("<table" in html and "Giá trị" in html, True, "bảng 1 cột có tiêu đề 'Giá trị'")
eq(build_content_html({"features": [], "spec": {}}), "", "không có dữ liệu → nội dung rỗng")
html2 = build_content_html({"sku": "48-22-8450", "features": ["a"],
                            "spec": {"headers": ["48-22-8424", "48-22-8450"], "images": ["https://x/1.png", ""],
                                     "rows": [{"section": "NHÓM"}, {"label": "Dài", "values": ["1", "2"]}]}})
eq(html2.count("<img"), 1, "hàng ảnh: chỉ cột có ảnh")
eq("<strong>48-22-8450</strong>" in html2, True, "tô đậm cột của mã đang đăng")
eq('colspan="3"' in html2, True, "dòng tiêu đề nhóm trải hết bảng")

print("=== Nhận diện trang sản phẩm ===")
P = lambda **f: {"name": f.pop("name", "SP"), "sku": f.pop("sku", ""), "found": f}
eq(Scraper.is_product(P(price=True, sku="", features=True)), True, "có giá + đặc điểm")
eq(Scraper.is_product(P(price=False, sku="A-1", specs=True)), True, "sản phẩm 'Liên hệ' (không giá) có mã + thông số")
eq(Scraper.is_product(P(price=False, sku="", features=True)), False, "không giá, không mã → không chắc là SP")
eq(Scraper.is_product(P(price=True)), False, "trang danh mục (chỉ có giá)")
eq(Scraper.is_product(P(name="", price=True, sku="A")), False, "không có tên")
eq(Scraper.is_product(P(price=True, sku="48-22-8424", listing=True)), False, "trang danh mục có mã + giá ở thẻ SP → KHÔNG phải SP")
eq(Scraper.is_product(P(price=True, sku="48-22-8424", listing=True, product_view=True)), True, "trang SP có khối 'SP liên quan' vẫn là SP")
eq(Scraper.is_product(P(price=True, sku="A1", listing=True, specs=True)), True, "có Thông số → trang chi tiết dù có nhiều giá")

print("=== Chọn ảnh ===")
d = {"variant_images": ["v1", "v2"], "gallery_images": ["g1", "v1"]}
eq(pick_images(d, "quycach"), ["v1", "v2"], "quycach")
eq(pick_images(d, "gallery"), ["g1", "v1"], "gallery")
eq(pick_images(d, "both"), ["v1", "v2", "g1"], "both (không trùng)")
eq(pick_images({"variant_images": [], "gallery_images": ["g1"]}, "quycach"), ["g1"], "không có ảnh quy cách → dùng gallery")

print("=== Nhận diện ảnh trùng (cùng hình khác kích thước) ===")
from PIL import Image as _I, ImageDraw as _D
from dt_importer.scraper import _image_signature, _same_image
_a = _I.new("RGB", (1200, 900), (255, 255, 255)); _D.Draw(_a).rectangle([200, 200, 900, 700], fill=(200, 20, 40))
_b = _a.resize((600, 450))                                                    # cùng hình, nhỏ hơn
_c = _I.new("RGB", (1200, 900), (255, 255, 255)); _D.Draw(_c).rectangle([200, 200, 900, 700], fill=(30, 30, 30))   # khác màu
_d = _I.new("RGB", (1200, 900), (255, 255, 255)); _D.Draw(_d).rectangle([500, 100, 700, 800], fill=(200, 20, 40))  # khác dáng
eq(_same_image(_image_signature(_a), _image_signature(_b)), True, "cùng hình khác kích thước → trùng")
eq(_same_image(_image_signature(_a), _image_signature(_c)), False, "khác màu → không trùng")
eq(_same_image(_image_signature(_a), _image_signature(_d)), False, "khác hình dáng → không trùng")
eq(_same_image(_image_signature(_a), _image_signature(_a.resize((900, 900)))), False, "khác tỉ lệ khung → không trùng")
_e = _I.new("RGB", (1200, 900), (255, 255, 255)); _D.Draw(_e).rectangle([200, 200, 900, 700], fill=(160, 20, 30))  # chỉ khác sắc đỏ
eq(_same_image(_image_signature(_a), _image_signature(_e)), False, "2 sản phẩm chỉ khác sắc đỏ → KHÔNG gộp nhầm")
import io as _io
_buf = _io.BytesIO(); _a.save(_buf, "JPEG", quality=40)
eq(_same_image(_image_signature(_a), _image_signature(_I.open(_io.BytesIO(_buf.getvalue())))), True, "cùng hình nén JPEG mạnh → vẫn nhận là trùng")

print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} LỖI")
sys.exit(1 if fails else 0)
