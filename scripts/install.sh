#!/bin/sh
# install.sh — one-shot installer for Raspy on Linux & macOS.
#
#   curl -fsSL https://raw.githubusercontent.com/vardhin/raspy/master/scripts/install.sh | sh
#
# WHAT THE USER NEEDS INSTALLED: nothing but a POSIX shell and curl-or-wget
# (both ship on every mainstream Linux and macOS). No Python, no Node, no uv —
# Raspy ships as ONE self-contained binary (see backend/raspy.spec). This script
# only downloads it, verifies its checksum, sets up the first admin account and
# Web Push keys, and registers a boot service.
#
# Idempotent: if Raspy is already installed, it shows a menu — update / uninstall
# / cancel — instead of blindly reinstalling.
#
# Override points (env vars):
#   RASPY_REPO        GitHub owner/repo            (default vardhin/raspy)
#   RASPY_VERSION     tag to install, e.g. v1.2.3 (default: latest release)
#   RASPY_PREFIX      where the binary goes        (default /usr/local/bin, ~/.local/bin if no root)
#   RASPY_DATA_DIR    data dir                     (default per-OS, see below)
#   RASPY_PORT        listen port                  (default 49317)
#   RASPY_NONINTERACTIVE=1  fail instead of prompting (CI/automation)

set -eu

REPO="${RASPY_REPO:-vardhin/raspy}"
PORT="${RASPY_PORT:-49317}"
SERVICE_NAME="raspy"
# Bold/colors only on a tty.
if [ -t 1 ]; then B="$(printf '\033[1m')"; G="$(printf '\033[32m')"; Y="$(printf '\033[33m')"; R="$(printf '\033[31m')"; N="$(printf '\033[0m')"; else B=""; G=""; Y=""; R=""; N=""; fi

say()  { printf '%s==>%s %s\n' "$G" "$N" "$1"; }
warn() { printf '%s!! %s%s\n' "$Y" "$1" "$N" >&2; }
die()  { printf '%serror:%s %s\n' "$R" "$N" "$1" >&2; exit 1; }

# Where to read interactive input. When piped (curl | sh) stdin IS the script,
# so prompts must come from the controlling terminal. If there's no tty at all
# (true CI / nested pipe), mark non-interactive and use defaults rather than hang
# or crash on a missing /dev/tty.
TTY=""
if [ "${RASPY_NONINTERACTIVE:-0}" != "1" ]; then
  if [ -r /dev/tty ] && [ -w /dev/tty ]; then TTY="/dev/tty";
  elif [ -t 0 ]; then TTY="/proc/self/fd/0";
  else
    warn "no interactive terminal; proceeding non-interactively with defaults"
    RASPY_NONINTERACTIVE=1
  fi
fi

ask()  { # ask "prompt" "default"; echoes answer
  if [ "${RASPY_NONINTERACTIVE:-0}" = "1" ]; then printf '%s' "$2"; return; fi
  printf '%s%s%s ' "$B" "$1" "$N" > "$TTY"
  read -r _ans < "$TTY" || _ans=""
  [ -n "$_ans" ] && printf '%s' "$_ans" || printf '%s' "$2"
}

# ── Platform detection ───────────────────────────────────────────────────────
detect_platform() {
  os="$(uname -s)"; arch="$(uname -m)"
  case "$os" in
    Linux)  OS_NAME="linux" ;;
    Darwin) OS_NAME="macos" ;;
    *) die "unsupported OS: $os (this installer covers Linux and macOS; use install.ps1 on Windows)" ;;
  esac
  case "$arch" in
    x86_64|amd64)  ARCH="x64" ;;
    aarch64|arm64) ARCH="arm64" ;;
    armv7l|armv6l) die "32-bit ARM is not built; a 64-bit OS is required (most Raspberry Pi OS 64-bit works)" ;;
    *) die "unsupported arch: $arch" ;;
  esac
  ASSET="raspy-${OS_NAME}-${ARCH}"
  say "platform: ${OS_NAME}-${ARCH}"
}

