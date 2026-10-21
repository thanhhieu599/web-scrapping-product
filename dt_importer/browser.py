"""Mở trình duyệt + truy cập trang có thử lại và chẩn đoán lỗi mạng.

Thứ tự ưu tiên (browser_channel = "auto"):
  Microsoft Edge (có sẵn trên mọi Windows 10/11) → Google Chrome → Chromium đóng gói kèm.
Edge/Chrome thật được phần mềm diệt virus, tường lửa, proxy công ty tin cậy, nên ít bị
cắt kết nối (ERR_CONNECTION_RESET) hơn Chromium đóng gói kèm.
"""
import time
import urllib.error
import urllib.request
from pathlib import Path

ARGS = ["--disable-quic", "--disable-blink-features=AutomationControlled", "--no-first-run",
        "--no-default-browser-check"]
NET_ERRORS = ("ERR_CONNECTION_RESET", "ERR_CONNECTION_CLOSED", "ERR_CONNECTION_REFUSED",
              "ERR_CONNECTION_TIMED_OUT", "ERR_TIMED_OUT", "ERR_NETWORK_CHANGED",
              "ERR_EMPTY_RESPONSE", "ERR_SSL_PROTOCOL_ERROR", "ERR_PROXY_CONNECTION_FAILED",
              "ERR_TUNNEL_CONNECTION_FAILED", "ERR_NAME_NOT_RESOLVED", "ERR_INTERNET_DISCONNECTED",
              "ERR_CERT_AUTHORITY_INVALID", "ERR_HTTP2_PROTOCOL_ERROR")
LABEL = {"msedge": "Microsoft Edge", "chrome": "Google Chrome", "": "Chromium (đóng gói kèm)"}


def _candidates(cfg):
    if cfg.get("browser_executable"):
        return [("exe", {"executable_path": cfg["browser_executable"]})]
    ch = (cfg.get("browser_channel") or "auto").strip().lower()
    if ch in ("", "bundled", "chromium"):
        return [("", {})]
    if ch == "auto":
        return [("msedge", {"channel": "msedge"}), ("chrome", {"channel": "chrome"}), ("", {})]
    return [(ch, {"channel": ch}), ("", {})]


def launch(pw, cfg, log=print, headless=True, profile_dir=None, **extra):
    """Trả về Browser (profile_dir=None) hoặc BrowserContext lưu phiên (profile_dir)."""
    errors = []
    for name, kw in _candidates(cfg):
        opts = dict(headless=headless, args=ARGS, **kw)
        try:
            if profile_dir:
                # mỗi loại trình duyệt 1 hồ sơ riêng (hồ sơ Edge/Chrome/Chromium không dùng chung được)
                path = str(Path(profile_dir) / (name or "chromium"))
                obj = pw.chromium.launch_persistent_context(path, **opts, **extra)
            else:
                obj = pw.chromium.launch(**opts)
            log(f"  (trình duyệt: {LABEL.get(name, kw.get('executable_path', name))})")
            return obj
        except Exception as e:
            errors.append(f"{LABEL.get(name, name)}: {str(e).splitlines()[0]}")
    raise RuntimeError("Không mở được trình duyệt nào:\n  " + "\n  ".join(errors))


def is_net_error(exc):
    return any(code in str(exc) for code in NET_ERRORS)


def goto(page, url, log=print, retries=3, timeout=60000):
    """page.goto có thử lại khi lỗi mạng; hết lượt thì chẩn đoán và báo cách xử lý."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            return page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        except Exception as e:
            last = e
            if not is_net_error(e):
                raise
            code = next((c for c in NET_ERRORS if c in str(e)), "lỗi mạng")
            log(f"  ! {code} – thử lại lần {attempt}/{retries}...")
            time.sleep(3 * attempt)
    raise RuntimeError(f"{str(last).splitlines()[0]}\n{diagnose(url)}")


def diagnose(url):
    """So sánh: Python mở được trang không? → khoanh vùng nguyên nhân."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            status = r.status
        ok = True
    except urllib.error.HTTPError as e:
        status, ok = e.code, True          # có phản hồi từ máy chủ → mạng vẫn thông
    except Exception as e:
        status, ok = str(e), False
    if ok:
        return ("  → CHẨN ĐOÁN: Mạng vẫn truy cập được trang (HTTP %s) nhưng TRÌNH DUYỆT bị chặn.\n"
                "    Nguyên nhân thường gặp: phần mềm diệt virus (Kaspersky, ESET, Avast, Bitdefender...) "
                "quét HTTPS hoặc chặn chương trình lạ.\n"
                "    Cách xử lý: thêm thư mục DT-Sapo-Importer vào danh sách loại trừ (Exclusions) của "
                "phần mềm diệt virus, hoặc tắt 'quét HTTPS/Web Shield' rồi chạy lại.\n"
                "    Đảm bảo máy có Microsoft Edge hoặc Google Chrome (ứng dụng sẽ tự dùng)." % status)
    return ("  → CHẨN ĐOÁN: Máy này không kết nối được tới trang (%s).\n"
            "    Kiểm tra: mở thử link bằng Chrome/Edge; tắt VPN; nếu mạng công ty dùng proxy/tường lửa, "
            "nhờ IT cho phép truy cập tên miền này; thử mạng khác (4G) để đối chứng." % status)
