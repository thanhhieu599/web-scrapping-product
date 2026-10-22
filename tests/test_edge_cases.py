"""Kiểm thử TÌNH HUỐNG XẤU bằng trình duyệt thật + máy chủ giả lập cố tình gây lỗi.

    python tests/test_edge_cases.py
Biến môi trường DT_BROWSER (tuỳ chọn): đường dẫn trình duyệt Chromium muốn dùng.
"""
import functools
import http.server
import json
import os
import shutil
import socket
import struct
import sys
import tempfile
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from dt_importer import pipeline  # noqa: E402
import dt_importer.sapo as sapo_mod  # noqa: E402
from dt_importer.utils import load_config, read_json  # noqa: E402

SITE = HERE / "mock_site"
hits = {}


class Handler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):                                   # giả lập máy chủ Sapo nhận ảnh (~1 giây/ảnh)
        import time as _t
        n = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(n)
        _t.sleep(1.0)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *a):
        pass

    def _reset(self):
        # đóng kết nối kiểu RST → trình duyệt báo ERR_CONNECTION_RESET (giống lỗi trên máy khách)
        fmt = "HH" if sys.platform == "win32" else "ii"      # cấu trúc linger khác nhau giữa Windows/Linux
        self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack(fmt, 1, 0))
        self.connection.close()
        self.close_connection = True

    def do_GET(self):
        path = self.path.split("?")[0]
        hits[path] = hits.get(path, 0) + 1
        if path.startswith("/flaky/"):                       # 2 lần đầu bị cắt kết nối
            if hits[path] <= 2:
                return self._reset()
            self.path = self.path.replace("/flaky/", "/san-pham/", 1)
        if path.startswith("/admin2/products/create"):        # Sapo chưa đăng nhập → chuyển tới trang login
            if "logged=1" not in (self.headers.get("Cookie") or ""):
                self.send_response(302)
                self.send_header("Location", "/admin2/login.html")
                self.end_headers()
                return
            self.path = "/admin/products/create/index.html"
        if path.startswith("/admin3/products/create"):        # trang lỗi: không có form
            self.path = "/admin2/index.html"
        for prefix, flag in (("/admin4/products/create", "FAIL_FIRST_UPLOAD"), ("/admin5/products/create", "FAIL_ALWAYS")):
            if path.startswith(prefix):                         # Sapo làm mất lần tải ảnh đầu / không nhận ảnh
                html = (SITE / "admin/products/create/index.html").read_text(encoding="utf-8")
                html = html.replace("<head>", f"<head><script>window.{flag}=1</script>", 1).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html)))
                self.end_headers()
                self.wfile.write(html)
                return
        return super().do_GET()


PORT = 8790
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Handler, directory=str(SITE)))
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{PORT}"

tmp = Path(tempfile.mkdtemp())
cfg = load_config()
cfg.update(sapo_admin_url=f"{base}/admin", output_dir=str(tmp / "out"), profile_dir=str(tmp / "profile"),
           sapo_headless=True, delay_seconds=0)
if os.environ.get("DT_BROWSER"):
    cfg["browser_executable"] = os.environ["DT_BROWSER"]

saved = []
_orig_save = sapo_mod.SapoUploader._save


def _spy(self):
    url = _orig_save(self)
    self.page.wait_for_timeout(300)
    saved.append(json.loads(self.page.evaluate("sessionStorage.getItem('saved')")))
    return url


sapo_mod.SapoUploader._save = _spy
logs = []
log = lambda m: logs.append(str(m))
OPTS = {"product_type": "Hộp", "vendor": "Milwaukee", "collections": [], "tags": [],
        "auto_save": True, "dry_run": False, "force": True}
fails = 0


def check(cond, msg):
    global fails
    fails += not cond
    print(("  PASS " if cond else "  FAIL ") + msg)


