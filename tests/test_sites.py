"""Kiểm thử kiến trúc mở rộng theo nhà cung cấp (sites.json + bộ đọc theo nền tảng).

    python tests/test_sites.py
- Magento: Quy cách dạng DANH SÁCH CHỌN (không có ô để bấm) → đọc phiên bản từ dữ liệu cấu hình.
- WooCommerce (kiểu delivietnam.com.vn): trang danh mục nhiều trang → đủ sản phẩm, giá khuyến mãi,
  mô tả gốc đã làm sạch, bảng thuộc tính, phiên bản màu sắc, sản phẩm Liên hệ, NCC/Loại mặc định.
"""
import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from dt_importer import pipeline  # noqa: E402
from dt_importer.content import clean_description  # noqa: E402
from dt_importer.sites import load_sites, merged_cfg, profile_for  # noqa: E402
from dt_importer.utils import load_config  # noqa: E402


class Q(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):                                   # giả lập máy chủ Sapo nhận ảnh
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass


PORT = 8775
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Q, directory=str(HERE / "mock_site")))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{PORT}"

fails = 0


def check(cond, msg):
    global fails
    fails += not cond
    print(("  PASS " if cond else "  FAIL ") + msg)


print("=== Danh bạ nhà cung cấp (sites.json) ===")
sites = load_sites()
check(profile_for("https://delivietnam.com.vn/danh-muc-san-pham/van-phong-pham", sites).get("platform") == "woocommerce",
      "delivietnam.com.vn → WooCommerce")
check(profile_for("https://www.delivietnam.com.vn/san-pham/x/", sites).get("vendor") == "Deli", "www.* vẫn khớp, NCC mặc định Deli")
check(profile_for("https://milwaukeetool.com.vn/x.html", sites).get("platform") == "magento", "milwaukeetool.com.vn → Magento")
p = profile_for("https://web-moi.vn/a", sites)
check(p["platform"] == "auto" and p["name"] == "web-moi.vn", "web chưa khai báo → tự nhận nền tảng")
mc = merged_cfg({"listing_max_pages": 10, "source_selectors": {"name": ""}},
                {"listing_max_pages": 60, "selectors": {"name": "h1.x"}})
check(mc["listing_max_pages"] == 60 and mc["source_selectors"]["name"] == "h1.x", "hồ sơ NCC ghi đè config.json")

print("=== Làm sạch mô tả gốc ===")
c = clean_description('<p style="color:red" onclick="x()">A <b>B</b></p><script>bad()</script><img src="/i.jpg" onerror="x">'
                      '<a href="javascript:x">L</a><iframe src="y"></iframe><div><span></span></div>', "https://a.vn/p/")
check("script" not in c and "bad()" not in c and "onclick" not in c and "onerror" not in c and "iframe" not in c,
      "bỏ script / sự kiện / iframe")
check('src="https://a.vn/i.jpg"' in c and "color:red" not in c and "<b>B</b>" in c and c.endswith("L"), "ảnh link tuyệt đối, bỏ màu gốc, giữ chữ")

tmp = Path(tempfile.mkdtemp())
cfg = load_config()
cfg.update(sapo_admin_url=f"{base}/admin", output_dir=str(tmp / "out"), profile_dir=str(tmp / "profile"),
           sapo_headless=True, delay_seconds=0)
if os.environ.get("DT_BROWSER"):
    cfg["browser_executable"] = os.environ["DT_BROWSER"]

import dt_importer.sapo as sapo_mod  # noqa: E402
saved = []
orig_save = sapo_mod.SapoUploader._save


def spy_save(self):
    url = orig_save(self)
    self.page.wait_for_timeout(300)
    saved.append(json.loads(self.page.evaluate("sessionStorage.getItem('saved')")))
    return url


sapo_mod.SapoUploader._save = spy_save
logs = []
log = lambda m: (logs.append(m), print(m))

