# D&T Sapo Importer – Chép sản phẩm từ web nhà cung cấp sang Sapo

Chỉ cần dán **link trang nguồn** (trang 1 sản phẩm hoặc cả trang danh mục), nhập **Loại** + **Nhà cung cấp** → ứng dụng tự động:

1. Mở trang nhà cung cấp, đọc dữ liệu sản phẩm.
2. Tải ảnh về máy, lưu bản ghi (để đối chiếu / làm lại).
3. Mở Sapo Admin `…/admin/products/create`, **tự điền form** và bấm **Lưu**.
4. Ghi nhớ mã sản phẩm đã đăng → lần sau không đăng trùng.

---

## 1. Dữ liệu được lấy và điền vào đâu

| Trang nguồn (nhà cung cấp) | → | Form "Thêm mới sản phẩm" trên Sapo |
|---|---|---|
| Tên sản phẩm (tiêu đề cạnh giá, không lấy banner viết hoa) + **chèn tên Nhà cung cấp**: tên có mã SP → chèn ngay trước mã (`Hộp đựng dụng cụ 8450, 8424` → `Hộp đựng dụng cụ Milwaukee 8450, 8424`); tên không có mã → thêm vào cuối. Tắt được bằng ô "Chèn nhà cung cấp vào tên" | → | **Tên sản phẩm** |
| Mã sản phẩm – chuỗi nhỏ dưới tên (vd `48-22-8450`) | → | **Mã sản phẩm / SKU** |
| Giá (vd `2.940.000 ₫` → `2940000`) | → | **Giá** + tự tick **"Giá đã bao gồm VAT"** |
| Các ảnh dưới chữ **QUY CÁCH** (tải ảnh gốc, đổi sang JPG) | → | **Ảnh sản phẩm** |
| Mục **Đặc điểm** (danh sách gạch đầu dòng) | → | **Nội dung** – phần "Đặc điểm nổi bật" |
| Mục **Thông Số** – giữ nguyên dạng **bảng** như trang gốc (đủ hàng, cột model, dòng tiêu đề nhóm). Trang dùng bảng HTML hay xếp lưới bằng `div` (như Milwaukee/Magento) đều dựng lại được thành bảng | → | **Nội dung** – bảng "Thông số kỹ thuật" có kẻ khung, tô màu xen kẽ |
| Trọng lượng (kg) đúng cột của mã sản phẩm | → | **Khối lượng** (gram, để tính phí ship) |
| Các ô dưới **QUY CÁCH** (mỗi ô = 1 phiên bản: mã SP, giá, ảnh riêng) – chỉ khi bạn nhập **"Tên thuộc tính phiên bản"** (vd `Model`) | → | **Thuộc tính**: tên = ô bạn nhập, giá trị = mã SP từng phiên bản; mỗi dòng phiên bản được đặt **giá, SKU** và **gán đúng ảnh** |
| Ảnh nằm trong phần mô tả (vd hàng ảnh sản phẩm phía trên bảng Thông số, ảnh minh hoạ trong Đặc điểm) | → | Giữ trong **Nội dung**, đúng vị trí như trang gốc (dùng link ảnh gốc của nhà cung cấp) |
| Bạn nhập: Loại sản phẩm | → | **Loại** |
| Bạn nhập: Nhà cung cấp | → | **Nhà cung cấp** |
| Bạn nhập (tuỳ chọn): Danh mục, Tags | → | **Danh mục**, **Tags** |
| – | → | Tự tick **"Sản phẩm yêu cầu vận chuyển"** |
| Bạn chọn: **Trạng thái** Hiển thị / Ẩn (mặc định Hiển thị) | → | Mục **Trạng thái** (Hiển thị / Ẩn) |
| Sản phẩm **"Liên hệ"** (không có giá) | → | Vẫn được đăng, ô **Giá** để nguyên 0 (đa số giao diện Sapo hiển thị "Liên hệ") |

**Không lấy**: khối "BAO GỒM TRONG SẢN PHẨM" và dòng `48-22-xxxx (1)` bên dưới (hình 3).
Các mã model ở khối đó chỉ được dùng làm **tiêu đề cột** cho bảng thông số (để biết cột nào là model nào).

---

## 2. Bản Windows chạy ngay – KHÔNG cần cài đặt (dùng cho máy khách hàng)

