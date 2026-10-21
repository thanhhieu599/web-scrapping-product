"""Kiểm thử end-to-end trên trang giả lập (không cần Internet).

    python tests/run_mock_test.py
"""
import functools
import http.server
import json
import shutil
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from playwright.sync_api import sync_playwright  # noqa: E402
from dt_importer import pipeline  # noqa: E402
from dt_importer.utils import load_config  # noqa: E402

PORT = 8765
class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


handler = functools.partial(Quiet, directory=str(HERE / "mock_site"))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{PORT}"

tmp = Path(tempfile.mkdtemp())
cfg = load_config()
cfg.update(sapo_admin_url=f"{base}/admin", output_dir=str(tmp / "out"), profile_dir=str(tmp / "profile"),
           sapo_headless=True, delay_seconds=0, category_map_file=str(tmp / "danh_muc.csv"))
import os  # noqa: E402
if os.environ.get("DT_BROWSER"):
    cfg["browser_executable"] = os.environ["DT_BROWSER"]

# Bắt dữ liệu form đã lưu từ trang đích giả lập
import dt_importer.sapo as sapo_mod  # noqa: E402
saved = []
orig_save = sapo_mod.SapoUploader._save
def spy_save(self):
    url = orig_save(self)
    self.page.wait_for_timeout(300)
    saved.append(json.loads(self.page.evaluate("sessionStorage.getItem('saved')")))
    return url
sapo_mod.SapoUploader._save = spy_save

opts = {"product_type": "Hộp đựng dụng cụ", "vendor": "Milwaukee", "collections": ["Lưu trữ dụng cụ"],
        "tags": ["packout"], "auto_save": True, "dry_run": False}
res = pipeline.run([f"{base}/san-pham/"], opts, cfg)

ok = True
def check(cond, msg):
    global ok
    print(("  PASS " if cond else "  FAIL ") + msg)
    ok &= bool(cond)

print("\n=== KIỂM TRA ===")
check(len(saved) == 2, f"Tạo 2 sản phẩm từ trang danh mục (thực tế {len(saved)})")
d = next((x for x in saved if x["sku"] == "48-22-8450"), {})
check(d.get("name") == "Hộp đựng dụng cụ Milwaukee 8450, 8424, 8425", f"Tên đúng + chèn nhà cung cấp trước mã: {d.get('name')!r}")
check(d.get("price", "").replace(".", "") == "2940000", f"Giá = {d.get('price')}")
check(d.get("vat") is True, "Tick 'Giá đã bao gồm VAT'")
check(d.get("visible") is True, "Trạng thái mặc định: Hiển thị")
check(d.get("ship") is True, "Tick 'Sản phẩm yêu cầu vận chuyển'")
check(d.get("weight") == "2580", f"Khối lượng 8450 = {d.get('weight')} g")
check(d.get("type") == "Hộp đựng dụng cụ" and d.get("vendor") == "Milwaukee", "Loại / Nhà cung cấp")
check(d.get("cols") == ["Lưu trữ dụng cụ"], f"Danh mục {d.get('cols')}")
check(len(d.get("files", [])) == 3, f"Ảnh quy cách: {d.get('files')}")
c = d.get("content", "")
check("Đặc điểm nổi bật" in c and "Bao gồm khay xốp" in c, "Có phần Đặc điểm")
check(d.get("short", "x") == "", "Ô Mô tả ngắn để trống (không điền nhầm Đặc điểm/Thông số)")
check("Thông số kỹ thuật" in c and "Khả năng chịu trọng lượng" in c, "Có bảng Thông số")
check("BAO GỒM TRONG SẢN PHẨM" not in c and "(1)" not in c, "KHÔNG lấy khối 'Bao gồm trong sản phẩm'")
img = tmp / "out" / "48-22-8450" / "images" / "01.jpg"
from PIL import Image  # noqa: E402
check(img.exists() and Image.open(img).size[0] == 800, "Ảnh tải về ở độ phân giải gốc (800px)")

# chạy lại → phải bỏ qua mã đã đăng
saved.clear()
pipeline.run([f"{base}/san-pham/hop-dung-dung-cu-8450.html"], opts, cfg)
check(len(saved) == 0, "Chạy lại: bỏ qua mã đã đăng")