try:
    print("\n=== MAGENTO: QUY CÁCH DẠNG DANH SÁCH CHỌN ===")
    opts = {"product_type": "Sạc pin", "vendor": "Milwaukee", "collections": [], "tags": [], "auto_save": True,
            "dry_run": False, "force": True, "variant_attr": "Model"}
    pipeline.run([f"{base}/san-pham/sac-c12c.html"], opts, cfg, log)
    d = saved[0] if saved else {}
    vs = d.get("variants", [])
    check([v["value"] for v in vs] == ["C12C", "M12-18C", "M12-18FC"], f"3 phiên bản từ dữ liệu Magento {[v['value'] for v in vs]}")
    check([v["price"].replace(".", "") for v in vs] == ["1030000", "1450000", "2390000"], f"giá từng phiên bản {[v['price'] for v in vs]}")
    check(len(d.get("files", [])) == 3 and [v["image"] for v in vs] == [0, 1, 2],
          f"3 ảnh, gán đúng từng phiên bản ({d.get('files')}, {[v['image'] for v in vs]})")
    check(d.get("uploadCalls", 1) == 1, f"ảnh chỉ đăng 1 lần ({d.get('uploadCalls')})")

    logs.clear()
    pipeline.run([f"{base}/san-pham/sac-khong-du-lieu.html"], dict(opts, dry_run=True), cfg, log)
    check(any("không đọc được ô Quy cách" in m for m in logs), "nhiều model nhưng không có dữ liệu → cảnh báo rõ trong log")

    print("\n=== WOOCOMMERCE (kiểu Deli) – tự nhận nền tảng, chưa khai báo sites.json ===")
    dry = {"product_type": "", "vendor": "", "collections": [], "tags": [], "auto_save": True, "dry_run": True,
           "force": True, "variant_attr": "Màu sắc"}
    logs.clear()
    res = pipeline.run([f"{base}/woo/danh-muc-san-pham/van-phong-pham/"], dry, cfg, log)
    got = sorted(r.get("sku") or "" for r in res if r["status"] == "scraped")
    check(len(got) == 4, f"danh mục 2 trang → 4 sản phẩm ({got}; {[r['status'] for r in res]})")
    check(not any("so-tay-deli-a5" in r["url"] and r.get("sku") == "N/A" for r in res), "mã 'N/A' không dùng làm SKU")
    pj = json.loads((tmp / "out" / "q01" / "product.json").read_text(encoding="utf-8"))
    check(pj["platform"] == "woocommerce", f"tự nhận WooCommerce ({pj['platform']})")
    check(pj["name"] == "Bút bi Deli Q01 0.7mm" and pj["price"] == 4500, f"tên + giá khuyến mãi ({pj['name']}, {pj['price']})")
    check(len(pj["image_files"]) == 2, f"2 ảnh gallery gốc ({pj['image_files']})")
    from PIL import Image  # noqa: E402
    check(all(Image.open(f).size == (1000, 1000) for f in pj["image_files"]), "ảnh lấy bản gốc 1000px (không lấy ảnh thu nhỏ)")
    rows = {r["label"]: r["values"] for r in pj["spec"]["rows"]}
    check(rows.get("Quy cách đóng gói") == ["Hộp 12 cây"], f"bảng Thông tin bổ sung → Thông số ({rows})")
    mt = json.loads((tmp / "out" / "1238" / "product.json").read_text(encoding="utf-8"))
    mv = [(v["value"], v["sku"], v["price"]) for v in mt["variants"]]
    check(mv == [("Đen", "1238-DEN", 245000), ("Trắng", "1238-TRANG", 255000), ("Xanh lá", "1238-XANH", 265000)],
          f"phiên bản màu sắc (tên màu, mã, giá) {mv}")
    check(len(mt["image_files"]) == 4, f"ảnh 3 màu + ảnh chính ({len(mt['image_files'])})")
    gh = json.loads((tmp / "out" / "0012" / "product.json").read_text(encoding="utf-8"))
    check(gh["price"] is None, "sản phẩm Liên hệ: không có giá, vẫn lấy")

    print("\n=== WOOCOMMERCE + HỒ SƠ NHÀ CUNG CẤP → SAPO ===")
    sf = tmp / "sites.json"
    sf.write_text(json.dumps({"127.0.0.1": {"name": "Deli (test)", "platform": "woocommerce", "vendor": "Deli",
                                            "product_type": "Văn phòng phẩm", "content": "description"}},
                             ensure_ascii=False), encoding="utf-8")
    cfg2 = dict(cfg, sites_file=str(sf))
    saved.clear()
    pipeline.run([f"{base}/woo/san-pham/but-bi-deli-q01/", f"{base}/woo/san-pham/may-tinh-deli-1238/"],
                 dict(dry, dry_run=False), cfg2, log)
    check(len(saved) == 2, f"đã lưu 2 sản phẩm lên Sapo ({len(saved)})")
    b = next((x for x in saved if x.get("sku") == "Q01"), {})
    check(b.get("vendor") == "Deli" and b.get("type") == "Văn phòng phẩm", f"NCC/Loại lấy từ hồ sơ khi ô để trống ({b.get('vendor')}, {b.get('type')})")
    check(b.get("name") == "Bút bi Deli Q01 0.7mm", f"tên đã có Deli → không chèn lặp ({b.get('name')})")
    check(b.get("price", "").replace(".", "") == "4500", f"giá {b.get('price')}")
    c = b.get("content", "")
    check("viết êm" in c and "Mực ra đều" in c and "Thông số kỹ thuật" in c, "Nội dung = mô tả gốc + bảng thuộc tính")
    check("<script" not in c and "onclick" not in c and "onerror" not in c and "iframe" not in c and "color:red" not in c
          and "javascript:" not in c, "mô tả đã làm sạch (không mã độc, không màu đỏ)")
    check("desc-q01-600x600.jpg" in c and ">Mô tả<" not in c, "giữ ảnh trong mô tả, bỏ tiêu đề 'Mô tả' thừa")
    check(b.get("short", "x") == "", "Mô tả ngắn để trống")
    m = next((x for x in saved if x.get("sku") == "1238"), {})
    check(m.get("attr") == "Màu sắc" and [v["value"] for v in m.get("variants", [])] == ["Đen", "Trắng", "Xanh lá"],
          f"phiên bản WooCommerce lên Sapo ({m.get('attr')}, {[v['value'] for v in m.get('variants', [])]})")
    check([v["image"] for v in m.get("variants", [])] == [0, 1, 2], f"ảnh từng màu ({[v['image'] for v in m.get('variants', [])]})")
    check(len(m.get("files", [])) == 4, f"4 ảnh lên Sapo ({len(m.get('files', []))})")

    print("\n=== DELI THẬT (theme Flatsome) – dùng đúng cấu hình delivietnam.com.vn trong sites.json ===")
    deli = dict(load_sites()["delivietnam.com.vn"], name="Deli (test)")
    sf2 = tmp / "sites_deli.json"
    sf2.write_text(json.dumps({"127.0.0.1": deli}, ensure_ascii=False), encoding="utf-8")
    cfg3 = dict(cfg, sites_file=str(sf2))
    blank = {"product_type": "", "vendor": "", "collections": [], "tags": [], "auto_save": True, "dry_run": False,
             "force": True, "variant_attr": ""}           # để trống hết → lấy theo hồ sơ Deli
    saved.clear()
    logs.clear()
    res = pipeline.run([f"{base}/deli/danh-muc-san-pham/van-phong-pham/"], blank, cfg3, log)
    check(len(saved) == 3, f"danh mục Flatsome 2 trang → đăng đủ 3 sản phẩm ({len(saved)}; {[r['status'] for r in res]})")
    e = next((x for x in saved if x.get("sku") == "E6600S"), {})
    check(e.get("name") == "Bút Gel siêu trơn Deli E6600S", f"tên cắt tại dấu '–' ({e.get('name')!r})")
    check(e.get("vendor") == "Deli" and e.get("type") == "Văn phòng phẩm", "NCC Deli, Loại Văn phòng phẩm")
    check(e.get("price", "") in ("", "0"), f"sản phẩm LIÊN HỆ: không điền giá ({e.get('price')!r})")
    check(len(e.get("files", [])) == 2, f"lấy đủ 2 ảnh gallery (kể cả ảnh tải chậm) ({e.get('files')})")
    ec = e.get("content", "")
    check("1. MÔ TẢ SẢN PHẨM" in ec and "giải pháp tuyệt vời" in ec and "2. THÔNG SỐ KỸ THUẬT" in ec
          and "Màu mực: Xanh dương" in ec and "Quy cách: Thiết kế hiện đại" in ec, "lấy TOÀN BỘ phần Mô tả")
    check("<img" not in ec, "mô tả KHÔNG lấy hình ảnh")
    check("Thông số kỹ thuật</h2>" not in ec and "Nét bút mượt mà" not in ec, "không chèn thêm bảng / mô tả ngắn")
    check(e.get("variants") == [] or not e.get("variants"), "SP 1 màu: không tạo thuộc tính")
    g = next((x for x in saved if x.get("sku") == "EG057"), {})
    check(g.get("name") == "Bút gel bấm siêu trơn Deli EG575", f"EG575: tên ({g.get('name')!r})")
    check(g.get("attr") == "Màu sắc", f"EG575: thuộc tính 'Màu sắc' tự lấy theo hồ sơ ({g.get('attr')!r})")
    gv = [(v["value"], v["sku"]) for v in g.get("variants", [])]
    check(gv == [("Đen", "EG057-DEN"), ("Xanh", "EG057-XANH")], f"EG575: phiên bản Đen, Xanh từ ô màu ({gv})")
    check(len(g.get("files", [])) == 3, f"EG575: 3 ảnh gallery ({len(g.get('files', []))})")
    b1 = next((x for x in saved if x.get("sku") == "S01"), {})
    bv = [v["value"] for v in b1.get("variants", [])]
    check(bv == ["Đỏ", "Xanh", "Đen"], f"chỉ có dòng chữ 'Màu sắc: Đỏ, Xanh, Đen' → vẫn tạo thuộc tính ({bv})")
finally:
    srv.shutdown()
    shutil.rmtree(tmp, ignore_errors=True)

print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} LỖI")
sys.exit(1 if fails else 0)