# ── Paths ────────────────────────────────────────────────────────────────────
resolve_paths() {
  if [ -n "${RASPY_PREFIX:-}" ]; then
    PREFIX="$RASPY_PREFIX"
  elif [ "$(id -u)" = "0" ]; then
    PREFIX="/usr/local/bin"
  elif [ -w /usr/local/bin ] 2>/dev/null; then
    PREFIX="/usr/local/bin"
  else
    PREFIX="$HOME/.local/bin"
  fi
  BIN="$PREFIX/raspy"

  if [ -n "${RASPY_DATA_DIR:-}" ]; then
    DATA_DIR="$RASPY_DATA_DIR"
  elif [ "$OS_NAME" = "macos" ]; then
    DATA_DIR="$HOME/Library/Application Support/raspy"
  else
    DATA_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/raspy"
  fi
}

# ── Downloader (curl or wget, whichever exists) ──────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }
fetch() { # fetch URL OUTFILE
  if have curl; then curl -fsSL "$1" -o "$2";
  elif have wget; then wget -qO "$2" "$1";
  else die "need curl or wget to download"; fi
}
fetch_stdout() { # fetch URL -> stdout
  if have curl; then curl -fsSL "$1";
  elif have wget; then wget -qO- "$1";
  else die "need curl or wget to download"; fi
}

sha256_check() { # sha256_check FILE EXPECTED_HEX
  _file="$1"; _want="$2"
  if have sha256sum; then _got="$(sha256sum "$_file" | awk '{print $1}')"
  elif have shasum;   then _got="$(shasum -a 256 "$_file" | awk '{print $1}')"
  else warn "no sha256 tool found; skipping checksum verification"; return 0; fi
  [ "$_got" = "$_want" ] || die "checksum mismatch for $_file (got $_got want $_want)"
}

# ── Resolve the release + asset URLs ─────────────────────────────────────────
resolve_release() {
  if [ -n "${RASPY_VERSION:-}" ]; then
    TAG="$RASPY_VERSION"; BASE="https://github.com/$REPO/releases/download/$TAG"
  else
    BASE="https://github.com/$REPO/releases/latest/download"; TAG="latest"
  fi
  ASSET_URL="$BASE/$ASSET"
  SUMS_URL="$BASE/SHA256SUMS"
}

# ── Download + verify the binary ─────────────────────────────────────────────
download_binary() {
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  say "downloading $ASSET ($TAG)…"
  fetch "$ASSET_URL" "$TMP/raspy" || die "download failed ($ASSET_URL). Does a release exist for this platform?"
  if fetch "$SUMS_URL" "$TMP/SHA256SUMS" 2>/dev/null; then
    want="$(grep " $ASSET\$" "$TMP/SHA256SUMS" | awk '{print $1}' | head -n1)"
    if [ -n "$want" ]; then say "verifying checksum…"; sha256_check "$TMP/raspy" "$want"; else warn "no checksum entry for $ASSET; skipping"; fi
  else
    warn "could not fetch SHA256SUMS; skipping verification"
  fi
  chmod +x "$TMP/raspy"
}

install_binary() {
  say "installing to $BIN"
  mkdir -p "$PREFIX"
  if [ -w "$PREFIX" ]; then mv "$TMP/raspy" "$BIN";
  elif have sudo; then sudo mv "$TMP/raspy" "$BIN";
  else die "no write access to $PREFIX and no sudo; set RASPY_PREFIX to a writable dir"; fi
}