def run(urls, cfg_=None, log_=log, **o):
    logs.clear()
    saved.clear()
    t = time.time()
    res = pipeline.run(urls, dict(OPTS, **o), cfg_ or cfg, log_, wait_user=lambda msg: logs.append("CHỜ: " + msg))
    return res, time.time() - t


print("=== 1. Mạng bị cắt (ERR_CONNECTION_RESET) 2 lần rồi mới vào được ===")
res, _ = run([f"{base}/flaky/hop-dung-dung-cu-8450.html"], dry_run=True)
check(any("thử lại" in l for l in logs), "Có thử lại khi bị cắt kết nối")
check(res and res[0]["status"] == "scraped", f"Vẫn lấy được sản phẩm sau khi thử lại ({res and res[0]['status']})")

print("=== 2. Sản phẩm 'Liên hệ' (không có giá) ===")
res, _ = run([f"{base}/san-pham/lien-he.html"])
check(res and res[0]["status"] == "created", f"Vẫn đăng được ({res and res[0]['status']})")
d = saved[0] if saved else {}
check(d.get("price") in ("0", ""), f"Ô Giá để nguyên (không điền bừa): {d.get('price')!r}")
check(d.get("sku") == "48-22-9999", "Có mã SP")

print("=== 3. Nhập Tên thuộc tính nhưng ô Quy cách không có mã → bỏ phiên bản, vẫn đăng ===")
res, _ = run([f"{base}/san-pham/khong-ma.html"], variant_attr="Model")
check(any("bỏ qua phần phiên bản" in l for l in logs), "Cảnh báo không xác định được mã phiên bản")
check(res and res[0]["status"] == "created", "Sản phẩm vẫn được lưu")
check(saved and saved[0].get("variants") == [] and saved[0].get("attr") == "", "Không tạo thuộc tính rỗng trên Sapo")

print("=== 4. 1 ảnh quy cách bị lỗi 404 ===")
res, _ = run([f"{base}/san-pham/anh-loi.html"])
check(any("Không tải được ảnh 1" in l for l in logs), "Báo rõ ảnh nào lỗi")
check(res and res[0]["status"] == "created", "Sản phẩm vẫn được lưu")
check(saved and len(saved[0].get("files", [])) == 1, f"Tải lên các ảnh còn lại ({saved and saved[0].get('files')})")

print("=== 5. Trang cuộn vô hạn ===")
res, secs = run([f"{base}/san-pham/vo-han.html"], dry_run=True)
check(res and res[0]["status"] == "scraped", "Lấy được dữ liệu")
check(secs < 60, f"Không bị treo ({secs:.0f} giây)")

print("=== 6. Không tự Lưu và người dùng KHÔNG bấm Lưu ===")
logs.clear(); saved.clear()
res = pipeline.run([f"{base}/san-pham/hop-dung-dung-cu-8424.html"], dict(OPTS, auto_save=False), cfg, log,
                   wait_user=lambda msg: None)
check(res and res[0]["status"] == "not_saved", f"Ghi nhận 'chưa lưu' ({res and res[0]['status']})")
hist = read_json(Path(cfg["output_dir"]) / "history.json", {})
check("48-22-8424" not in hist, "KHÔNG ghi vào lịch sử → lần sau vẫn đăng")

print("=== 7. Bấm Dừng giữa chừng (trang danh mục 2 sản phẩm) ===")
logs.clear(); saved.clear()
res = pipeline.run([f"{base}/san-pham/"], OPTS, cfg, log, stop_flag=lambda: len(saved) >= 1)
check(len(saved) == 1 and any("Đã dừng" in l for l in logs), f"Dừng sau sản phẩm đang làm ({len(saved)} đã lưu)")

