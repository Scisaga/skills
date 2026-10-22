param(
  [Parameter(Mandatory = $true)]
  [string]$InputPptx,
  [Parameter(Mandatory = $true)]
  [string]$Pages,
  [Parameter(Mandatory = $true)]
  [string]$Output,
  [ValidateSet("pdf", "png", "jpg")]
  [string]$Format = "pdf",
  [int]$Width = 1600,
  [int]$Height = 900
)

$ErrorActionPreference = "Stop"
$inputPath = [System.IO.Path]::GetFullPath($InputPptx)
$outputPath = [System.IO.Path]::GetFullPath($Output)
if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
  throw "PPTX not found: $inputPath"
}
$pageNumbers = @(
  $Pages.Split(",") |
    ForEach-Object { [int]$_.Trim() }
)
if ($pageNumbers.Count -eq 0 -or ($pageNumbers | Where-Object { $_ -le 0 })) {
  throw "Pages must be a comma-separated list of positive slide numbers."
}

$powerPoint = $null
$source = $null
$temporary = $null
try {
  $powerPoint = New-Object -ComObject PowerPoint.Application
  $powerPoint.Visible = -1
  $source = $powerPoint.Presentations.Open($inputPath, -1, 0, -1)
  foreach ($page in $pageNumbers) {
    if ($page -gt $source.Slides.Count) {
      throw "Slide $page exceeds slide count $($source.Slides.Count)."
    }
  }

  if ($Format -eq "pdf") {
    $outputDir = Split-Path -Parent $outputPath
    [System.IO.Directory]::CreateDirectory($outputDir) | Out-Null
    $temporary = $powerPoint.Presentations.Add(0)
    foreach ($page in $pageNumbers) {
      $source.Slides.Item($page).Copy()
      [void]$temporary.Slides.Paste()
    }
    # ppSaveAsPDF = 32. SaveAs is more reliable than calling the long
    # ExportAsFixedFormat COM overload from Windows PowerShell 5.1.
    $temporary.SaveAs($outputPath, 32)
  }
  else {
    [System.IO.Directory]::CreateDirectory($outputPath) | Out-Null
    $filter = if ($Format -eq "png") { "PNG" } else { "JPG" }
    foreach ($page in $pageNumbers) {
      $target = Join-Path $outputPath (
        "slide-{0:D2}.{1}" -f $page, $Format
      )
      $source.Slides.Item($page).Export(
        $target,
        $filter,
        $Width,
        $Height
      )
    }
  }
  Write-Output "OK exported slides $Pages to $outputPath"
}
finally {
  if ($temporary) {
    try { $temporary.Close() } catch {}
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject(
      $temporary
    )
  }
  if ($source) {
    try { $source.Close() } catch {}
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject($source)
  }
  if ($powerPoint) {
    try { $powerPoint.Quit() } catch {}
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject(
      $powerPoint
    )
  }
  [GC]::Collect()
  [GC]::WaitForPendingFinalizers()
}
