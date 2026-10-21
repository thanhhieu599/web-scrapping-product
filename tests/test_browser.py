"""Kiểm thử TRÌNH DUYỆT: mở Edge/Chrome CÓ CỬA SỔ (như khi đăng Sapo) và kiểm tra
- không còn cờ --no-sandbox (gây cảnh báo "unsupported command-line flag") và --enable-automation
- hộp cát bảo mật (sandbox) được bật
- vẫn điều khiển được trang (gõ chữ, đọc lại)
Chụp ảnh toàn màn hình vào tests/artifacts/ để xem có còn thanh cảnh báo nào không.

    python tests/test_browser.py
"""
import functools
import http.server
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from playwright.sync_api import sync_playwright  # noqa: E402
from dt_importer.browser import launch  # noqa: E402

fails = 0


def check(cond, msg):
    global fails
    fails += not cond
    print(("  PASS " if cond else "  FAIL ") + msg)


class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


PORT = 8799
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Q, directory=str(HERE / "mock_site")))
threading.Thread(target=srv.serve_forever, daemon=True).start()

art = HERE / "artifacts"
art.mkdir(exist_ok=True)
tmp = Path(tempfile.mkdtemp())
cfg = {"browser_channel": "auto"}
if os.environ.get("DT_BROWSER"):
    cfg["browser_executable"] = os.environ["DT_BROWSER"]
is_root_linux = sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0
headless = not (sys.platform == "win32" or os.environ.get("DISPLAY"))
logs = []

with sync_playwright() as pw:
    ctx = launch(pw, cfg, logs.append, headless=headless, profile_dir=str(tmp / "profile"),
                 viewport={"width": 1280, "height": 800}, locale="vi-VN")
    print("  " + " ".join(logs).strip())
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    page.goto("chrome://version")
    flags = page.inner_text("body")
    if is_root_linux:
        print("  (Linux chạy bằng root: trình duyệt không cho bật hộp cát – bỏ qua kiểm tra cờ sandbox)")
    else:
        check("--no-sandbox" not in flags, "Không còn cờ --no-sandbox (hết cảnh báo 'unsupported command-line flag')")
        check("hộp cát" not in " ".join(logs), "Hộp cát bảo mật được bật")
    check("--enable-automation" not in flags, "Không còn cờ --enable-automation (hết thanh 'đang bị điều khiển tự động')")
    if not headless:
        # các cờ Chrome/Edge cảnh báo "unsupported command-line flag" (danh sách bad flags của Chromium)
        BAD = ["--disable-blink-features", "--disable-web-security", "--single-process", "--ignore-certificate-errors",
               "--disable-site-isolation-trials", "--disable-gpu-sandbox", "--disable-seccomp-filter-sandbox"]
        found = [b for b in BAD if b in flags]
        check(not found, f"Cửa sổ hiển thị không có cờ gây cảnh báo: {found or 'không có'}")

    page.goto(f"http://127.0.0.1:{PORT}/admin/products/create/")
    page.fill('input[placeholder="Nhập tên sản phẩm"]', "Kiểm thử trình duyệt")
    check(page.input_value('input[placeholder="Nhập tên sản phẩm"]') == "Kiểm thử trình duyệt", "Vẫn điều khiển được trang (gõ chữ)")

    if not headless:
        page.bring_to_front()
        page.wait_for_timeout(2500)
        try:
            from PIL import ImageGrab
            ImageGrab.grab(xdisplay=os.environ.get("DISPLAY") if sys.platform != "win32" else None).save(art / "man_hinh_trinh_duyet.png")
            print(f"  (đã chụp màn hình: {art / 'man_hinh_trinh_duyet.png'})")
        except Exception as e:
            print(f"  (không chụp được màn hình: {e})")
    ctx.close()

srv.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} LỖI")
sys.exit(1 if fails else 0)
