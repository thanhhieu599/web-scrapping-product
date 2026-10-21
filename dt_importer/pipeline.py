"""Pipeline: URL nguồn → cào dữ liệu → lưu bản ghi + ảnh → đăng lên Sapo."""
import time
import traceback
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from .browser import launch as launch_browser
from .categories import CategoryMap, resolve as resolve_categories, split_names
from .content import build_content_html
from .sapo import SapoUploader
from .scraper import Scraper, pick_images, product_category_path, product_folder, upgrade_image_url, weight_grams
from .utils import format_vnd, name_with_vendor, read_json, write_json


def run(urls, opts, cfg, log=print, wait_user=None, stop_flag=None):
    """
    urls : list URL trang sản phẩm hoặc trang danh mục của nhà cung cấp
    opts : product_type, vendor, collections(list), tags(list), auto_save, dry_run, force
    Trả về list kết quả từng sản phẩm.
    """
    out_dir = Path(cfg["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    history_path = out_dir / "history.json"
    history = read_json(history_path, {})
    results = []
    stopped = lambda: bool(stop_flag and stop_flag())
    cmap = CategoryMap(cfg["category_map_file"]) if cfg.get("category_map_file") else None
    auto_cat = cfg.get("category_auto", True)

    # Mỗi dòng: "link" hoặc "link | Danh mục A, Danh mục B" (gán thêm danh mục cho sản phẩm từ link đó)
    entries = []
    for u in urls:
        link, _, extra = str(u).partition("|")
        if link.strip():
            entries.append((link.strip(), split_names(extra)))

    with sync_playwright() as pw:
        browser = launch_browser(pw, cfg, log, headless=True)
        scraper = Scraper(browser, cfg, log)
        uploader = None
        try:
            # 1) Gom danh sách URL sản phẩm
            product_urls, cache, listing_paths, line_cats = [], {}, {}, {}
            for u, extra in entries:
                if stopped():
                    break
                log(f"🔎 Đọc nguồn: {u}" + (f"  (danh mục gán thêm: {', '.join(extra)})" if extra else ""))
                try:
                    links, data, lpath = scraper.expand(u)
                except Exception as e:
                    log(f"  ✗ Không mở được: {e}")
                    continue
                cache.update(data)
                for l in links:
                    listing_paths.setdefault(l, lpath)
                    line_cats.setdefault(l, [])
                    line_cats[l] += [x for x in extra if x not in line_cats[l]]
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
                    data = cache.get(url) or scraper.scrape_url(url)
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
                    if sku and sku in history and cfg.get("skip_existing_sku", True) and not opts.get("force"):
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

                    # Danh mục Sapo: ô Danh mục chung + "link | danh mục" + theo đường dẫn danh mục nguồn
                    cat_path = product_category_path(data, listing_paths.get(url))
                    auto_names, how = resolve_categories(cat_path, cmap, auto_cat) if (cmap or auto_cat) else ([], "")
                    collections = []
                    for c in list(opts.get("collections") or []) + line_cats.get(url, []) + auto_names:
                        if c and c.lower() not in [x.lower() for x in collections]:
                            collections.append(c)
                    log(f"  • Danh mục nguồn: {' > '.join(cat_path) or '(không có)'}"
                        + (f" → Sapo: {', '.join(auto_names) or '(không gán)'} [{how}]" if how else ""))

                    folder = product_folder(out_dir, data)
                    strip = [x.lower() for x in cfg.get("image_url_strip_params", [])]
                    if variants and cfg.get("image_mode", "quycach") == "quycach":
                        imgs = [v["image"] for v in variants if v.get("image")]   # ảnh sản phẩm theo đúng thứ tự phiên bản
                    else:
                        imgs = pick_images(data, cfg.get("image_mode", "quycach"))
                    files = scraper.download_images(imgs, folder / "images", int(cfg.get("max_images", 15)))
                    variant_imgs = len(files) if variants and len(files) == len(variants) else 0
                    if variants and not variant_imgs:
                        log("  ! Số ảnh tải được không khớp số phiên bản → không tự gán ảnh cho phiên bản")
                    # ảnh trong mô tả: dùng link ảnh gốc của nhà cung cấp
                    data["spec"]["images"] = [upgrade_image_url(u, strip) if u else "" for u in data["spec"].get("images", [])]
                    data["feature_images"] = [upgrade_image_url(u, strip) for u in data.get("feature_images", [])]
                    html = build_content_html(data)
                    weight = weight_grams(data) if cfg.get("fill_weight", True) else None
                    title = name_with_vendor(data["name"], opts.get("vendor")) if opts.get("vendor_in_name", True) else data["name"]
                    payload = {"name": title, "sku": sku, "price": data.get("price"),
                               "content_html": html, "image_files": files, "weight_g": weight,
                               "variants": variants, "variant_images": variant_imgs, "collections": collections}
                    write_json(folder / "product.json", {**data, "title": title, "weight_g": weight,
                                                         "category_path": cat_path, "collections": collections,
                                                         "image_files": files, "variants": variants})
                    if scraper.page.url.split("#")[0] == url.split("#")[0]:
                        scraper.save_source_html(folder / "trang_goc.html")
                    (folder / "noi_dung.html").write_text(html, encoding="utf-8")
                    rec.update(sku=sku, name=data["name"], folder=str(folder))

                    if opts.get("dry_run"):
                        log(f"  ✓ Đã lưu bản nháp tại {folder}")
                        rec["status"] = "scraped"
                    else:
                        sapo_url = uploader.create_product(payload, opts)
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
            if cmap:
                try:
                    cmap.save()
                    if cmap.new_paths:
                        log(f"\n📂 {len(cmap.new_paths)} danh mục nguồn mới đã được thêm vào {cmap.path.name} "
                            "– mở bằng Excel, điền cột 'Danh mục Sapo' để lần sau gán đúng:")
                        for p_ in cmap.new_paths[:20]:
                            log(f"     {p_}")
                except OSError as e:
                    log(f"  ! Không ghi được {cmap.path.name} (đang mở trong Excel?): {e}")
            scraper.close()
            browser.close()
            if uploader:
                uploader.close()

    ok = sum(r["status"] in ("created", "scraped") for r in results)
    err = sum(r["status"] == "error" for r in results)
    ns = sum(r["status"] == "not_saved" for r in results)
    log(f"\n✅ Hoàn tất: {ok} thành công, {err} lỗi, {ns} chưa lưu, {len(results) - ok - err - ns} bỏ qua.")
    write_json(out_dir / f"ket-qua-{datetime.now():%Y%m%d-%H%M%S}.json", results)
    return results


def login_only(cfg, log=print):
    """Mở trình duyệt để đăng nhập Sapo lần đầu (lưu phiên đăng nhập)."""
    with sync_playwright() as pw:
        up = SapoUploader(pw, cfg, log)
        try:
            up.ensure_login()
            log("✓ Phiên đăng nhập đã được lưu. Có thể đóng trình duyệt.")
        finally:
            up.close()
