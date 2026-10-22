param()

$ErrorActionPreference = "Stop"
if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
  & ffmpeg -version | Select-Object -First 1
  exit 0
}

if (Get-Command winget -ErrorAction SilentlyContinue) {
  & winget install --exact --id Gyan.FFmpeg `
    --accept-package-agreements --accept-source-agreements
} elseif (Get-Command choco -ErrorAction SilentlyContinue) {
  & choco install ffmpeg -y
} elseif (Get-Command scoop -ErrorAction SilentlyContinue) {
  & scoop install ffmpeg
} else {
  throw "No supported package manager found. Install FFmpeg from https://ffmpeg.org/download.html"
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
  Write-Host "FFmpeg was installed but is not visible in this PowerShell session."
  Write-Host "Open a new terminal, run 'ffmpeg -version', then rerun export-video."
  exit 0
}
& ffmpeg -version | Select-Object -First 1
