$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillRoot = Resolve-Path (Join-Path $ScriptDir "..")

if (Get-Command ffmpeg -ErrorAction SilentlyContinue -and Get-Command ffprobe -ErrorAction SilentlyContinue) {
  Write-Host "ffmpeg 已存在于 PATH，跳过安装。"
  exit 0
}

if (Get-Command winget -ErrorAction SilentlyContinue) {
  winget install --accept-source-agreements --accept-package-agreements Gyan.FFmpeg
  exit 0
}

if (Get-Command choco -ErrorAction SilentlyContinue) {
  choco install ffmpeg -y
  exit 0
}

if (Get-Command scoop -ErrorAction SilentlyContinue) {
  scoop install ffmpeg
  exit 0
}

$arch = $env:PROCESSOR_ARCHITECTURE
switch ($arch) {
  "AMD64" { $TargetDir = Join-Path $SkillRoot ".cache/ffmpeg/windows-x64" }
  "ARM64" { $TargetDir = Join-Path $SkillRoot ".cache/ffmpeg/windows-arm64" }
  default { throw "暂不支持的 Windows 架构: $arch" }
}

$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) ("video-ffmpeg-" + [System.Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempDir | Out-Null

$ZipPath = Join-Path $TempDir "ffmpeg.zip"
$Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
Write-Host "下载 FFmpeg: $Url"
Invoke-WebRequest -Uri $Url -OutFile $ZipPath
Expand-Archive -Path $ZipPath -DestinationPath $TempDir -Force

$ExtractedDir = Get-ChildItem -Path $TempDir -Directory | Where-Object { $_.Name -like "ffmpeg-*" } | Select-Object -First 1
if (-not $ExtractedDir) {
  throw "未找到解压后的 FFmpeg 目录。"
}

if (Test-Path $TargetDir) {
  Remove-Item -Recurse -Force $TargetDir
}
New-Item -ItemType Directory -Path $TargetDir | Out-Null
Copy-Item -Path (Join-Path $ExtractedDir.FullName "*") -Destination $TargetDir -Recurse -Force

Write-Host "FFmpeg 已安装到 $TargetDir"
Remove-Item -Recurse -Force $TempDir
