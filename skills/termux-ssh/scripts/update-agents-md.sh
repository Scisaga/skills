#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

SSH_PORT=8022
LOGIN_LABEL=root
HOST_LABEL=android
GREEZE_STATUS=unknown
BOOT_APP_VERSION=unknown
FDROID_APP_VERSION=unknown

usage() {
  cat <<'EOF'
Usage: update-agents-md.sh [options]

Create or refresh the managed Android Termux context in ~/AGENTS.md while
preserving any content outside this script's managed markers.

Options:
  --ssh-port PORT             configured SSH port (default: 8022)
  --login-label NAME          cosmetic SSH login label (default: root)
  --host-label NAME           cosmetic prompt host label (default: android)
  --greeze-status STATUS      enabled, disabled, or unknown
  --boot-app-version VERSION  known Termux:Boot Android app version
  --fdroid-version VERSION    known F-Droid client version
  -h, --help                  show this help
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh-port) [[ $# -ge 2 ]] || die "$1 requires a value"; SSH_PORT=$2; shift 2 ;;
    --login-label) [[ $# -ge 2 ]] || die "$1 requires a value"; LOGIN_LABEL=$2; shift 2 ;;
    --host-label) [[ $# -ge 2 ]] || die "$1 requires a value"; HOST_LABEL=$2; shift 2 ;;
    --greeze-status) [[ $# -ge 2 ]] || die "$1 requires a value"; GREEZE_STATUS=$2; shift 2 ;;
    --boot-app-version) [[ $# -ge 2 ]] || die "$1 requires a value"; BOOT_APP_VERSION=$2; shift 2 ;;
    --fdroid-version) [[ $# -ge 2 ]] || die "$1 requires a value"; FDROID_APP_VERSION=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

[[ ${PREFIX:-} == */com.termux/files/usr ]] || die "run this script inside the standard Termux environment"
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || die "SSH port must be numeric"
[[ "$LOGIN_LABEL" =~ ^[A-Za-z0-9._-]+$ ]] || die "login label contains unsupported characters"
[[ "$HOST_LABEL" =~ ^[A-Za-z0-9._-]+$ ]] || die "host label contains unsupported characters"
case "$GREEZE_STATUS" in enabled|disabled|unknown) ;; *) die "greeze status must be enabled, disabled, or unknown" ;; esac

BEGIN_MARKER='<!-- BEGIN android-termux-ssh managed context -->'
END_MARKER='<!-- END android-termux-ssh managed context -->'
TARGET="$HOME/AGENTS.md"
TEMP_DIR=$(mktemp -d "$PREFIX/tmp/android-termux-agents.XXXXXX")
BASE_FILE="$TEMP_DIR/base"
BLOCK_FILE="$TEMP_DIR/block"
FINAL_FILE="$TEMP_DIR/final"

cleanup() {
  [[ -f "$BASE_FILE" ]] && unlink "$BASE_FILE"
  [[ -f "$BLOCK_FILE" ]] && unlink "$BLOCK_FILE"
  [[ -f "$FINAL_FILE" ]] && unlink "$FINAL_FILE"
  rmdir "$TEMP_DIR" 2>/dev/null || true
}
trap cleanup EXIT

termux_info=$(termux-info 2>/dev/null || true)
termux_version=$(sed -n 's/^TERMUX_VERSION=//p' <<<"$termux_info" | head -n 1)
termux_release=$(sed -n 's/^TERMUX_APK_RELEASE=//p' <<<"$termux_info" | head -n 1)
api_app_version=$(sed -n 's/^TERMUX_API_VERSION=//p' <<<"$termux_info" | head -n 1)
manufacturer=$(getprop ro.product.manufacturer 2>/dev/null || true)
model=$(getprop ro.product.model 2>/dev/null || true)
android_release=$(getprop ro.build.version.release 2>/dev/null || true)
android_sdk=$(getprop ro.build.version.sdk 2>/dev/null || true)
abi=$(getprop ro.product.cpu.abi 2>/dev/null || true)

termux_version=${termux_version:-unknown}
termux_release=${termux_release:-unknown}
api_app_version=${api_app_version:-unknown}
manufacturer=${manufacturer:-unknown}
model=${model:-unknown}
android_release=${android_release:-unknown}
android_sdk=${android_sdk:-unknown}
abi=${abi:-unknown}

package_state() {
  if pm path "$1" >/dev/null 2>&1; then printf installed; else printf missing; fi
}

native_version() {
  dpkg-query -W -f='${Version}' "$1" 2>/dev/null || printf missing
}

termux_state=$(package_state com.termux)
api_state=$(package_state com.termux.api)
boot_state=$(package_state com.termux.boot)
fdroid_state=$(package_state org.fdroid.fdroid)
openssh_version=$(native_version openssh)
services_version=$(native_version termux-services)
api_cli_version=$(native_version termux-api)
bash_version=$(native_version bash)
git_version=$(native_version git)
node_version=$(command -v node >/dev/null 2>&1 && node --version 2>/dev/null || printf missing)
npm_version=$(command -v npm >/dev/null 2>&1 && npm --version 2>/dev/null || printf missing)

toml_root_value() {
  local key=$1 file=$2
  [[ -r "$file" ]] || return 0
  awk -F= -v wanted="$key" '
    /^[[:space:]]*\[/ { exit }
    {
      lhs=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", lhs)
      if (lhs == wanted) {
        value=$0
        sub(/^[^=]*=[[:space:]]*/, "", value)
        sub(/[[:space:]]*#.*/, "", value)
        gsub(/^[[:space:]"]+|[[:space:]"]+$/, "", value)
        print value
        exit
      }
    }
  ' "$file"
}

csv_has_entry() {
  local csv=$1 entry=$2
  case ",$csv," in
    *,"$entry",*) return 0 ;;
    *) return 1 ;;
  esac
}

codex_version=missing
codex_auth_state='not logged in'
codex_install_state=unknown
codex_sandbox_mode=default
codex_approval_policy=default
codex_network_state=missing
if command -v codex >/dev/null 2>&1; then
  codex_version=$(codex --version 2>/dev/null | head -n 1 || printf installed-but-not-runnable)
  if codex login status >/dev/null 2>&1; then codex_auth_state='logged in'; fi
  if command -v npm >/dev/null 2>&1 && command -v node >/dev/null 2>&1; then
    codex_npm_root=$(npm root -g 2>/dev/null || true)
    codex_main_json="$codex_npm_root/@openai/codex/package.json"
    if [[ -r "$codex_main_json" ]]; then
      codex_main_version=$(node -e 'console.log(require(process.argv[1]).version)' "$codex_main_json" 2>/dev/null || printf unknown)
      codex_node_arch=$(node -p 'process.arch' 2>/dev/null || printf unknown)
      codex_runtime_json="$codex_npm_root/@openai/codex-linux-$codex_node_arch/package.json"
      if [[ -r "$codex_runtime_json" ]]; then
        codex_runtime_version=$(node -e 'console.log(require(process.argv[1]).version)' "$codex_runtime_json" 2>/dev/null || printf unknown)
        codex_install_state="official npm; main $codex_main_version; linux-$codex_node_arch $codex_runtime_version"
      else
        codex_install_state="official npm; main $codex_main_version; matching runtime missing"
      fi
    fi
  fi
  codex_config="$HOME/.codex/config.toml"
  configured_sandbox=$(toml_root_value sandbox_mode "$codex_config")
  configured_approval=$(toml_root_value approval_policy "$codex_config")
  [[ -n "$configured_sandbox" ]] && codex_sandbox_mode=$configured_sandbox
  [[ -n "$configured_approval" ]] && codex_approval_policy=$configured_approval
fi
codex_network_env="$HOME/.config/android-termux-ssh/network-env.sh"
if [[ -r "$codex_network_env" ]]; then
  codex_network_mode=$(stat -c '%a' "$codex_network_env" 2>/dev/null || printf unknown)
  codex_network_state="configured; mode $codex_network_mode"
  if [[ "$codex_network_mode" == 600 ]]; then
    # This is a private file generated by configure-codex.sh and already sourced by the managed launcher.
    # shellcheck disable=SC1090
    . "$codex_network_env"
    if [[ -n "${HTTPS_PROXY:-${https_proxy:-}}" ]]; then
      codex_network_state+='; proxy configured'
    else
      codex_network_state+='; proxy not configured'
    fi
    if [[ -n "${CODEX_CA_CERTIFICATE:-}" && -s "$CODEX_CA_CERTIFICATE" ]]; then
      codex_network_state+='; CA readable'
    else
      codex_network_state+='; CA missing/unreadable'
    fi
    if csv_has_entry "${NO_PROXY:-}" localhost \
        && csv_has_entry "${NO_PROXY:-}" 127.0.0.1 \
        && csv_has_entry "${NO_PROXY:-}" ::1; then
      codex_network_state+='; loopback exclusions complete'
    else
      codex_network_state+='; loopback exclusions incomplete'
    fi
  fi
fi

ssh_start_directory=$HOME
ssh_start_directory_note='Termux private HOME'
ssh_start_directory_file="$HOME/.config/android-termux-ssh/ssh-start-directory"
if [[ -r "$ssh_start_directory_file" ]]; then
  IFS= read -r configured_start_directory < "$ssh_start_directory_file" || true
  if [[ "${configured_start_directory:-}" == /* ]]; then
    ssh_start_directory=$configured_start_directory
    if [[ -d "$ssh_start_directory" && -r "$ssh_start_directory" \
        && -w "$ssh_start_directory" && -x "$ssh_start_directory" ]]; then
      ssh_start_directory_note='available; interactive SSH only'
    else
      ssh_start_directory_note='configured but unavailable'
    fi
  fi
fi

workspace_alias_state='not configured'
workspace_alias="$HOME/workspace"
workspace_target=
if [[ -L "$workspace_alias" ]]; then
  workspace_target=$(readlink -f -- "$workspace_alias" 2>/dev/null || true)
  if [[ -n "$workspace_target" && -d "$workspace_alias" \
      && -r "$workspace_alias" && -w "$workspace_alias" \
      && -x "$workspace_alias" ]]; then
    workspace_alias_state='available'
  else
    workspace_alias_state='broken or unavailable'
  fi
elif [[ -e "$workspace_alias" ]]; then
  workspace_alias_state='exists but is not a symlink'
fi

service_output=$(sv status "$PREFIX/var/service/sshd" 2>&1 || true)
if [[ "$service_output" == run:* ]]; then
  service_status=running
elif [[ -n "$service_output" ]]; then
  service_status='not running'
else
  service_status='not available'
fi
downloads_state=unavailable
if [[ -d "$HOME/storage/downloads" && -r "$HOME/storage/downloads" && -w "$HOME/storage/downloads" ]]; then
  downloads_state='read/write available'
fi
camera_state=missing
command -v remote-camera-photo >/dev/null 2>&1 && camera_state=installed
wifi_state=missing
command -v termux-wifi-scaninfo >/dev/null 2>&1 && wifi_state=installed
bluetooth_state='not installed'
if command -v termux-bluetooth >/dev/null 2>&1; then
  if bluetooth_status=$(termux-bluetooth status 2>/dev/null); then
    if grep -Fq '"scanPermission":true' <<<"$bluetooth_status" \
        && grep -Fq '"connectPermission":true' <<<"$bluetooth_status"; then
      bluetooth_state='local-only companion active; scan/connect permissions granted'
    else
      bluetooth_state='local-only companion active; Android permissions incomplete'
    fi
  else
    bluetooth_state='helper installed; loopback companion unavailable'
  fi
elif command -v termux-bluetooth-scaninfo >/dev/null 2>&1; then
  bluetooth_state='unrecognized Bluetooth CLI detected; verify source and permissions'
fi
bluetooth_settings_state=missing
command -v remote-bluetooth-settings >/dev/null 2>&1 && bluetooth_settings_state=installed

cli_state() {
  if command -v "$1" >/dev/null 2>&1; then printf installed; else printf missing; fi
}

battery_state=$(cli_state termux-battery-status)
location_state=$(cli_state termux-location)
sensor_state=$(cli_state termux-sensor)
nfc_state=$(cli_state termux-nfc)
microphone_state=$(cli_state termux-microphone-record)
notification_state=$(cli_state termux-notification)
torch_state=$(cli_state termux-torch)
clipboard_state=$(cli_state termux-clipboard-get)
usb_state=$(cli_state termux-usb)
telephony_state=$(cli_state termux-telephony-deviceinfo)
sms_state=$(cli_state termux-sms-list)
media_state=$(cli_state termux-media-player)
speech_state=$(cli_state termux-speech-to-text)
tts_state=$(cli_state termux-tts-speak)
saf_state=$(cli_state termux-saf-ls)
biometric_state=$(cli_state termux-fingerprint)

if [[ -f "$TARGET" ]]; then
  begin_count=$(grep -Fxc "$BEGIN_MARKER" "$TARGET" || true)
  end_count=$(grep -Fxc "$END_MARKER" "$TARGET" || true)
  if [[ $begin_count -eq 0 && $end_count -eq 0 ]]; then
    cp "$TARGET" "$BASE_FILE"
  elif [[ $begin_count -eq 1 && $end_count -eq 1 ]]; then
    awk -v begin="$BEGIN_MARKER" -v end="$END_MARKER" '
      $0 == begin {skip=1; next}
      $0 == end {skip=0; next}
      !skip {print}
    ' "$TARGET" > "$BASE_FILE"
  else
    die "AGENTS.md contains incomplete or duplicate android-termux-ssh markers; refusing to overwrite it"
  fi
else
  : > "$BASE_FILE"
fi

{
  printf '%s\n' "$BEGIN_MARKER"
  cat <<'EOF'
# Android Termux 设备上下文

进入此目录工作的自动化代理必须先阅读本节。这里是 Android 上的原生 Termux 环境，不是普通 Ubuntu 主机。

## 当前设备与应用

EOF
  printf -- '- 设备：`%s %s`，Android `%s` / API `%s`，ABI `%s`\n' "$manufacturer" "$model" "$android_release" "$android_sdk" "$abi"
  printf -- '- Termux：`%s`，来源 `%s`，包状态 `%s`\n' "$termux_version" "$termux_release" "$termux_state"
  printf -- '- Termux:API：应用版本 `%s`，包状态 `%s`；CLI `%s`\n' "$api_app_version" "$api_state" "$api_cli_version"
  printf -- '- Termux:Boot：应用版本 `%s`，包状态 `%s`\n' "$BOOT_APP_VERSION" "$boot_state"
  printf -- '- F-Droid 客户端：版本 `%s`，包状态 `%s`\n' "$FDROID_APP_VERSION" "$fdroid_state"
  printf -- '- 原生包：OpenSSH `%s`，termux-services `%s`，Bash `%s`，Git `%s`，Node `%s`，npm `%s`\n' "$openssh_version" "$services_version" "$bash_version" "$git_version" "$node_version" "$npm_version"
  printf -- '- Codex CLI：`%s`；安装：`%s`；身份验证：`%s`；sandbox_mode：`%s`；approval_policy：`%s`\n' "$codex_version" "$codex_install_state" "$codex_auth_state" "$codex_sandbox_mode" "$codex_approval_policy"
  cat <<'EOF'

## 身份与 SSH 边界

EOF
  printf -- '- SSH 端口：`%s`；连接标签：`%s`；提示符主机标签：`%s`\n' "$SSH_PORT" "$LOGIN_LABEL" "$HOST_LABEL"
  printf -- '- 实际 Android/Termux 用户：`%s`，UID `%s`。连接用户名显示为 `%s` 不代表 UID 0，也不提供系统 Root。\n' "$(whoami)" "$(id -u)" "$LOGIN_LABEL"
  printf -- '- 当前 runit 状态：`%s`\n' "$service_status"
  printf -- '- 交互式 SSH 起始目录：`%s`（%s）；真实 `$HOME` 仍为 `%s`。\n' "$ssh_start_directory" "$ssh_start_directory_note" "$HOME"
  if [[ -n "$workspace_target" ]]; then
    printf -- '- 共享工作区别名：`~/workspace` → `%s`（%s）；执行 `cd ~/workspace` 进入，其他 Android 应用可查看目标中的文件。\n' "$workspace_target" "$workspace_alias_state"
  else
    printf -- '- 共享工作区别名：`~/workspace`（%s）。\n' "$workspace_alias_state"
  fi
  cat <<'EOF'
- 非 Root Android 应用不能直接监听 22；不要把 ADB forward 当作设备自身监听或长期运行条件。
- 主机私钥不应出现在设备中。`~/.ssh/authorized_keys` 只保存公钥。

已授权公钥指纹：

EOF
  if [[ -s "$HOME/.ssh/authorized_keys" ]]; then
    while IFS= read -r fingerprint; do printf -- '- `%s`\n' "$fingerprint"; done < <(ssh-keygen -lf "$HOME/.ssh/authorized_keys" 2>/dev/null || true)
  else
    printf -- '- 未发现公钥。\n'
  fi
  cat <<'EOF'

## 已配置能力

EOF
  printf -- '- 开机启动：`~/.termux/boot/start-sshd`；重启后必须先在本机完成一次图案/PIN 解锁，凭据加密的 Termux 数据才可用。\n'
  printf -- '- 息屏保活：Boot 脚本请求 `termux-wake-lock`，sshd 由 runit 管理；HyperOS Greeze 包级豁免状态：`%s`。\n' "$GREEZE_STATUS"
  printf -- '- 共享下载目录：`~/storage/downloads` → `/storage/emulated/0/Download`，当前状态：`%s`。\n' "$downloads_state"
  printf -- '- 相机 helper：`remote-camera-photo`，状态 `%s`。Android 可能要求先把 Termux Activity 带到前台。\n' "$camera_state"
  printf -- '- Wi-Fi 扫描：`termux-wifi-scaninfo`，状态 `%s`。通常需要位置权限和系统位置开关。\n' "$wifi_state"
  printf -- '- 蓝牙 companion：`%s`；打开系统蓝牙设置的 helper `remote-bluetooth-settings` 状态 `%s`。\n' "$bluetooth_state" "$bluetooth_settings_state"
  printf -- '- Codex 网络环境：`%s`。代理值可能包含凭据，不得写入本文、日志或共享存储。\n' "$codex_network_state"
  cat <<'EOF'
- Termux:API 的启动器界面无需常驻；SSH 执行相应 `termux-*` CLI 时按需请求插件。若插件被“强行停止”或后台启动被系统拦截，需要用户解锁并手动打开 Termux:API 一次；相机等能力仍可能要求 Termux Activity 位于前台。
- 蓝牙 companion 的界面无需常驻，但其前台服务必须运行，环回 API 才可用。SSH 可执行 `termux-bluetooth start` 打开 companion Activity，由 Activity 启动非导出的前台服务；`status`、`bonded`、`scan` 不会自动拉起服务。
- 若 companion 被系统“强行停止”，或锁屏/厂商后台策略拦截 Activity，SSH 拉起可能失败；需要用户解锁并手动打开 companion 一次。不要绕过图案/PIN。
- 官方 Termux:API 当前没有稳定的蓝牙扫描/配对/连接命令。独立的 `Termux Bluetooth Bridge` 只在 `127.0.0.1:18765` 提供令牌认证的状态、已配对列表和限时 BLE 扫描；它不是 Termux/F-Droid 官方组件，不提供通用连接动作，也不能静默开关蓝牙。
- `~/.config/android-termux-ssh/bluetooth-bridge.token` 是敏感凭据，必须保持 `0600`，不得输出到日志或复制到其他设备。扫描结果包含附近设备信息，未经用户明确要求不得保存或上传。
- Codex 直接运行在原生 Termux 中，可调用本机 shell、`termux-*` 和蓝牙 helper；同机控制不需要 MCP。ChatGPT Android App 本身仍不能直接调用 Termux。
- 当前 Codex 权限由 `~/.codex/config.toml` 决定。`sandbox_mode="danger-full-access"` 与 `approval_policy="never"` 组合表示 Full access：模型命令不受 Codex 沙箱限制，也不会等待批准，但仍只拥有 Termux 应用 UID，并非 Android 系统 Root。
- Codex 的代理和 CA 由 mode-`0600` 的 `~/.config/android-termux-ssh/network-env.sh` 提供。`NO_PROXY` 必须分别包含 `localhost`、`127.0.0.1` 和 `::1`，否则本地环回请求可能被错误发往上游代理。
- `~/.codex/auth.json` 含可刷新登录令牌，按密码处理；不得复制到 `~/workspace`、共享存储、工单或聊天。

Termux:API CLI 能力清单（`installed` 只表示命令存在，不代表 Android 权限已经授予或实机调用成功）：

EOF
  printf -- '- 电池 `%s`；位置 `%s`；传感器 `%s`；NFC `%s`\n' "$battery_state" "$location_state" "$sensor_state" "$nfc_state"
  printf -- '- 麦克风 `%s`；通知 `%s`；手电筒 `%s`；剪贴板 `%s`\n' "$microphone_state" "$notification_state" "$torch_state" "$clipboard_state"
  printf -- '- USB `%s`；电话信息 `%s`；短信 `%s`；媒体播放 `%s`\n' "$usb_state" "$telephony_state" "$sms_state" "$media_state"
  printf -- '- 语音识别 `%s`；TTS `%s`；SAF 文件接口 `%s`；指纹 `%s`\n' "$speech_state" "$tts_state" "$saf_state" "$biometric_state"
  cat <<'EOF'
- Bash 已配置补全、历史搜索、彩色输出和常用别名；这是原生 Termux，不是 proot Ubuntu。
- 公共共享存储不提供完整 POSIX 文件系统语义；Git 普通源码仓库已经过验证，但依赖符号链接、Unix 权限位、区分大小写文件名或 socket 的项目应放回 `$HOME`。

## 常用检查

```bash
termux-info
sv status "$PREFIX/var/service/sshd"
sshd -t
ssh-keygen -lf ~/.ssh/authorized_keys
cd ~/storage/downloads
termux-wifi-scaninfo
remote-camera-photo ~/storage/downloads/test-photo.jpg 0
termux-bluetooth start
termux-bluetooth status
termux-bluetooth bonded
termux-bluetooth scan 8
remote-bluetooth-settings
codex --version
codex login status
codex doctor
codex
```

相机测试结束后只删除本次创建的精确文件，并再次确认没有测试照片残留。不要对相册使用宽泛通配符删除。

## 自动化代理约束

- 日常管理必须通过设备自身的 SSH/IP 完成；ADB 只可用于用户授权的一次性安装、Android 权限配置或诊断。
- 修改前先检查实时状态，不要把本文生成时的版本、IP 或服务状态当作永久事实。手机 IP 可能变化。
- 对相机、麦克风、位置、短信、联系人、电话、NFC、蓝牙等隐私或硬件能力，先检查权限和用户任务范围；命令存在不等于授权使用。
- Codex Full access 不扩大用户任务授权范围。不要因无需批准就擅自扫描未授权网段、连接设备、拍照、读取隐私数据或执行破坏性命令。
- 不要把 Codex app-server、SSH 或通用 `shell(command)` MCP 暴露到公网。需要长期探针时优先提供范围明确、可审计的 helper。
- 不要擅自卸载 Termux/插件、清除应用数据、关闭锁屏、永久关闭整机安全防护、全局禁用 Doze/Greeze，或覆盖用户已有配置。
- Termux、Termux:API、Termux:Boot 必须保持同一签名来源；当前部署预期为 F-Droid 系列。
- 服务统一通过 `termux-services`/runit 管理，不要另建循环执行 `sshd` 的重复守护进程。
- 若仅在物理息屏时出现 SSH banner 超时，检查 wake lock 与厂商进程冻结；不要用自动点亮屏幕掩盖问题。
- 改变应用、端口、能力或保活策略后，运行 `update-termux-agents` 刷新本节，并重新做纯局域网息屏验收。

## 关键文件

```text
~/.ssh/authorized_keys
~/.termux/boot/start-sshd
$PREFIX/etc/ssh/sshd_config.d/20-android-termux-ssh.conf
$PREFIX/var/service/sshd
~/.config/android-termux-ssh/bashrc
~/.config/android-termux-ssh/bluetooth-bridge.token
~/.config/android-termux-ssh/network-env.sh
~/.codex/config.toml
~/.codex/auth.json
$PREFIX/bin/codex
~/AGENTS.md
```
EOF
  printf '%s\n' "$END_MARKER"
} > "$BLOCK_FILE"

cp "$BASE_FILE" "$FINAL_FILE"
if [[ -s "$FINAL_FILE" ]]; then printf '\n' >> "$FINAL_FILE"; fi
cat "$BLOCK_FILE" >> "$FINAL_FILE"

if [[ -f "$TARGET" ]] && cmp -s "$TARGET" "$FINAL_FILE"; then
  printf 'AGENTS.md is already current: %s\n' "$TARGET"
  exit 0
fi

if [[ -f "$TARGET" ]]; then
  backup_dir="$HOME/.local/state/android-termux-ssh/backups"
  install -d -m 700 "$backup_dir"
  backup_path="$backup_dir/AGENTS.md.$(date +%Y%m%d-%H%M%S-%N)"
  cp -p "$TARGET" "$backup_path"
  printf 'Previous AGENTS.md backed up to: %s\n' "$backup_path"
fi

install -m 600 "$FINAL_FILE" "$TARGET"
printf 'Updated device context: %s\n' "$TARGET"
