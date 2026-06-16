# install.ps1 — one-shot installer for Raspy on Windows.
#
#   irm https://raw.githubusercontent.com/vardhin/raspy/master/scripts/install.ps1 | iex
#
# WHAT THE USER NEEDS INSTALLED: nothing but Windows PowerShell 5+ (ships with
# Windows). No Python, no Node — Raspy is one self-contained .exe. This script
# downloads it, verifies its checksum, creates the first admin account + Web Push
# keys, and registers a service that starts at boot.
#
# Idempotent: if Raspy is already installed it shows a menu (update / uninstall /
# cancel) instead of reinstalling blindly.
#
# Override via env vars: RASPY_REPO, RASPY_VERSION, RASPY_PREFIX, RASPY_DATA_DIR,
# RASPY_PORT, RASPY_NONINTERACTIVE=1 (+ RASPY_ADMIN_USER/PASS/PIN for unattended).

$ErrorActionPreference = 'Stop'

$Repo    = if ($env:RASPY_REPO)    { $env:RASPY_REPO }    else { 'vardhin/raspy' }
$Port    = if ($env:RASPY_PORT)    { $env:RASPY_PORT }    else { '49317' }
$Service = 'Raspy'
$NonInteractive = ($env:RASPY_NONINTERACTIVE -eq '1')

function Say  ($m) { Write-Host "==> $m" -ForegroundColor Green }
function Warn ($m) { Write-Host "!! $m"  -ForegroundColor Yellow }
function Die  ($m) { Write-Host "error: $m" -ForegroundColor Red; exit 1 }
function Ask  ($prompt, $default) {
  if ($NonInteractive) { return $default }
  $a = Read-Host $prompt
  if ([string]::IsNullOrWhiteSpace($a)) { return $default } else { return $a }
}

# ── Platform ─────────────────────────────────────────────────────────────────
$arch = if ([Environment]::Is64BitOperatingSystem) {
  if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') { 'arm64' } else { 'x64' }
} else { Die '32-bit Windows is not supported' }
# We currently build windows-x64; arm64 falls back to x64 emulation.
$assetArch = if ($arch -eq 'arm64') { 'x64' } else { $arch }
$Asset = "raspy-windows-$assetArch.exe"
Say "platform: windows-$arch (asset: $Asset)"

# ── Paths ────────────────────────────────────────────────────────────────────
$Prefix  = if ($env:RASPY_PREFIX)   { $env:RASPY_PREFIX }   else { Join-Path $env:LOCALAPPDATA 'Programs\Raspy' }
$Bin     = Join-Path $Prefix 'raspy.exe'
$DataDir = if ($env:RASPY_DATA_DIR) { $env:RASPY_DATA_DIR } else { Join-Path $env:APPDATA 'raspy' }

# ── Release URLs ─────────────────────────────────────────────────────────────
if ($env:RASPY_VERSION) {
  $base = "https://github.com/$Repo/releases/download/$($env:RASPY_VERSION)"; $tag = $env:RASPY_VERSION
} else {
  $base = "https://github.com/$Repo/releases/latest/download"; $tag = 'latest'
}
$AssetUrl = "$base/$Asset"
$SumsUrl  = "$base/SHA256SUMS"

# ── Service helpers ──────────────────────────────────────────────────────────
function Get-RaspySvc { Get-Service -Name $Service -ErrorAction SilentlyContinue }

