"""Kiểm thử GÁN DANH MỤC nhiều cấp: breadcrumb nguồn → bảng ghép danh_muc.csv → danh mục Sapo.

    python tests/test_categories.py
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
sys.path.insert(0, str(HERE.parent))

from dt_importer import pipeline  # noqa: E402
import dt_importer.sapo as sapo_mod  # noqa: E402
from dt_importer.categories import CategoryMap, resolve  # noqa: E402
from dt_importer.utils import load_config  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    fails += not cond
    print(("  PASS " if cond else "  FAIL ") + msg)


tmp = Path(tempfile.mkdtemp())

print("=== Bảng ghép (không cần trình duyệt) ===")
f = tmp / "map1.csv"
f.write_text("Danh mục nguồn;Danh mục Sapo\n"                    # Excel lưu bằng dấu ;
             "dung cu cam tay > KIM;Dụng cụ cầm tay, Kìm, Bộ dụng cụ\n"
             "Tin tức;-\n", encoding="utf-8-sig")
m = CategoryMap(f)
names, how = resolve(["Dụng cụ cầm tay", "Kìm", "Kìm cắt"], m)
check(names == ["Dụng cụ cầm tay", "Kìm", "Bộ dụng cụ"], f"Cấp con dùng dòng của cấp cha, không phân biệt dấu/hoa: {names}")
names, _ = resolve(["Tin tức", "Khuyến mãi"], m)
check(names == [], "Dòng '-' = không gán danh mục")
names, how = resolve(["Bảo hộ lao động", "Găng tay"], m)
check(names == ["Bảo hộ lao động", "Găng tay"] and "tự động" in how, "Chưa có trong bảng → tự gán theo tên từng cấp")
names, _ = resolve(["Bảo hộ lao động", "Găng tay"], m, auto_levels=False)
check(names == [], "Tắt tự gán → không gán")
m.save()
txt = f.read_text(encoding="utf-8-sig")
check("Bảo hộ lao động > Găng tay," in txt and "Bộ dụng cụ" in txt, "Ghi thêm đường dẫn mới vào bảng, giữ dòng cũ")
check(f.read_bytes().startswith(b"\xef\xbb\xbf"), "File có BOM → Excel hiển thị đúng tiếng Việt")

print("\n=== Toàn bộ quy trình với trình duyệt ===")


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


PORT = 8797
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Q, directory=str(HERE / "mock_site")))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{PORT}"
cfg = load_config()
cfg.update(sapo_admin_url=f"{base}/admin", output_dir=str(tmp / "out"), profile_dir=str(tmp / "profile"),
           sapo_headless=True, delay_seconds=0, category_map_file=str(tmp / "danh_muc.csv"))
if os.environ.get("DT_BROWSER"):
    cfg["browser_executable"] = os.environ["DT_BROWSER"]

saved = []
_orig = sapo_mod.SapoUploader._save


def _spy(self):
    url = _orig(self)
    self.page.wait_for_timeout(300)
    saved.append(json.loads(self.page.evaluate("sessionStorage.getItem('saved')")))
    return url


sapo_mod.SapoUploader._save = _spy
OPTS = {"product_type": "Bộ dụng cụ", "vendor": "IRWIN", "collections": [], "tags": [],
        "auto_save": True, "dry_run": False, "force": True}
logs = []
by_sku = lambda: {d["sku"]: sorted(d["cols"]) for d in saved}

print("--- A. Chưa có bảng ghép: tự gán theo tên từng cấp ---")
pipeline.run([f"{base}/kim/"], OPTS, cfg, logs.append)
r = by_sku()
check(r.get("10505501") == sorted(["Dụng cụ cầm tay", "Kìm", "Kìm cắt"]),
      f"Kìm cắt (breadcrumb trên trang SP): {r.get('10505501')}")
check(r.get("10505502") == sorted(["Dụng cụ cầm tay", "Kìm"]),
      f"Kìm mũi nhọn (trang SP không có breadcrumb → lấy theo trang danh mục): {r.get('10505502')}")
csvtxt = (tmp / "danh_muc.csv").read_text(encoding="utf-8-sig")
check("Dụng cụ cầm tay > Kìm > Kìm cắt" in csvtxt and "Dụng cụ cầm tay > Kìm," in csvtxt,
      "Tự tạo danh_muc.csv với các đường dẫn đã gặp")
check(any("danh mục nguồn mới" in l for l in logs), "Báo người dùng điền bảng ghép")

print("--- B. Người dùng điền bảng ghép ---")
(tmp / "danh_muc.csv").write_text("Danh mục nguồn,Danh mục Sapo\n"
                                  "Dụng cụ cầm tay > Kìm,\"Dụng cụ cầm tay, Kìm, Bộ dụng cụ\"\n", encoding="utf-8-sig")
saved.clear()
pipeline.run([f"{base}/kim/"], OPTS, cfg, logs.append)
r = by_sku()
check(r.get("10505501") == sorted(["Dụng cụ cầm tay", "Kìm", "Bộ dụng cụ"]), f"Theo bảng (cấp cha): {r.get('10505501')}")
check(r.get("10505502") == sorted(["Dụng cụ cầm tay", "Kìm", "Bộ dụng cụ"]), f"Theo bảng: {r.get('10505502')}")

print("--- C. Gán riêng theo dòng 'link | danh mục' + ô Danh mục chung ---")
saved.clear()
pipeline.run([f"{base}/kim/kim-cat.html | Kìm cắt"], dict(OPTS, collections=["PPE"]), dict(cfg, category_auto=False), logs.append)
r = by_sku()
check(r.get("10505501") == sorted(["PPE", "Kìm cắt", "Dụng cụ cầm tay", "Kìm", "Bộ dụng cụ"]),
      f"Gộp: ô chung + dòng link + bảng ghép, không trùng: {r.get('10505501')}")
pj = json.loads((tmp / "out" / "10505501" / "product.json").read_text(encoding="utf-8"))
check(pj.get("category_path") == ["Dụng cụ cầm tay", "Kìm", "Kìm cắt"], f"Lưu đường dẫn nguồn vào product.json: {pj.get('category_path')}")

srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} LỖI")
sys.exit(1 if fails else 0)
