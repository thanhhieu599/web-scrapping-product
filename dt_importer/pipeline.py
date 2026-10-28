"""Pipeline: URL nguồn → cào dữ liệu → lưu bản ghi + ảnh → đăng lên Sapo."""
import time
import traceback
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from .browser import launch as launch_browser
from .content import build_content_html
from .sapo import SapoUploader
from .scraper import Scraper, pick_images, product_folder, upgrade_image_url, weight_grams
from .utils import format_vnd, name_with_vendor, read_json, write_json


def run(urls, opts, cfg, log=print, wait_user=None, stop_flag=None):
    """
    urls : list URL trang sản phẩm hoặc trang danh mục của nhà cung cấp
    opts : product_type, vendor, collections(list), tags(list), auto_save, dry_run, force
    Trả về list kết quả từng sản phẩm.
    """
    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    # ghi TOÀN BỘ log ra file (để gửi chẩn đoán), đồng thời vẫn hiện trên giao diện
    (out_dir / "logs").mkdir(exist_ok=True)
    log_path = out_dir / "logs" / f"nhat-ky-{datetime.now():%Y%m%d-%H%M%S}.txt"
    _ui_log = log

    def log(msg):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
        except OSError:
            pass
        _ui_log(msg)

    history_path = out_dir / "history.json"
    history = read_json(history_path, {})
    results = []
    stopped = lambda: bool(stop_flag and stop_flag())

    with sync_playwright() as pw:
        browser = launch_browser(pw, cfg, log, headless=True)
        scraper = Scraper(browser, cfg, log)
        uploader = None
        try:
            # 1) Gom danh sách URL sản phẩm
            product_urls, cache = [], {}
            for u in urls:
                if stopped():
                    break
                prof = scraper.use_site(u)
                log(f"🔎 Đọc nguồn: {u}  [{prof.get('name')}]")
                try:
                    links, data = scraper.expand(u)
                except Exception as e:
                    log(f"  ✗ Không mở được: {e}")
                    continue
                cache.update(data)
                product_urls += [l for l in links if l not in product_urls]
            log(f"📦 Tổng cộng {len(product_urls)} link sản phẩm cần xử lý.")

            if not opts.get("dry_run"):
                uploader = SapoUploader(pw, cfg, log, wait_user)
                uploader.ensure_login()

            # 2) Từng sản phẩm
            for idx, url in enumerate(product_urls, 1):
                if stopped():
                    log("⏹ Đã dừng theo yêu cầu.")
                    break
                log(f"\n[{idx}/{len(product_urls)}] {url}")
                rec = {"url": url, "status": "error"}
                try:
                    prof = scraper.use_site(url)
                    data = cache.get(url) or scraper.scrape_url(url)
                    # ô để trống → dùng giá trị mặc định của nhà cung cấp trong sites.json
                    popts = dict(opts, vendor=opts.get("vendor") or prof.get("vendor") or "",
                                 product_type=opts.get("product_type") or prof.get("product_type") or "")
                    icfg = scraper.cfg
                    if not Scraper.is_product(data):
                        log("  – Bỏ qua: không phải trang sản phẩm")
                        rec["status"] = "skipped"
                        results.append(rec)
                        continue
                    sku = data.get("sku") or ""
                    log(f"  • {data['name']} | Mã: {sku or '(không có)'} | Giá: {format_vnd(data.get('price')) or '(không có)'}")
                    log(f"  • Đặc điểm: {len(data['features'])} dòng | Thông số: {len(data['spec']['rows'])} dòng"
                        f" ({data['found'].get('spec_source') or '-'})"
                        f" | Ảnh quy cách: {len(data['variant_images'])} | Ảnh gallery: {len(data['gallery_images'])}")
                    if sku and sku in history and icfg.get("skip_existing_sku", True) and not opts.get("force"):
                        log(f"  – Bỏ qua: mã {sku} đã đăng trước đó ({history[sku].get('sapo_url')})")
                        rec.update(status="exists", sku=sku)
                        results.append(rec)
                        continue

                    # Phiên bản (các ô dưới QUY CÁCH) – chỉ đọc khi có nhập "Tên thuộc tính"
                    variants = []
                    if opts.get("variant_attr"):
                        if scraper.page.url.split("#")[0] != url.split("#")[0]:
                            data = scraper.scrape_url(url)
                        variants = scraper.scrape_variants(url, data)
                        log(f"  • Phiên bản: {len(variants)}" + (" → " + ", ".join(
                            f"{v['value']} ({format_vnd(v['price'])})" for v in variants) if variants else ""))

                    folder = product_folder(out_dir, data)
                    strip = [x.lower() for x in icfg.get("image_url_strip_params", [])]
                    adapter = scraper.adapter
                    if not adapter or adapter.platform != data.get("platform"):     # dữ liệu lấy từ bộ nhớ tạm
                        from .sites import ADAPTERS
                        from .sites.base import SiteAdapter
                        adapter = ADAPTERS.get(data.get("platform"), SiteAdapter)(prof)
                    variant_mode = bool(variants) and icfg.get("image_mode", "quycach") == "quycach"
                    if variant_mode:
                        imgs = [v.get("image") for v in variants]          # đúng thứ tự phiên bản (có thể trùng hình)
                        extra = adapter.extra_images(data) if adapter else []
                        imgs += [u for u in extra if u and u not in imgs]
                    else:
                        imgs = pick_images(data, icfg.get("image_mode", "quycach"))
                    # ảnh cùng tên cỡ lớn trong dữ liệu trang (gallery, phiên bản) dùng thay ảnh nhỏ / ảnh gốc bị chặn
                    alternates = list(data.get("gallery_images") or []) + [v.get("image") for v in variants] \
                        + list(data.get("variant_images") or [])
                    max_img = int(icfg.get("max_images", 15))
                    files = scraper.download_images(imgs, folder / "images", max_img, alternates,
                                                    keep_small="always" if variant_mode else "if_none")
                    # ảnh của từng phiên bản = vị trí trong danh sách ảnh đã tải (hình trùng dùng chung 1 ảnh)
                    variant_idx = list(scraper.last_index[:len(variants)]) if variant_mode else [None] * len(variants)
                    if not files:                       # bộ ảnh đã chọn hỏng hết → thử bộ ảnh còn lại
                        others = [u for u in (data.get("gallery_images") or []) + (data.get("variant_images") or [])
                                  if u and u not in imgs]
                        if others:
                            log("  ! Không lấy được ảnh nào – thử bộ ảnh khác trên trang...")
                            files = scraper.download_images(others, folder / "images", max_img, alternates)
                            variant_idx = [None] * len(variants)
                    if variants and not any(k is not None for k in variant_idx):
                        log("  ! Không xác định được ảnh riêng của từng phiên bản → không tự gán ảnh cho phiên bản")
                    # ảnh trong mô tả: dùng link ảnh gốc của nhà cung cấp
                    data["spec"]["images"] = [upgrade_image_url(u, strip) if u else "" for u in data["spec"].get("images", [])]
                    data["feature_images"] = [upgrade_image_url(u, strip) for u in data.get("feature_images", [])]
                    mode = adapter.content_mode(data) if adapter else "features_specs"
                    html = build_content_html(data, mode)
                    weight = weight_grams(data) if cfg.get("fill_weight", True) else None
                    title = name_with_vendor(data["name"], popts.get("vendor")) if opts.get("vendor_in_name", True) else data["name"]
                    payload = {"debug_dir": str(folder), "name": title, "sku": sku, "price": data.get("price"),
                               "content_html": html, "image_files": files, "weight_g": weight,
                               "variants": variants, "variant_image_idx": variant_idx}
                    write_json(folder / "product.json", {**data, "title": title, "weight_g": weight,
                                                         "image_files": files, "variants": variants})
                    if scraper.page.url.split("#")[0] == url.split("#")[0]:
                        scraper.save_source_html(folder / "trang_goc.html")
                    (folder / "noi_dung.html").write_text(html, encoding="utf-8")
                    rec.update(sku=sku, name=data["name"], folder=str(folder), images=len(files), site=prof.get("name"))
                    if not files:
                        log("  ⚠ KHÔNG lấy được ảnh nào cho sản phẩm này (xem các dòng 'Không tải được ảnh' ở trên)")

                    if opts.get("dry_run"):
                        log(f"  ✓ Đã lưu bản nháp tại {folder}")
                        rec["status"] = "scraped"
                    else:
                        try:
                            sapo_url = uploader.create_product(payload, popts)
                        except Exception as e:
                            if not _browser_closed(e):
                                raise
                            # cửa sổ Sapo bị đóng / trình duyệt bị tắt → mở lại và làm lại SP này (1 lần)
                            log("  ! Trình duyệt Sapo bị đóng giữa chừng – đang mở lại và làm lại sản phẩm này...")
                            try:
                                uploader.close()
                            except Exception:
                                pass
                            uploader = SapoUploader(pw, cfg, log, wait_user)
                            uploader.ensure_login()
                            sapo_url = uploader.create_product(payload, popts)
                        rec["warnings"] = list(getattr(uploader, "last_warnings", []) or [])
                        if not sapo_url:
                            log("  – Sản phẩm CHƯA được lưu trên Sapo (không ghi vào lịch sử, lần sau sẽ đăng lại)")
                            rec["status"] = "not_saved"
                            results.append(rec)
                            continue
                        rec.update(status="created", sapo_url=sapo_url)
                        if sku:
                            history[sku] = {"sapo_url": sapo_url, "source": url,
                                            "time": datetime.now().isoformat(timespec="seconds")}
                            write_json(history_path, history)
                except Exception as e:
                    log(f"  ✗ Lỗi: {e}")
                    rec["error"] = str(e)
                    (out_dir / "logs").mkdir(exist_ok=True)
                    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                    (out_dir / "logs" / f"loi-{stamp}.txt").write_text(traceback.format_exc(), encoding="utf-8")
                    if uploader:
                        uploader.screenshot(out_dir / "logs" / f"loi-{stamp}.png")
                results.append(rec)
                time.sleep(float(cfg.get("delay_seconds", 2)))
        finally:
            scraper.close()
            browser.close()
            if uploader:
                uploader.close()

    ok = sum(r["status"] in ("created", "scraped") for r in results)
    err = sum(r["status"] == "error" for r in results)
    warn = [r for r in results if r["status"] == "created" and r.get("warnings")]
    if warn:
        log(f"\n⚠ {len(warn)} sản phẩm ĐÃ LƯU nhưng cần kiểm tra lại trên Sapo:")
        for r in warn:
            log(f"   - {r.get('sku') or ''} {r.get('name') or ''}: {'; '.join(r['warnings'])[:200]}")
    no_img = [r for r in results if r["status"] in ("created", "scraped") and r.get("images") == 0]
    if no_img:
        log(f"\n⚠ {len(no_img)} sản phẩm KHÔNG có ảnh – cần thêm ảnh bằng tay trên Sapo:")
        for r in no_img:
            log(f"   - {r.get('sku') or ''} {r.get('name') or ''}  ({r['url']})")
    ns = sum(r["status"] == "not_saved" for r in results)
    log(f"\n✅ Hoàn tất: {ok} thành công, {err} lỗi, {ns} chưa lưu, {len(results) - ok - err - ns} bỏ qua.")
    write_json(out_dir / f"ket-qua-{datetime.now():%Y%m%d-%H%M%S}.json", results)
    return results


def _browser_closed(exc):
    m = str(exc).lower()
    return "has been closed" in m or "target closed" in m or "browser has disconnected" in m or "connection closed" in m


def login_only(cfg, log=print):
    """Mở trình duyệt để đăng nhập Sapo lần đầu (lưu phiên đăng nhập)."""
    with sync_playwright() as pw:
        up = SapoUploader(pw, cfg, log)
        try:
            up.ensure_login()
            log("✓ Phiên đăng nhập đã được lưu. Có thể đóng trình duyệt.")
        finally:
            up.close()