function Install-Service {
  $ans = Ask 'Start Raspy automatically on boot? [Y/n]' 'Y'
  if ($ans -match '^(n|no)$') { Warn "skipping service; run it yourself: `"$Bin`" serve"; return }

  # A wrapper .cmd carries the env (data dir + port) since Windows services don't
  # take inline env the way systemd does.
  $cmd = Join-Path $Prefix 'raspy-service.cmd'
  @"
@echo off
set RASPY_DATA_DIR=$DataDir
set RASPY_PORT=$Port
"$Bin" serve
"@ | Set-Content -Path $cmd -Encoding ASCII

  if (Get-RaspySvc) { sc.exe stop $Service | Out-Null; sc.exe delete $Service | Out-Null; Start-Sleep 1 }
  # binPath wraps the .cmd via cmd.exe so the env is set before launch.
  $binPath = "cmd.exe /c `"$cmd`""
  sc.exe create $Service binPath= $binPath start= auto DisplayName= "Raspy spine" | Out-Null
  sc.exe description $Service "Raspy — personal control plane" | Out-Null
  sc.exe start $Service | Out-Null
  Say "service '$Service' installed and started (auto-start on boot)"
}

# ── Download + verify ────────────────────────────────────────────────────────
function Download-Binary {
  $tmp = Join-Path $env:TEMP ("raspy-" + [Guid]::NewGuid().ToString('N'))
  New-Item -ItemType Directory -Path $tmp | Out-Null
  $script:TmpExe = Join-Path $tmp 'raspy.exe'
  Say "downloading $Asset ($tag)…"
  try { Invoke-WebRequest -Uri $AssetUrl -OutFile $script:TmpExe -UseBasicParsing }
  catch { Die "download failed ($AssetUrl). Does a release exist for this platform?" }

  try {
    $sums = (Invoke-WebRequest -Uri $SumsUrl -UseBasicParsing).Content
    $want = ($sums -split "`n" | Where-Object { $_ -match "\s$([Regex]::Escape($Asset))$" } |
             ForEach-Object { ($_ -split '\s+')[0] } | Select-Object -First 1)
    if ($want) {
      Say 'verifying checksum…'
      $got = (Get-FileHash -Algorithm SHA256 -Path $script:TmpExe).Hash.ToLower()
      if ($got -ne $want.ToLower()) { Die "checksum mismatch (got $got want $want)" }
    } else { Warn "no checksum entry for $Asset; skipping" }
  } catch { Warn 'could not fetch SHA256SUMS; skipping verification' }
}

function Install-Binary {
  Say "installing to $Bin"
  New-Item -ItemType Directory -Force -Path $Prefix | Out-Null
  Move-Item -Force -Path $script:TmpExe -Destination $Bin
}

# ── First-run setup ──────────────────────────────────────────────────────────
function First-Run-Setup {
  New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
  if ((Test-Path (Join-Path $DataDir 'raspy.sqlite3')) -and (Test-Path (Join-Path $DataDir 'auth_secret'))) {
    Say "existing data dir at $DataDir — keeping accounts, skipping setup"; return
  }

  Say 'generating Web Push (VAPID) keys…'
  $env:RASPY_DATA_DIR = $DataDir
  & $Bin vapid --write | Out-Null

  Say 'create the first admin account'
  if ($NonInteractive) {
    if (-not ($env:RASPY_ADMIN_USER -and $env:RASPY_ADMIN_PASS -and $env:RASPY_ADMIN_PIN)) {
      Die 'non-interactive: set RASPY_ADMIN_USER / RASPY_ADMIN_PASS / RASPY_ADMIN_PIN'
    }
    $u = $env:RASPY_ADMIN_USER; $p = $env:RASPY_ADMIN_PASS; $pin = $env:RASPY_ADMIN_PIN
  } else {
    $u = Ask 'admin username:' 'admin'
    $p   = Read-Secret 'admin password'
    $pin = Read-Secret 'mini-PIN (numeric is fine)'
  }
  # Pipe username\npassword\npin into `auth create-account --stdin`.
  $payload = "$u`n$p`n$pin`n"
  $payload | & $Bin auth create-account --stdin
  if ($LASTEXITCODE -ne 0) { Die 'account creation failed' }
}

function Read-Secret ($label) {
  while ($true) {
    $s1 = Read-Host -AsSecureString "$label"
    $s2 = Read-Host -AsSecureString "$label (again)"
    $p1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s1))
    $p2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s2))
    if ([string]::IsNullOrEmpty($p1)) { Warn 'empty; try again'; continue }
    if ($p1 -ne $p2) { Warn 'did not match; try again'; continue }
    return $p1
  }
}

# ── Uninstall ────────────────────────────────────────────────────────────────
function Do-Uninstall {
  Say 'uninstalling Raspy'
  if (Get-RaspySvc) {
    sc.exe stop $Service | Out-Null
    sc.exe delete $Service | Out-Null
    Say "removed service '$Service'"
  }
  Remove-Item -Force -ErrorAction SilentlyContinue (Join-Path $Prefix 'raspy-service.cmd')
  if (Test-Path $Bin) { Remove-Item -Force $Bin; Say "removed $Bin" }
  if (Test-Path $DataDir) {
    $ans = Ask "Also delete ALL data (accounts, vault, notes) at $DataDir? [y/N]" 'N'
    if ($ans -match '^(y|yes)$') { Remove-Item -Recurse -Force $DataDir; Say 'deleted data dir' }
    else { Say "kept your data at $DataDir (a future reinstall will reuse it)" }
  }
  Say 'Raspy uninstalled.'
}

# ── Existing-install menu ────────────────────────────────────────────────────
function Maybe-Existing-Menu {
  if (-not (Test-Path $Bin)) { return }
  $cur = (& $Bin version) 2>$null
  Say "found an existing Raspy install ($Bin, v$cur)"
  if ($NonInteractive) { Say 'non-interactive: updating in place'; return }
  Write-Host '  1) update / reinstall to latest'
  Write-Host '  2) uninstall'
  Write-Host '  3) cancel'
  switch (Ask 'choose [1/2/3]:' '3') {
    '1' { Say 'updating…' }
    '2' { Do-Uninstall; exit 0 }
    default { Say 'cancelled.'; exit 0 }
  }
}

# ── Main ─────────────────────────────────────────────────────────────────────
Write-Host 'Raspy installer' -ForegroundColor Cyan
Maybe-Existing-Menu
Download-Binary
Install-Binary
First-Run-Setup
Install-Service
Write-Host ''
Say "Done. Raspy is at http://127.0.0.1:$Port"
Say "binary: $Bin   data: $DataDir"
