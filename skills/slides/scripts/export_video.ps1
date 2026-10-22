param(
  [Parameter(Mandatory = $true)]
  [string]$InputPptx,
  [Parameter(Mandatory = $true)]
  [string]$OutputMp4,
  [string]$ReportPath,
  [int]$TimeoutMinutes = 90,
  [int]$VerticalResolution = 1080,
  [int]$FramesPerSecond = 30,
  [int]$Quality = 100
)

$ErrorActionPreference = "Stop"

function Get-OfficeClickToRunIdentity {
  $registryPaths = @(
    "HKLM:\SOFTWARE\Microsoft\Office\ClickToRun\Configuration",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Office\ClickToRun\Configuration"
  )
  foreach ($registryPath in $registryPaths) {
    if (-not (Test-Path -LiteralPath $registryPath)) {
      continue
    }
    try {
      $configuration = Get-ItemProperty -LiteralPath $registryPath
    } catch {
      continue
    }
    return [pscustomobject]@{
      product_release_ids = [string]$configuration.ProductReleaseIds
      version_to_report = [string]$configuration.VersionToReport
      update_channel = [string]$configuration.UpdateChannel
      registry_path = $registryPath
    }
  }
  return [pscustomobject]@{
    product_release_ids = $null
    version_to_report = $null
    update_channel = $null
    registry_path = $null
  }
}

$inputPath = [System.IO.Path]::GetFullPath($InputPptx)
$outputPath = [System.IO.Path]::GetFullPath($OutputMp4)
if (-not (Test-Path -LiteralPath $inputPath -PathType Leaf)) {
  throw "PPTX not found: $inputPath"
}
$outputDir = Split-Path -Parent $outputPath
[System.IO.Directory]::CreateDirectory($outputDir) | Out-Null
if (Test-Path -LiteralPath $outputPath) {
  Remove-Item -LiteralPath $outputPath -Force
}

$powerPoint = $null
$presentation = $null
$started = Get-Date
try {
  $powerPoint = New-Object -ComObject PowerPoint.Application
  $powerPoint.Visible = -1
  $presentation = $powerPoint.Presentations.Open($inputPath, -1, 0, -1)
  $version = [string]$powerPoint.Version
  $build = try { [string]$powerPoint.Build } catch { $null }
  $productCode = try { [string]$powerPoint.ProductCode } catch { $null }
  $officeIdentity = Get-OfficeClickToRunIdentity
  $presentation.CreateVideo(
    $outputPath,
    $true,
    5,
    $VerticalResolution,
    $FramesPerSecond,
    $Quality
  )

  $deadline = (Get-Date).AddMinutes($TimeoutMinutes)
  do {
    Start-Sleep -Seconds 2
    $status = [int]$presentation.CreateVideoStatus
    if ($status -eq 4) {
      throw "PowerPoint video export failed."
    }
    if ((Get-Date) -gt $deadline) {
      throw "PowerPoint video export timed out after $TimeoutMinutes minutes."
    }
  } while ($status -in @(0, 1, 2))

  if ($status -ne 3) {
    throw "Unexpected PowerPoint video export status: $status"
  }
  if (-not (Test-Path -LiteralPath $outputPath -PathType Leaf)) {
    throw "PowerPoint reported completion but did not create $outputPath"
  }
  $item = Get-Item -LiteralPath $outputPath
  if ($item.Length -le 0) {
    throw "PowerPoint created an empty video: $outputPath"
  }
  $report = [ordered]@{
    schema_version = 2
    operation = "powerpoint-create-video"
    input_pptx = $inputPath
    output_mp4 = $outputPath
    output_bytes = $item.Length
    powerpoint_version = $version
    powerpoint_build = $build
    powerpoint_product_code = $productCode
    office_product_release_ids = $officeIdentity.product_release_ids
    office_click_to_run_version = $officeIdentity.version_to_report
    office_update_channel = $officeIdentity.update_channel
    office_identity_source = $officeIdentity.registry_path
    use_timings_and_narrations = $true
    started_at = $started.ToUniversalTime().ToString("o")
    completed_at = (Get-Date).ToUniversalTime().ToString("o")
    status = "exported"
  }
  if ($ReportPath) {
    $reportFile = [System.IO.Path]::GetFullPath($ReportPath)
    [System.IO.Directory]::CreateDirectory(
      (Split-Path -Parent $reportFile)
    ) | Out-Null
    $report | ConvertTo-Json -Depth 6 |
      Set-Content -LiteralPath $reportFile -Encoding UTF8
  }
  $report | ConvertTo-Json -Depth 6
}
finally {
  if ($presentation) {
    try { $presentation.Close() } catch {}
    [void][System.Runtime.InteropServices.Marshal]::FinalReleaseComObject(
      $presentation
    )
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
