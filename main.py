"""D&T Sapo Importer – chép sản phẩm từ web nhà cung cấp sang Sapo.

Chạy giao diện:   python main.py
Chạy dòng lệnh:   python main.py --url <link> --loai "Hộp đựng dụng cụ" --ncc "Milwaukee"
Đăng nhập Sapo:   python main.py --login
"""
import argparse
import json
import os
import queue
import sys
import threading
from pathlib import Path

from dt_importer.utils import FROZEN, ROOT, load_config, read_json, write_json

if FROZEN:
    # Trình duyệt Chromium đi kèm trong thư mục ms-playwright cạnh file .exe
    _browsers = ROOT / "ms-playwright"
    if _browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_browsers))
    # Bản không có cửa sổ dòng lệnh: ghi output ra file nhật ký
    if sys.stdout is None or sys.stderr is None:
        _log = open(ROOT / "nhat_ky.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or _log
        sys.stderr = sys.stderr or _log

STATE_FILE = ROOT / "last_inputs.json"


def split_list(text):
    return [x.strip() for x in (text or "").replace("\n", ",").split(",") if x.strip()]


def build_opts(product_type, vendor, collections, tags, auto_save, dry_run, force=False,
               variant_attr="", vendor_in_name=True):
    return {"product_type": product_type.strip(), "vendor": vendor.strip(),
            "collections": split_list(collections), "tags": split_list(tags),
            "auto_save": auto_save, "dry_run": dry_run, "force": force,
            "variant_attr": (variant_attr or "").strip(), "vendor_in_name": vendor_in_name}


# ---------------------------------------------------------------- CLI
def cli(args):
    from dt_importer import pipeline
    cfg = load_config(args.config)
    if args.login:
        pipeline.login_only(cfg)
        return
    urls = list(args.url or [])
    if args.file:
        urls += [l.strip() for l in Path(args.file).read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.startswith("#")]
    if not urls:
        sys.exit("Cần --url hoặc --file")
    auto_save = cfg.get("auto_save", True) and not args.no_save
    opts = build_opts(args.loai or "", args.ncc or "", args.danh_muc or "", args.tags or "",
                      auto_save, args.dry_run, args.force, args.thuoc_tinh or "", not args.khong_chen_ncc)
    pipeline.run(urls, opts, cfg)


# ---------------------------------------------------------------- GUI
def gui(config_path=None):
    import tkinter as tk
    from tkinter import ttk, messagebox, scrolledtext

    cfg = load_config(config_path)
    state = read_json(STATE_FILE, {})
    msgs = queue.Queue()
    stop = threading.Event()
    resume = threading.Event()

    root = tk.Tk()
    root.title("D&T – Chép sản phẩm nhà cung cấp → Sapo")
    root.geometry("1000x760")
    frm = ttk.Frame(root, padding=12)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    ttk.Label(frm, text="Link trang nguồn (mỗi dòng 1 link – trang sản phẩm hoặc trang danh mục):").grid(
        row=2, column=0, columnspan=2, sticky="w")
    txt_urls = scrolledtext.ScrolledText(frm, height=6)
    txt_urls.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=(2, 8))
    txt_urls.insert("1.0", state.get("urls", ""))

    fields = {}
    ttk.Label(frm, text="Địa chỉ Sapo Admin").grid(row=1, column=0, sticky="w")
    var_sapo = tk.StringVar(value=cfg["sapo_admin_url"])
    ttk.Entry(frm, textvariable=var_sapo).grid(row=1, column=1, sticky="ew", pady=3)
    rows = [("loai", "Loại sản phẩm (*)"), ("ncc", "Nhà cung cấp (*)"),
            ("thuoc_tinh", "Tên thuộc tính phiên bản (vd: Model) – để trống nếu không tạo phiên bản"),
            ("danh_muc", "Danh mục Sapo (tuỳ chọn, cách nhau dấu phẩy)"), ("tags", "Tags (tuỳ chọn, cách nhau dấu phẩy)")]
    for i, (key, label) in enumerate(rows, start=4):
        ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", pady=3)
        var = tk.StringVar(value=state.get(key, ""))
        ttk.Entry(frm, textvariable=var).grid(row=i, column=1, sticky="ew", pady=3)
        fields[key] = var

    var_save = tk.BooleanVar(value=state.get("auto_save", cfg.get("auto_save", True)))
    var_dry = tk.BooleanVar(value=False)
    var_force = tk.BooleanVar(value=False)
    var_vname = tk.BooleanVar(value=state.get("vendor_in_name", True))
    var_img = tk.StringVar(value=state.get("image_mode", cfg.get("image_mode", "quycach")))
    opt = ttk.Frame(frm)
    opt.grid(row=9, column=0, columnspan=2, sticky="w", pady=6)
    ttk.Checkbutton(opt, text="Tự bấm Lưu trên Sapo", variable=var_save).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(opt, text="Chỉ cào thử (không đăng)", variable=var_dry).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(opt, text="Đăng lại cả mã đã đăng", variable=var_force).pack(side="left", padx=(0, 12))
    ttk.Checkbutton(opt, text="Chèn nhà cung cấp vào tên", variable=var_vname).pack(side="left", padx=(0, 12))
    ttk.Label(opt, text="Ảnh:").pack(side="left")
    ttk.Combobox(opt, textvariable=var_img, width=10, state="readonly",
                 values=["quycach", "gallery", "both"]).pack(side="left")

    btns = ttk.Frame(frm)
    btns.grid(row=10, column=0, columnspan=2, sticky="w", pady=4)
    log_box = scrolledtext.ScrolledText(frm, height=20, state="disabled", font=("Consolas", 9))
    log_box.grid(row=11, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
    frm.rowconfigure(11, weight=1)

    def log(msg):
        msgs.put(("log", msg))

    def wait_user(msg):
        resume.clear()
        msgs.put(("wait", msg))
        resume.wait()

    def pump():
        try:
            while True:
                kind, msg = msgs.get_nowait()
                if kind == "log":
                    log_box.configure(state="normal")
                    log_box.insert("end", msg + "\n")
                    log_box.see("end")
                    log_box.configure(state="disabled")
                elif kind == "wait":
                    btn_continue.configure(state="normal")
                    log(f"⏸ {msg}")
                elif kind == "done":
                    btn_run.configure(state="normal")
                    btn_login.configure(state="normal")
                    btn_stop.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(150, pump)

    def worker(fn):
        try:
            fn()
        except Exception as e:
            log(f"✗ Lỗi: {e}")
        finally:
            msgs.put(("done", ""))

    def start(fn):
        btn_run.configure(state="disabled")
        btn_login.configure(state="disabled")
        btn_stop.configure(state="normal")
        stop.clear()
        threading.Thread(target=worker, args=(fn,), daemon=True).start()

    def sync_sapo_url():
        url = var_sapo.get().strip().rstrip("/")
        if url and not url.endswith("/admin"):
            url += "/admin"
        if url and url != cfg["sapo_admin_url"]:
            cfg["sapo_admin_url"] = url
            path = Path(config_path) if config_path else ROOT / "config.json"
            raw = read_json(path, {})
            raw["sapo_admin_url"] = url
            path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"✓ Đã lưu địa chỉ Sapo: {url}")

    def on_run():
        from dt_importer import pipeline
        sync_sapo_url()
        urls = [u.strip() for u in txt_urls.get("1.0", "end").splitlines() if u.strip().startswith("http")]
        if not urls:
            messagebox.showwarning("Thiếu link", "Hãy dán ít nhất 1 link trang nguồn.")
            return
        if not var_dry.get() and (not fields["loai"].get().strip() or not fields["ncc"].get().strip()):
            if not messagebox.askyesno("Thiếu thông tin", "Chưa nhập Loại / Nhà cung cấp. Vẫn tiếp tục?"):
                return
        st = {k: v.get() for k, v in fields.items()}
        st.update(urls=txt_urls.get("1.0", "end").strip(), auto_save=var_save.get(), image_mode=var_img.get(),
                  vendor_in_name=var_vname.get())
        write_json(STATE_FILE, st)
        run_cfg = dict(cfg, image_mode=var_img.get())
        opts = build_opts(st["loai"], st["ncc"], st["danh_muc"], st["tags"],
                          var_save.get(), var_dry.get(), var_force.get(), st["thuoc_tinh"], var_vname.get())
        start(lambda: pipeline.run(urls, opts, run_cfg, log, wait_user, stop.is_set))

    def on_login():
        from dt_importer import pipeline
        sync_sapo_url()
        start(lambda: pipeline.login_only(cfg, log))

    def on_continue():
        btn_continue.configure(state="disabled")
        resume.set()

    def on_stop():
        stop.set()
        resume.set()
        log("… Sẽ dừng sau sản phẩm hiện tại.")

    btn_run = ttk.Button(btns, text="▶ Chạy", command=on_run)
    btn_run.pack(side="left", padx=(0, 8))
    btn_login = ttk.Button(btns, text="🔑 Đăng nhập Sapo (lần đầu)", command=on_login)
    btn_login.pack(side="left", padx=(0, 8))
    btn_continue = ttk.Button(btns, text="Tiếp tục ▸", command=on_continue, state="disabled")
    btn_continue.pack(side="left", padx=(0, 8))
    btn_stop = ttk.Button(btns, text="⏹ Dừng", command=on_stop, state="disabled")
    btn_stop.pack(side="left")

    pump()
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description="Chép sản phẩm từ web nhà cung cấp sang Sapo")
    ap.add_argument("--url", action="append", help="Link trang sản phẩm / danh mục (lặp lại được)")
    ap.add_argument("--file", help="File .txt chứa danh sách link, mỗi dòng 1 link")
    ap.add_argument("--loai", help="Loại sản phẩm")
    ap.add_argument("--ncc", help="Nhà cung cấp")
    ap.add_argument("--danh-muc", dest="danh_muc", help="Danh mục Sapo, cách nhau dấu phẩy")
    ap.add_argument("--tags", help="Tags, cách nhau dấu phẩy")
    ap.add_argument("--thuoc-tinh", dest="thuoc_tinh", help="Tên thuộc tính để tạo phiên bản từ các ô Quy cách (vd: Model)")
    ap.add_argument("--khong-chen-ncc", dest="khong_chen_ncc", action="store_true", help="Không chèn nhà cung cấp vào tên")
    ap.add_argument("--dry-run", action="store_true", help="Chỉ cào và lưu vào output/, không đăng Sapo")
    ap.add_argument("--no-save", action="store_true", help="Điền form nhưng không bấm Lưu (tự kiểm tra)")
    ap.add_argument("--force", action="store_true", help="Đăng lại cả mã đã đăng trước đó")
    ap.add_argument("--login", action="store_true", help="Chỉ mở trình duyệt để đăng nhập Sapo")
    ap.add_argument("--config", help="Đường dẫn config.json khác")
    args = ap.parse_args()
    if len(sys.argv) == 1 or (len(sys.argv) == 3 and args.config):
        gui(args.config)
    else:
        cli(args)


if __name__ == "__main__":
    main()
