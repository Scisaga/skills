param(
  [Parameter(Mandatory = $true, Position = 0)]
  [string]$Uri,

  [switch]$PrintOnly
)

$ErrorActionPreference = "Stop"

function Show-LaunchError {
  param([string]$Message)

  try {
    Add-Type -AssemblyName System.Windows.Forms
    [System.Windows.Forms.MessageBox]::Show(
      $Message,
      "VLC Launch Failed",
      [System.Windows.Forms.MessageBoxButtons]::OK,
      [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
  }
  catch {
    Write-Error $Message
  }
}

function Decode-Base64Url {
  param([Parameter(Mandatory = $true)][string]$Value)

  $normalized = $Value.Replace("-", "+").Replace("_", "/")
  switch ($normalized.Length % 4) {
    0 { }
    2 { $normalized += "==" }
    3 { $normalized += "=" }
    default { throw "Invalid base64url value." }
  }

  return [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($normalized))
}

function Get-QueryParams {
  param([Parameter(Mandatory = $true)][System.Uri]$ParsedUri)

  $params = @{}
  $query = $ParsedUri.Query
  if ([string]::IsNullOrWhiteSpace($query)) {
    return $params
  }

  foreach ($part in $query.TrimStart("?").Split("&")) {
    if ([string]::IsNullOrWhiteSpace($part)) {
      continue
    }
    $pair = $part.Split("=", 2)
    if ($pair.Count -ne 2) {
      continue
    }
    $key = [System.Net.WebUtility]::UrlDecode($pair[0])
    $value = [System.Net.WebUtility]::UrlDecode($pair[1])
    $params[$key] = $value
  }
  return $params
}

function Resolve-VlcPath {
  $candidates = @()
  foreach ($envName in @("VLC_BIN", "VLC_EXE")) {
    $value = [Environment]::GetEnvironmentVariable($envName)
    if (-not [string]::IsNullOrWhiteSpace($value)) {
      $candidates += $value
    }
  }

  $programFiles = [Environment]::GetEnvironmentVariable("ProgramFiles")
  if (-not [string]::IsNullOrWhiteSpace($programFiles)) {
    $candidates += (Join-Path $programFiles "VideoLAN\VLC\vlc.exe")
  }
  $programFilesX86 = [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
  if (-not [string]::IsNullOrWhiteSpace($programFilesX86)) {
    $candidates += (Join-Path $programFilesX86 "VideoLAN\VLC\vlc.exe")
  }

  foreach ($candidate in $candidates) {
    if ((-not [string]::IsNullOrWhiteSpace($candidate)) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  foreach ($commandName in @("vlc.exe", "vlc")) {
    $command = Get-Command $commandName -ErrorAction SilentlyContinue
    if ($command) {
      return $command.Source
    }
  }

  return $null
}

function Quote-PreviewArg {
  param([string]$Value)
  if ($Value -match '\s') {
    return '"' + $Value.Replace('"', '\"') + '"'
  }
  return $Value
}

function Join-ProcessArguments {
  param([string[]]$Arguments)

  $quoted = foreach ($argument in $Arguments) {
    if ($null -eq $argument) {
      '""'
    }
    elseif ($argument -notmatch '[\s"]') {
      $argument
    }
    else {
      $escaped = $argument -replace '(\\*)"', '$1$1\"'
      $escaped = $escaped -replace '(\\+)$', '$1$1'
      '"' + $escaped + '"'
    }
  }

  return ($quoted -join " ")
}

try {
  $parsed = [System.Uri]$Uri
  if ($parsed.Scheme -ne "vlcfile") {
    throw "Unsupported protocol: $($parsed.Scheme)"
  }

  $params = Get-QueryParams $parsed
  if (-not $params.ContainsKey("path")) {
    throw "Missing video path parameter."
  }

  $videoPath = Decode-Base64Url $params["path"]
  if (-not (Test-Path -LiteralPath $videoPath -PathType Leaf)) {
    throw "Video file does not exist: $videoPath"
  }

  $subtitlePath = $null
  if ($params.ContainsKey("subtitle")) {
    $decodedSubtitle = Decode-Base64Url $params["subtitle"]
    if (Test-Path -LiteralPath $decodedSubtitle -PathType Leaf) {
      $subtitlePath = $decodedSubtitle
    }
  }

  $vlcPath = Resolve-VlcPath
  if (-not $vlcPath) {
    throw "Cannot find VLC. Install VLC or set VLC_BIN to vlc.exe."
  }

  $arguments = [System.Collections.Generic.List[string]]::new()
  [void]$arguments.Add($videoPath)
  if ($subtitlePath) {
    [void]$arguments.Add("--sub-file=$subtitlePath")
  }

  if ($PrintOnly) {
    $preview = @((Quote-PreviewArg $vlcPath)) + ($arguments | ForEach-Object { Quote-PreviewArg $_ })
    Write-Output ($preview -join " ")
    exit 0
  }

  $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
  $startInfo.FileName = $vlcPath
  $startInfo.Arguments = Join-ProcessArguments ($arguments.ToArray())
  $startInfo.UseShellExecute = $false

  [void][System.Diagnostics.Process]::Start($startInfo)
}
catch {
  Show-LaunchError $_.Exception.Message
  exit 1
}
