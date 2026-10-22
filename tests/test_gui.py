"""Kiểm thử GIAO DIỆN: tự điền ô, tick "Chỉ cào thử", bấm "Chạy" và chờ kết quả trong khung log.

    python tests/test_gui.py          (cần màn hình; trên Linux không màn hình: xvfb-run python tests/test_gui.py)
Biến môi trường: DT_BROWSER (tuỳ chọn), DT_GUI_SHOT (đường dẫn lưu ảnh chụp giao diện, tuỳ chọn).
"""
import functools
import http.server
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import tkinter as tk
from tkinter import scrolledtext, ttk
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
import main  # noqa: E402


class Q(http.server.SimpleHTTPRequestHandler):
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


PORT = 8795
srv = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), functools.partial(Q, directory=str(HERE / "mock_site")))
threading.Thread(target=srv.serve_forever, daemon=True).start()

tmp = Path(tempfile.mkdtemp())
cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
cfg.update(output_dir=str(tmp / "out"), profile_dir=str(tmp / "profile"), delay_seconds=0)
if os.environ.get("DT_BROWSER"):
    cfg["browser_executable"] = os.environ["DT_BROWSER"]
cfg_path = tmp / "config.json"
cfg_path.write_text(json.dumps(cfg, ensure_ascii=False), encoding="utf-8")
state_backup = main.STATE_FILE.read_bytes() if main.STATE_FILE.exists() else None

result = {"ok": False, "log": "", "msg": ""}


def widgets(w, kind):
    out = []
    for c in w.winfo_children():
        if isinstance(c, kind):
            out.append(c)
        out += widgets(c, kind)
    return out


def driver(root):
    texts = widgets(root, scrolledtext.ScrolledText)
    entries = [e for e in widgets(root, ttk.Entry) if not isinstance(e, ttk.Combobox)]
    urls, logbox = texts[0], texts[1]
    combos = widgets(root, ttk.Combobox)
    checks = {c.cget("text"): c for c in widgets(root, ttk.Checkbutton)}
    buttons = {c.cget("text"): c for c in widgets(root, ttk.Button)}
    # thứ tự ô: Sapo, Loại, Nhà cung cấp, Tên thuộc tính, Danh mục, Tags
    result["fields"] = len(entries)
    urls.delete("1.0", "end")
    urls.insert("1.0", f"http://127.0.0.1:{PORT}/san-pham/magento-packout.html\n")
    for e, v in zip(entries[1:4], ["Hộp đựng dụng cụ", "Milwaukee", "Model"]):
        e.delete(0, "end")
        e.insert(0, v)
    result["status_values"] = list(combos[0].cget("values")) if combos else []
    checks["Chỉ cào thử (không đăng)"].invoke()
    buttons["▶ Chạy"].invoke()
    start = time.time()

    def poll():
        txt = logbox.get("1.0", "end")
        if "Hoàn tất" in txt or time.time() - start > 240:
            result["log"] = txt
            result["ok"] = "Hoàn tất: 1 thành công" in txt
            shot = os.environ.get("DT_GUI_SHOT")
            if shot:
                try:
                    from PIL import ImageGrab
                    root.update()
                    x, y = root.winfo_rootx(), root.winfo_rooty()
                    ImageGrab.grab(bbox=(x, y, x + root.winfo_width(), y + root.winfo_height()),
                                   xdisplay=os.environ.get("DISPLAY")).save(shot)
                except Exception as ex:      # ảnh chụp chỉ để xem, không bắt buộc
                    result["msg"] = f"không chụp được ảnh: {ex}"
            root.after(300, root.destroy)
        else:
            root.after(500, poll)

    root.after(500, poll)


_orig = tk.Tk.mainloop


def _patched(self, n=0):
    self.after(800, lambda: driver(self))
    _orig(self, n)


tk.Tk.mainloop = _patched
try:
    main.gui(str(cfg_path))
finally:
    srv.shutdown()
    if state_backup is None:
        main.STATE_FILE.unlink(missing_ok=True)
    else:
        main.STATE_FILE.write_bytes(state_backup)

fails = 0


def check(cond, msg):
    global fails
    fails += not cond
    print(("  PASS " if cond else "  FAIL ") + msg)


log = result["log"]
check(result.get("fields") == 6, f"Đủ 6 ô nhập (Sapo, Loại, NCC, Thuộc tính, Danh mục, Tags): {result.get('fields')}")
check(result.get("status_values") == ["Hiển thị", "Ẩn"], f"Ô Trạng thái có Hiển thị/Ẩn: {result.get('status_values')}")
check(result["ok"], "Bấm Chạy → hoàn tất 1 sản phẩm")
check("Phiên bản: 3" in log, "Đọc được 3 phiên bản từ giao diện")
check("Đã lưu bản nháp" in log, "Chế độ Chỉ cào thử: lưu bản nháp, không đăng Sapo")
pj = tmp / "out" / "48-22-8425" / "product.json"
check(pj.exists() and json.loads(pj.read_text(encoding="utf-8"))["title"] == "Hộp đựng dụng cụ Milwaukee 8450, 8424, 8425",
      "Tên đã chèn nhà cung cấp")
if result["msg"]:
    print("  (ghi chú)", result["msg"])
shutil.rmtree(tmp, ignore_errors=True)
print("\nKẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} LỖI")
if fails:
    print(log[-2000:])
sys.exit(1 if fails else 0)