# ── First-run setup: VAPID keys + admin account ──────────────────────────────
first_run_setup() {
  mkdir -p "$DATA_DIR"
  # Already set up? (an account db exists) → skip.
  if [ -f "$DATA_DIR/raspy.sqlite3" ] && [ -f "$DATA_DIR/auth_secret" ]; then
    say "existing data dir found at $DATA_DIR — keeping accounts, skipping setup"
    return
  fi

  say "generating Web Push (VAPID) keys…"
  RASPY_DATA_DIR="$DATA_DIR" "$BIN" vapid --write >/dev/null || warn "VAPID key generation failed (push will be off until fixed)"

  say "create the first admin account"
  if [ "${RASPY_NONINTERACTIVE:-0}" = "1" ]; then
    [ -n "${RASPY_ADMIN_USER:-}" ] && [ -n "${RASPY_ADMIN_PASS:-}" ] && [ -n "${RASPY_ADMIN_PIN:-}" ] \
      || die "non-interactive: set RASPY_ADMIN_USER / RASPY_ADMIN_PASS / RASPY_ADMIN_PIN"
    printf '%s\n%s\n%s\n' "$RASPY_ADMIN_USER" "$RASPY_ADMIN_PASS" "$RASPY_ADMIN_PIN" \
      | RASPY_DATA_DIR="$DATA_DIR" "$BIN" auth create-account --stdin
    return
  fi

  user="$(ask 'admin username:' 'admin')"
  pass="$(prompt_secret 'admin password')"
  pin="$(prompt_secret 'mini-PIN (numeric is fine)')"
  printf '%s\n%s\n%s\n' "$user" "$pass" "$pin" \
    | RASPY_DATA_DIR="$DATA_DIR" "$BIN" auth create-account --stdin \
    || die "account creation failed"
}

prompt_secret() { # prompt_secret "label" -> echoes value (no echo to screen)
  _label="$1"
  while :; do
    printf '%s%s:%s ' "$B" "$_label" "$N" >/dev/tty
    stty -echo </dev/tty 2>/dev/null || true
    read -r _v </dev/tty; stty echo </dev/tty 2>/dev/null || true; printf '\n' >/dev/tty
    printf '%s (again):%s ' "$B" "$N" >/dev/tty
    stty -echo </dev/tty 2>/dev/null || true
    read -r _v2 </dev/tty; stty echo </dev/tty 2>/dev/null || true; printf '\n' >/dev/tty
    [ -n "$_v" ] || { warn "empty; try again"; continue; }
    [ "$_v" = "$_v2" ] || { warn "did not match; try again"; continue; }
    printf '%s' "$_v"; return
  done
}

# ── Boot service (systemd / launchd) ─────────────────────────────────────────
install_service_linux() {
  if ! have systemctl; then warn "systemd not found; skipping boot service. Run manually: $BIN serve"; return; fi
  if [ "$(id -u)" = "0" ]; then
    unit="/etc/systemd/system/${SERVICE_NAME}.service"; SCOPE="system"; sysctl="systemctl"
  else
    mkdir -p "$HOME/.config/systemd/user"; unit="$HOME/.config/systemd/user/${SERVICE_NAME}.service"; SCOPE="user"; sysctl="systemctl --user"
  fi
  say "installing systemd ($SCOPE) unit → $unit"
  cat > "$unit" <<EOF
[Unit]
Description=Raspy spine — personal control plane
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=RASPY_DATA_DIR=$DATA_DIR
Environment=RASPY_PORT=$PORT
ExecStart=$BIN serve
Restart=always
RestartSec=3
TimeoutStartSec=120

[Install]
WantedBy=$( [ "$SCOPE" = system ] && echo multi-user.target || echo default.target )
EOF
  $sysctl daemon-reload
  $sysctl enable --now "$SERVICE_NAME" 2>/dev/null || $sysctl restart "$SERVICE_NAME"
  [ "$SCOPE" = user ] && have loginctl && loginctl enable-linger "$(id -un)" 2>/dev/null || true
  say "service started; logs: ${B}$sysctl status $SERVICE_NAME${N} / journalctl"
}

install_service_macos() {
  plist="$HOME/Library/LaunchAgents/com.raspy.spine.plist"
  mkdir -p "$HOME/Library/LaunchAgents"
  say "installing launchd agent → $plist"
  cat > "$plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.raspy.spine</string>
  <key>ProgramArguments</key><array><string>$BIN</string><string>serve</string></array>
  <key>EnvironmentVariables</key><dict>
    <key>RASPY_DATA_DIR</key><string>$DATA_DIR</string>
    <key>RASPY_PORT</key><string>$PORT</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
EOF
  launchctl unload "$plist" 2>/dev/null || true
  launchctl load "$plist" && say "service loaded (launchctl)"
}