1. Vào trang **[Releases](https://github.com/thanhhieu599/web-scrapping-product/releases/latest)**,
   tải file **`DT-Sapo-Importer-windows.zip`** (~400 MB, đã gồm Python, thư viện, trình duyệt Chromium).
2. Chuột phải → **Extract All** → mở thư mục `DT-Sapo-Importer` → nhấp đúp **`DT-Sapo-Importer.exe`**.
3. Nhập **Địa chỉ Sapo Admin** của cửa hàng (vd `https://tencuahang.mysapo.net/admin`) → bấm **Đăng nhập Sapo (lần đầu)**.

Yêu cầu: Windows 10/11 64-bit. Nếu Windows báo *"Windows protected your PC"* → **More info → Run anyway**
(file chưa ký số). Hướng dẫn ngắn cho khách nằm trong `HUONG_DAN_SU_DUNG.txt` trong thư mục giải nén.

**Bản đóng gói được tạo tự động**: mỗi lần push lên `main`, GitHub Actions (`.github/workflows/build-windows.yml`)
build trên máy Windows bằng PyInstaller, tải kèm Chromium, **chạy thử file .exe trên trang mô phỏng**,
rồi đăng file ZIP lên Releases. Muốn build tay trên máy Windows có Python:
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# kết quả: dist\DT-Sapo-Importer-windows.zip
```

## 2b. Cài đặt từ mã nguồn (dành cho người phát triển)

### Windows
1. Cài **Python 3.10 trở lên** tại <https://www.python.org/downloads/> – khi cài **tick ô "Add Python to PATH"**.
2. Tải mã nguồn: nút **Code → Download ZIP** trên GitHub, giải nén ra ví dụ `D:\sapo-importer`.
3. Nhấp đúp **`install.bat`** (cài thư viện + trình duyệt Chromium, ~3–5 phút).

### Mac / Linux
```bash
./install.sh
```

---

## 3. Sử dụng hằng ngày

### Cách 1 – Giao diện (khuyên dùng)
Nhấp đúp **`run.bat`** (Mac/Linux: `./run.sh`). Cửa sổ ứng dụng hiện ra:

1. **Lần đầu tiên**: bấm **🔑 Đăng nhập Sapo (lần đầu)** → trình duyệt mở trang Sapo → đăng nhập như bình thường.
   Phiên đăng nhập được lưu trong thư mục `browser_profile/`, các lần sau không cần đăng nhập lại.
2. Dán link trang nguồn (mỗi dòng 1 link). Có thể là:
   - link 1 sản phẩm, hoặc
   - link **trang danh mục** → ứng dụng tự lấy hết sản phẩm trong danh mục (kể cả các trang 2, 3…).
3. Nhập **Loại sản phẩm** và **Nhà cung cấp** (bắt buộc), **Danh mục / Tags** (tuỳ chọn, cách nhau dấu phẩy).
4. Bấm **▶ Chạy**. Theo dõi tiến trình trong khung log.

Tuỳ chọn trên giao diện:

| Tuỳ chọn | Ý nghĩa |
|---|---|
| Tự bấm Lưu trên Sapo | Bỏ tick → ứng dụng điền form rồi **dừng chờ** bạn kiểm tra và tự bấm Lưu, sau đó bấm **Tiếp tục ▸** |
| Chỉ cào thử (không đăng) | Chỉ lấy dữ liệu + ảnh về thư mục `output/` để xem trước, không đụng tới Sapo |
| Đăng lại cả mã đã đăng | Mặc định mã đã đăng sẽ bị bỏ qua để tránh trùng. Tick để đăng lại |
| Ảnh: `quycach` / `gallery` / `both` | Lấy ảnh dưới chữ Quy cách (mặc định) / ảnh cột trái / cả hai |

> Gợi ý quy trình an toàn: lần đầu với 1 nhà cung cấp mới, chạy **"Chỉ cào thử"**, mở `output/<mã-sp>/noi_dung.html`
> để xem bố cục, sau đó mới chạy thật. Với 2–3 sản phẩm đầu nên bỏ tick "Tự bấm Lưu" để kiểm tra form.

### Cách 2 – Dòng lệnh (chạy hàng loạt / lên lịch)
```bash
# 1 sản phẩm
python main.py --url "https://web-ncc/san-pham/abc" --loai "Hộp đựng dụng cụ" --ncc "Milwaukee"

# Cả danh mục + gán danh mục, tag trên Sapo
python main.py --url "https://web-ncc/danh-muc/luu-tru" --loai "Hộp đựng dụng cụ" --ncc "Milwaukee" \
               --danh-muc "Lưu trữ dụng cụ" --tags "packout,milwaukee"

# Nhiều link trong file (xem urls_mau.txt)
python main.py --file urls.txt --loai "Găng tay" --ncc "TOWA"

python main.py --url ... --thuoc-tinh "Model"   # tạo phiên bản từ các ô Quy cách
python main.py --url ... --khong-chen-ncc       # không chèn nhà cung cấp vào tên
python main.py --url ... --an                   # đăng ở trạng thái Ẩn (để duyệt lại trước khi mở bán)
python main.py --url ... --dry-run   # chỉ cào, không đăng
python main.py --url ... --no-save   # điền form nhưng không bấm Lưu
python main.py --url ... --force     # đăng lại mã đã đăng
python main.py --login               # chỉ đăng nhập Sapo
```

---

### Phiên bản (thuộc tính) – lưu ý
- Nhập **Tên thuộc tính phiên bản** (vd `Model`, `Kích thước`) → ứng dụng bấm lần lượt từng ô dưới QUY CÁCH
  trên trang nguồn để đọc **mã SP, giá, ảnh** của từng phiên bản (web Magento như Milwaukee còn đọc thẳng dữ liệu cấu hình).
- Ảnh sản phẩm được tải lên **theo đúng thứ tự phiên bản**, rồi phiên bản thứ *n* được gán ảnh thứ *n*.
- Nếu Sapo đổi giao diện và ứng dụng **không đặt được** giá/SKU/ảnh của phiên bản nào, ứng dụng **không tự bấm Lưu**:
  nó dừng lại để bạn hoàn tất bằng tay, và lưu form vào `output/logs/sapo-form-*.html` – gửi file này để chỉnh công cụ.
- Để trống ô Tên thuộc tính → đăng sản phẩm đơn như trước.

## 4. Kết quả lưu ở đâu

```
output/
├── 48-22-8450/
│   ├── images/01.jpg, 02.jpg …   # ảnh đã tải (độ phân giải gốc, JPG)
│   ├── product.json             # toàn bộ dữ liệu đã cào
│   ├── noi_dung.html            # nội dung đã dựng – mở bằng trình duyệt để xem trước
│   └── trang_goc.html           # bản lưu trang nguồn – gửi file này khi cần chỉnh cách đọc dữ liệu
├── history.json                 # mã SP đã đăng → link sản phẩm trên Sapo (chống đăng trùng)
├── ket-qua-YYYYMMDD-HHMMSS.json # báo cáo mỗi lần chạy
└── logs/                        # chi tiết lỗi + ảnh chụp màn hình Sapo khi lỗi
```

---

## 5. Cấu hình (`config.json`)

| Khoá | Mặc định | Ý nghĩa |
|---|---|---|
| `sapo_admin_url` | `https://trangthietbivn.mysapo.net/admin` | Địa chỉ admin Sapo |
| `auto_save` | `true` | Tự bấm Lưu |
| `image_mode` | `quycach` | `quycach` / `gallery` / `both` |
| `max_images` | `15` | Số ảnh tối đa mỗi sản phẩm |
| `fill_weight` | `true` | Tự điền khối lượng từ "Trọng lượng (kg)" |
| `skip_existing_sku` | `true` | Bỏ qua mã đã đăng |
| `listing_max_pages` | `10` | Số trang tối đa khi quét trang danh mục |
| `product_link_pattern` | `""` | Regex lọc link sản phẩm ở trang danh mục, vd `"/san-pham/"`. Để trống = tự nhận (link có ảnh, ngoài menu) |
| `delay_seconds` | `2` | Nghỉ giữa 2 sản phẩm (tránh bị chặn) |
| `browser_channel` | `"auto"` | `auto` = dùng Microsoft Edge → Google Chrome có sẵn trên máy → Chromium đóng gói kèm. Có thể đặt cố định `"msedge"`, `"chrome"`, `"bundled"` |
| `browser_executable` | `""` | Đường dẫn file chạy trình duyệt (nếu cần) |
| `source_selectors` | trống | Ghi đè CSS selector khi trang nguồn đổi giao diện (xem mục 7) |

---

## 6. Cách hoạt động (để dễ bảo trì)

- **Không phụ thuộc mã CSS của trang nguồn**: ứng dụng tìm dữ liệu theo **chữ hiển thị** –
  giá là dòng dạng `x.xxx.xxx ₫`, tên là tiêu đề trong cùng khối với giá, mã SP là chuỗi dạng `48-22-8450`
  ngay sau tên, ảnh nằm sau chữ `QUY CÁCH`, nội dung nằm sau tiêu đề `Đặc điểm` / `Thông Số`.
  Nhờ vậy dùng được cho nhiều web nhà cung cấp có bố cục tương tự.
- **Sapo**: điều khiển trình duyệt thật (Playwright), tìm ô theo placeholder/nhãn tiếng Việt
  ("Nhập tên sản phẩm", "Giá", "Mã sản phẩm / SKU"…). Nội dung được đưa vào trình soạn thảo qua API của editor;
  nếu không được sẽ dùng chế độ **Mã HTML**.
- Ảnh được tải bằng phiên trình duyệt (có Referer), bỏ tham số thu nhỏ (`?width=`, `?w=`…) để lấy ảnh gốc,
  chuyển sang JPG nền trắng – Sapo nhận ổn định.

Cấu trúc mã:
```
main.py                  # giao diện + dòng lệnh
dt_importer/scraper.py   # cào trang nguồn
dt_importer/content.py   # dựng HTML Đặc điểm + bảng Thông số
dt_importer/sapo.py      # tự điền form Sapo
dt_importer/pipeline.py  # điều phối, chống trùng, ghi log
tests/run_mock_test.py   # kiểm thử tự động trên trang giả lập
```

---

## 7. Xử lý sự cố

| Hiện tượng | Cách xử lý |
|---|---|
| `ERR_CONNECTION_RESET` / `ERR_CONNECTION_CLOSED` / `ERR_SSL_PROTOCOL_ERROR` | Ứng dụng tự thử lại 3 lần rồi **tự chẩn đoán** (ghi ngay trong log). Thường do **phần mềm diệt virus quét HTTPS** hoặc chặn chương trình lạ → thêm thư mục ứng dụng vào *Exclusions*, hoặc tắt "HTTPS scanning / Web Shield". Đảm bảo máy có Edge hoặc Chrome (ứng dụng ưu tiên dùng). Nếu chẩn đoán báo "máy không kết nối được": tắt VPN, hỏi IT về proxy/tường lửa, thử mạng 4G |
| Log báo "Bỏ qua: không phải trang sản phẩm" | Trang nguồn khác bố cục. Điền `source_selectors` trong `config.json`, ví dụ `"name": ".product-info h2"`, `"sku": ".product-code"`, `"price": ".price"`, `"variant_images": ".swatches"`, `"features": "#dac-diem"`, `"specs": "#thong-so"` (chuột phải → Inspect trên trang nguồn để lấy) |
| Trang danh mục lấy nhầm link (tin tức, banner…) | Đặt `product_link_pattern`, vd `"/san-pham/"` |
| "Danh mục … không có trong Sapo" | Tạo danh mục đó trên Sapo trước (tên phải trùng khớp) |
| Bấm Lưu nhưng Sapo không chuyển trang | Xem ảnh chụp trong `output/logs/` – thường do thiếu trường bắt buộc hoặc Sapo đổi giao diện |
| Ảnh bị nhỏ / mờ | Đổi `image_mode` sang `both` hoặc `gallery` |
| Muốn đăng nhập lại tài khoản Sapo khác | Xoá thư mục `browser_profile/` rồi bấm "Đăng nhập Sapo" |

Kiểm thử sau khi sửa mã (không cần Internet, chạy trên trang mô phỏng):
```bash
python tests/test_units.py        # từng hàm: đọc giá, chèn nhà cung cấp, khối lượng, chống mã độc...
python tests/run_mock_test.py     # toàn bộ quy trình: cào → đăng Sapo (phiên bản, ảnh, trạng thái...)
python tests/test_edge_cases.py   # tình huống xấu: mất mạng, chưa đăng nhập, ảnh lỗi, "Liên hệ", bấm Dừng...
python tests/test_gui.py          # giao diện: tự điền ô, bấm Chạy, kiểm tra kết quả
```
Mỗi lần cập nhật mã, GitHub chạy **toàn bộ** các bộ kiểm thử trên Windows với Microsoft Edge thật;
chỉ khi tất cả đạt mới đóng gói và phát hành bản mới.

---

## 8. Lưu ý vận hành

- Chỉ sao chép dữ liệu từ nhà cung cấp mà D&T **được phép phân phối/sử dụng nội dung**.
- Giá lấy về là **giá niêm yết của nhà cung cấp** – nên rà lại chính sách giá bán của D&T trước khi hiển thị
  (có thể bỏ tick "Tự bấm Lưu" để chỉnh giá trước khi lưu).
- Nội dung chép nguyên văn sẽ bị Google coi là **trùng lặp**. Để SEO tốt, sau khi đăng nên bổ sung đoạn mô tả riêng
  (ứng dụng, tiêu chuẩn, ngành phù hợp) và tiêu đề/mô tả SEO cho các sản phẩm chủ lực.
