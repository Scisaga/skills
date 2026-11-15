#!/bin/bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive LC_ALL=C
guest_user=$1
apps=",$2,"
locale_name=$3
code_version=$4
touch_long_press=${5:-0}
policy_created=false
if [[ ! -e /usr/sbin/policy-rc.d ]]; then
  printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d
  chmod 755 /usr/sbin/policy-rc.d
  policy_created=true
fi
cleanup() { if $policy_created; then rm -f /usr/sbin/policy-rc.d; fi; }
trap cleanup EXIT
apt-get -o Acquire::Retries=3 update
packages=(ca-certificates curl git dbus-x11 locales python3 python3-gi python3-xlib gir1.2-gtk-3.0
  xfce4-session xfce4-panel xfdesktop4 xfwm4 xfce4-settings xfce4-terminal
  xfce4-genmon-plugin thunar mousepad x11-xserver-utils x11-utils xdotool wmctrl
  procps psmisc fontconfig xdg-utils fonts-dejavu-core fonts-noto-cjk greybird-gtk-theme papirus-icon-theme
  librsvg2-common adwaita-icon-theme)
[[ $apps != *,chromium,* ]] || packages+=(chromium)
[[ $apps != *,office,* ]] || packages+=(libreoffice-writer libreoffice-calc libreoffice-impress libreoffice-gtk3 libreoffice-l10n-zh-cn)
[[ $apps != *,vlc,* ]] || packages+=(vlc ffmpeg)
[[ $touch_long_press != 1 ]] || packages+=(gcc libc6-dev libx11-dev libxi-dev libxtst-dev)
apt-get -y --no-install-recommends install "${packages[@]}"
want_code=false
if [[ $apps == *,code,* ]]; then
  installed_version=$(dpkg-query -W -f='${Version}' code 2>/dev/null || true)
  if [[ -z $installed_version ]]; then want_code=true
  elif [[ $code_version != stable && $installed_version != "$code_version" && $installed_version != "$code_version"-* ]]; then want_code=true
  fi
fi
if $want_code; then
  architecture=$(dpkg --print-architecture)
  case "$architecture" in
    arm64) code_arch=arm64 ;; amd64) code_arch=x64 ;; armhf) code_arch=armhf ;;
    *) printf 'VS Code architecture not supported by this installer: %s\n' "$architecture" >&2; exit 1 ;;
  esac
  release=$code_version
  [[ $release != stable ]] || release=latest
  package=$(mktemp /tmp/termux-code.XXXXXX.deb)
  curl --proto '=https' --tlsv1.2 -fL --retry 3 "https://update.code.visualstudio.com/$release/linux-deb-$code_arch/stable" -o "$package"
  [[ $(dpkg-deb -f "$package" Architecture) == "$architecture" ]] || { rm -f "$package"; exit 1; }
  printf 'code code/add-microsoft-repo boolean true\ncode code/add-copilot-command boolean false\n' | debconf-set-selections
  apt-get -y install "$package"
  rm -f "$package"
fi
if ! grep -Fxq "$locale_name UTF-8" /etc/locale.gen; then
  printf '%s UTF-8\n' "$locale_name" >> /etc/locale.gen
fi
locale-gen "$locale_name"
if ! id "$guest_user" >/dev/null 2>&1; then useradd --create-home --shell /bin/bash "$guest_user"; fi
install -d -m 755 -o "$guest_user" -g "$(id -gn "$guest_user")" "/home/$guest_user/Desktop" "/home/$guest_user/workspaces"
