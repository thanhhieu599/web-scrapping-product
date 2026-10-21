# Đóng gói bản Windows chạy ngay (không cần cài Python / thư viện / trình duyệt).
# Chạy trên máy Windows có Python 3.10+:   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
param([switch]$SkipZip)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$name = "DT-Sapo-Importer"
$dist = "dist\$name"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt pyinstaller

# 1) Đóng gói ứng dụng + Python + thư viện (có cả bộ điều khiển trình duyệt của Playwright)
pyinstaller --noconfirm --clean --windowed --name $name `
  --collect-all playwright --hidden-import PIL.Image main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller lỗi" }

# 2) Tải Chromium vào thư mục ms-playwright cạnh file .exe
$env:PLAYWRIGHT_BROWSERS_PATH = Join-Path (Resolve-Path $dist).Path "ms-playwright"
python -m playwright install chromium
if ($LASTEXITCODE -ne 0) { throw "Tải Chromium lỗi" }

# 3) File cấu hình + hướng dẫn đi kèm
Copy-Item config.json, urls_mau.txt, README.md $dist
Copy-Item packaging\HUONG_DAN_SU_DUNG.txt $dist

if (-not $SkipZip) {
  $zip = "dist\$name-windows.zip"
  if (Test-Path $zip) { Remove-Item $zip }
  Compress-Archive -Path $dist -DestinationPath $zip
  Write-Host "Xong: $zip"
}