# Trang kiểu Magento (giống milwaukeetool.com.vn): bảng thông số xếp bằng lưới <div>
print("\n=== TRANG KIỂU MAGENTO ===")
dry = dict(opts, dry_run=True, force=True)
pipeline.run([f"{base}/san-pham/magento-packout.html"], dry, cfg)
m = json.loads((tmp / "out" / "48-22-8425" / "product.json").read_text(encoding="utf-8"))
check(m["name"] == "Hộp đựng dụng cụ 8450, 8424, 8425", f"Magento: tên = {m['name']!r} (không lấy 'TÌM CỬA HÀNG')")
check(m["sku"] == "48-22-8425", f"Magento: mã = {m['sku']!r}")
check(m["price"] == 2820000, f"Magento: giá = {m['price']}")
check(m["found"]["spec_source"] == "layout", f"Magento: bảng dựng theo bố cục ({m['found']['spec_source']})")
check(m["spec"]["headers"] == ["48-22-8424", "48-22-8425", "48-22-8450"], f"Magento: tiêu đề cột {m['spec']['headers']}")
rows = {r.get("label"): r.get("values") for r in m["spec"]["rows"] if "label" in r}
check(rows.get("Chiều dài (mm)") == ["561", "561", "526"], f"Magento: Chiều dài {rows.get('Chiều dài (mm)')}")
check(rows.get("Khả năng chịu trọng lượng (kg)") == ["34", "45.3", "34"], "Magento: Khả năng chịu trọng lượng")
check({"section": "THÔNG SỐ KỸ THUẬT CỦA SẢN PHẨM"} in m["spec"]["rows"], "Magento: dòng tiêu đề nhóm")
check(not any("(1)" in str(r) or "BAO GỒM" in str(r) for r in m["spec"]["rows"]), "Magento: bỏ khối Bao gồm")
check(m["weight_g"] == 5500, f"Magento: khối lượng đúng cột 8425 = {m['weight_g']}")
check(len(m["image_files"]) == 3, f"Magento: 3 ảnh quy cách ({len(m['image_files'])})")
im = Image.open(m["image_files"][0])
check(im.size == (1200, 900), f"Magento: lấy ảnh gốc 1200x900 thay vì ảnh cache ({im.size})")
html = (tmp / "out" / "48-22-8425" / "noi_dung.html").read_text(encoding="utf-8")
check("<table" in html and "<p>561</p>" not in html, "Magento: nội dung ra BẢNG, không ra từng dòng rời")
check((tmp / "out" / "48-22-8425" / "trang_goc.html").exists(), "Lưu trang_goc.html để chẩn đoán")

# Phiên bản: ô quy cách là link sang trang khác (trang 1)
print("\n=== PHIÊN BẢN – Ô QUY CÁCH LÀ LINK ===")
pipeline.run([f"{base}/san-pham/hop-dung-dung-cu-8450.html"], dict(dry, variant_attr="Model"), cfg)
pj = json.loads((tmp / "out" / "48-22-8450" / "product.json").read_text(encoding="utf-8"))
vv = [(v["value"], v["price"]) for v in pj["variants"]]
check(vv == [("48-22-8424", 3120000), ("48-22-8425", 2820000), ("48-22-8450", 2940000)], f"Link: phiên bản {vv}")

# Phiên bản trên Magento + đăng lên Sapo (thuộc tính, giá/SKU/ảnh từng phiên bản)
print("\n=== PHIÊN BẢN MAGENTO → SAPO ===")
saved.clear()
pipeline.run([f"{base}/san-pham/magento-packout.html"], dict(opts, force=True, variant_attr="Model", visible=False), cfg)
check(len(saved) == 1, "Magento→Sapo: đã lưu 1 sản phẩm")
d = saved[0] if saved else {}
check(d.get("name") == "Hộp đựng dụng cụ Milwaukee 8450, 8424, 8425", f"Magento→Sapo: tên {d.get('name')!r}")
check(d.get("visible") is False, "Trạng thái: Ẩn khi chọn Ẩn")
check(d.get("attr") == "Model", f"Magento→Sapo: tên thuộc tính {d.get('attr')!r}")
vs = d.get("variants", [])
check([v["value"] for v in vs] == ["48-22-8424", "48-22-8425", "48-22-8450"], f"Magento→Sapo: giá trị {[v['value'] for v in vs]}")
check([v["price"].replace(".", "") for v in vs] == ["2700000", "2820000", "2940000"], f"Magento→Sapo: giá từng phiên bản {[v['price'] for v in vs]}")
check([v["sku"] for v in vs] == ["48-22-8424", "48-22-8425", "48-22-8450"], f"Magento→Sapo: SKU từng phiên bản {[v['sku'] for v in vs]}")
check([v["image"] for v in vs] == [0, 1, 2], f"Magento→Sapo: ảnh đúng từng phiên bản {[v['image'] for v in vs]}")
c = d.get("content", "")
check(c.count("<img") >= 4 and "/media/catalog/product/4/8/48-22-8424-hero01.png" in c and "/img/p5.jpg" in c,
      "Mô tả có ảnh: hàng ảnh trong bảng Thông số + ảnh trong Đặc điểm")

srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if ok else "CÓ LỖI")
sys.exit(0 if ok else 1)
