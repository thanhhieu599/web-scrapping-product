# Chạy thử file .exe đã đóng gói trên trang mô phỏng (chế độ chỉ cào, không cần Sapo).
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$app = Resolve-Path "dist\DT-Sapo-Importer"

$srv = Start-Process python -ArgumentList "-m", "http.server", "8765", "--directory", "tests\mock_site" -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 3
try {
  $p = Start-Process "$app\DT-Sapo-Importer.exe" -ArgumentList "--url", "http://127.0.0.1:8765/san-pham/", "--dry-run" `
        -WorkingDirectory $app -PassThru -Wait
  if (Test-Path "$app\nhat_ky.log") { Get-Content "$app\nhat_ky.log" -Encoding UTF8 }
  $json = "$app\output\48-22-8450\product.json"
  if ($p.ExitCode -ne 0 -or -not (Test-Path $json)) { throw "Smoke test THẤT BẠI (exit $($p.ExitCode))" }
  $d = Get-Content $json -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($d.price -ne 2940000 -or $d.image_files.Count -ne 3) { throw "Dữ liệu sai: giá $($d.price), ảnh $($d.image_files.Count)" }
  Write-Host "Smoke test ĐẠT: $($d.name) | $($d.sku) | $($d.price) | $($d.image_files.Count) ảnh"
} finally {
  Stop-Process -Id $srv.Id -Force -ErrorAction SilentlyContinue
  Remove-Item "$app\output", "$app\nhat_ky.log" -Recurse -Force -ErrorAction SilentlyContinue
}