install_service() {
  ans="$(ask 'start Raspy automatically on boot? [Y/n]' 'Y')"
  case "$ans" in
    n|N|no|NO) warn "skipping boot service. Start it yourself with: $BIN serve"; return ;;
  esac
  if [ "$OS_NAME" = "linux" ]; then install_service_linux; else install_service_macos; fi
}

# ── Uninstall ────────────────────────────────────────────────────────────────
do_uninstall() {
  say "uninstalling Raspy"
  # Stop + remove services.
  if [ "$OS_NAME" = "linux" ] && have systemctl; then
    for scope in "--user" ""; do
      systemctl $scope stop "$SERVICE_NAME" 2>/dev/null || true
      systemctl $scope disable "$SERVICE_NAME" 2>/dev/null || true
    done
    rm -f "$HOME/.config/systemd/user/${SERVICE_NAME}.service" 2>/dev/null || true
    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
      if [ -w /etc/systemd/system ]; then rm -f "/etc/systemd/system/${SERVICE_NAME}.service"; elif have sudo; then sudo rm -f "/etc/systemd/system/${SERVICE_NAME}.service"; fi
    fi
    systemctl --user daemon-reload 2>/dev/null || true
    say "removed systemd unit(s)"
  elif [ "$OS_NAME" = "macos" ]; then
    plist="$HOME/Library/LaunchAgents/com.raspy.spine.plist"
    launchctl unload "$plist" 2>/dev/null || true; rm -f "$plist"; say "removed launchd agent"
  fi
  # Remove the binary.
  if [ -f "$BIN" ]; then
    if [ -w "$(dirname "$BIN")" ]; then rm -f "$BIN"; elif have sudo; then sudo rm -f "$BIN"; fi
    say "removed binary $BIN"
  fi
  # Data dir holds ACCOUNTS, vault, mail creds — never delete without consent.
  if [ -d "$DATA_DIR" ]; then
    ans="$(ask "also delete ALL data (accounts, vault, notes) at $DATA_DIR? [y/N]" 'N')"
    case "$ans" in
      y|Y|yes|YES) rm -rf "$DATA_DIR"; say "deleted data dir" ;;
      *) say "kept your data at $DATA_DIR (a future reinstall will reuse it)" ;;
    esac
  fi
  say "${B}Raspy uninstalled.${N}"
}

# ── Detect existing install → menu ───────────────────────────────────────────
maybe_existing_menu() {
  [ -f "$BIN" ] || return 0   # fresh install, proceed
  cur="$("$BIN" version 2>/dev/null || echo '?')"
  say "found an existing Raspy install ($BIN, v$cur)"
  if [ "${RASPY_NONINTERACTIVE:-0}" = "1" ]; then say "non-interactive: reinstalling/updating in place"; return 0; fi
  printf '%s\n' "  ${B}1${N}) update / reinstall to latest"
  printf '%s\n' "  ${B}2${N}) uninstall"
  printf '%s\n' "  ${B}3${N}) cancel"
  choice="$(ask 'choose [1/2/3]:' '3')"
  case "$choice" in
    1) say "updating…"; return 0 ;;
    2) do_uninstall; exit 0 ;;
    *) say "cancelled."; exit 0 ;;
  esac
}

main() {
  printf '%s\n' "${B}Raspy installer${N}"
  detect_platform
  resolve_paths
  maybe_existing_menu
  resolve_release
  download_binary
  install_binary
  first_run_setup
  install_service
  echo
  say "${B}Done.${N} Raspy is at ${B}http://127.0.0.1:$PORT${N}"
  say "binary: $BIN   data: $DATA_DIR"
  case ":$PATH:" in *":$PREFIX:"*) : ;; *) warn "$PREFIX is not on your PATH; add it to run 'raspy' directly";; esac
}

main "$@"
