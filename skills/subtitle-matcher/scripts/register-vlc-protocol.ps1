param(
  [switch]$Unregister
)

$ErrorActionPreference = "Stop"

$Protocol = "vlcfile"
$ProtocolKey = "HKCU:\Software\Classes\$Protocol"
$HandlerPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "open-vlc-url.ps1")).Path

function Ensure-RegistryKey {
  param([Parameter(Mandatory = $true)][string]$Path)
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -Path $Path -Force | Out-Null
  }
}

function Resolve-VlcIcon {
  foreach ($envName in @("VLC_BIN", "VLC_EXE")) {
    $value = [Environment]::GetEnvironmentVariable($envName)
    if ((-not [string]::IsNullOrWhiteSpace($value)) -and (Test-Path -LiteralPath $value -PathType Leaf)) {
      return (Resolve-Path -LiteralPath $value).Path
    }
  }

  foreach ($base in @(
      [Environment]::GetEnvironmentVariable("ProgramFiles"),
      [Environment]::GetEnvironmentVariable("ProgramFiles(x86)")
    )) {
    if ([string]::IsNullOrWhiteSpace($base)) {
      continue
    }
    $candidate = Join-Path $base "VideoLAN\VLC\vlc.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
      return (Resolve-Path -LiteralPath $candidate).Path
    }
  }

  $command = Get-Command "vlc.exe" -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }
  return "vlc.exe"
}

if ($Unregister) {
  if (Test-Path -LiteralPath $ProtocolKey) {
    Remove-Item -LiteralPath $ProtocolKey -Recurse -Force
    Write-Output "Unregistered $Protocol protocol from HKCU."
  }
  else {
    Write-Output "$Protocol protocol is not registered in HKCU."
  }
  exit 0
}

$powerShellExe = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
if (-not (Test-Path -LiteralPath $powerShellExe -PathType Leaf)) {
  $powerShellExe = (Get-Command "powershell.exe" -ErrorAction Stop).Source
}

$commandValue = '"' + $powerShellExe + '" -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $HandlerPath + '" "%1"'
$iconValue = (Resolve-VlcIcon) + ",0"

Ensure-RegistryKey $ProtocolKey
Set-Item -LiteralPath $ProtocolKey -Value "URL:VLC File Protocol"
New-ItemProperty -LiteralPath $ProtocolKey -Name "URL Protocol" -Value "" -PropertyType String -Force | Out-Null

$iconKey = Join-Path $ProtocolKey "DefaultIcon"
Ensure-RegistryKey $iconKey
Set-Item -LiteralPath $iconKey -Value $iconValue

$commandKey = Join-Path $ProtocolKey "shell\open\command"
Ensure-RegistryKey $commandKey
Set-Item -LiteralPath $commandKey -Value $commandValue

Write-Output "Registered $Protocol protocol for current user."
Write-Output "Handler: $HandlerPath"