print("=== 8. Chưa đăng nhập Sapo → chờ đăng nhập rồi tự tiếp tục ===")
cfg2 = dict(cfg, sapo_admin_url=f"{base}/admin2")
res, _ = run([f"{base}/san-pham/hop-dung-dung-cu-8425.html"], cfg_=cfg2)
check(any("Chưa đăng nhập" in l for l in logs) and any("Đã đăng nhập" in l for l in logs), "Phát hiện chưa đăng nhập và chờ")
check(res and res[0]["status"] == "created", f"Sau khi đăng nhập vẫn đăng được ({res and res[0]['status']})")

print("=== 9. Form Sapo không như mong đợi → báo lỗi rõ, không treo ===")
cfg3 = dict(cfg, sapo_admin_url=f"{base}/admin3")
sapo_mod.SapoUploader.ensure_login = lambda self: None          # bỏ bước chờ đăng nhập 10 phút
_orig_wait = sapo_mod.SapoUploader._wait_form
sapo_mod.SapoUploader._wait_form = lambda self, timeout=0: False
res, secs = run([f"{base}/san-pham/hop-dung-dung-cu-8450.html"], cfg_=cfg3)
sapo_mod.SapoUploader._wait_form = _orig_wait
check(res and res[0]["status"] == "error" and "Tên sản phẩm" in res[0].get("error", ""), f"Báo lỗi rõ ràng: {res and res[0].get('error')!r}")
check(list((Path(cfg["output_dir"]) / "logs").glob("loi-*.png")), "Có ảnh chụp màn hình lỗi trong output/logs")

print("=== 10. Sapo làm mất lần chọn ảnh đầu → KHÔNG gửi lại (tránh trùng ảnh), vẫn tự Lưu ===")
res, _ = run([f"{base}/san-pham/hop-dung-dung-cu-8425.html"], cfg_=dict(cfg, sapo_admin_url=f"{base}/admin4"))
check(not any("tải lên lại" in l for l in logs) and saved and saved[0].get("uploadCalls") == 1,
      f"Chỉ gửi ảnh 1 lần, không gửi lại ({saved and saved[0].get('uploadCalls')})")
check(res and res[0]["status"] == "created", "Vẫn tự Lưu và chạy tiếp")

print("=== 11. Sapo không nhận ảnh → KHÔNG dừng chờ, KHÔNG gửi lại, vẫn tự Lưu ===")
asked = []
logs.clear(); saved.clear()
res = pipeline.run([f"{base}/san-pham/hop-dung-dung-cu-8450.html"], OPTS, dict(cfg, sapo_admin_url=f"{base}/admin5"), log,
                   wait_user=lambda msg: asked.append(msg))
check(not asked, "Không dừng chờ người dùng")
check(saved and res and res[0]["status"] == "created" and saved[0].get("uploadCalls") == 1,
      f"Tự Lưu, chỉ gửi ảnh 1 lần ({res and res[0]['status']}, {saved and saved[0].get('uploadCalls')})")

print("=== 12. Trình duyệt Sapo bị đóng giữa chừng → tự mở lại và làm lại sản phẩm ===")
_orig_pick = sapo_mod.SapoUploader._pick_collections
_state = {"n": 0}
def _crash_once(self, names):
    if _state["n"] == 0:
        _state["n"] = 1
        self.ctx.close()                       # giống người dùng lỡ đóng cửa sổ Sapo
        self.page.wait_for_timeout(100)        # → TargetClosedError như log thật
    return _orig_pick(self, names)
sapo_mod.SapoUploader._pick_collections = _crash_once
res, _ = run([f"{base}/san-pham/hop-dung-dung-cu-8424.html", f"{base}/san-pham/hop-dung-dung-cu-8425.html"])
sapo_mod.SapoUploader._pick_collections = _orig_pick
check(any("mở lại" in l for l in logs), "Phát hiện trình duyệt bị đóng và mở lại")
check(res and [r["status"] for r in res] == ["created", "created"], f"Cả 2 sản phẩm vẫn được lưu ({[r['status'] for r in res]})")

srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} LỖI")
sys.exit(1 if fails else 0)
