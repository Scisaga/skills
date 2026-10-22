#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
SKILL_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
SOURCE_DIR="$SKILL_DIR/assets/bluetooth-companion"
OUTPUT="$PWD/termux-bluetooth-bridge.apk"
FRAMEWORK_APK=
ADB_BIN=${ADB_BIN:-}
JAVA_HOME_WINDOWS=${JAVA_HOME_WINDOWS:-}
CACHE_DIR=${XDG_CACHE_HOME:-$HOME/.cache}/android-termux-ssh/bluetooth-build
KEY_DIR=${XDG_CONFIG_HOME:-$HOME/.config}/android-termux-ssh

AAPT2_VERSION=9.3.2-15703166
R8_VERSION=9.4.17
APKSIG_VERSION=9.3.2
ANDROID_ALL_VERSION=16-robolectric-13921718
AAPT2_SHA256=b1006ecec7e5936257e95e97f3eba7ef439d3e44178967cc048f86c9119fb231
R8_SHA256=2100511344497f041644a4d63fb7be8a516ce9bace30b7d17ab27cc93a0e58d4
APKSIG_SHA256=562cd0a88890960d2ece48e116c61f12872222f1dcc306890799382bc019b201
ANDROID_ALL_SHA256=8b74a0a137330658d2f33f0dc715d42734f74ba8b2d7014fc2e95aa40d3f682d

usage() {
  cat <<'EOF'
Usage: build-bluetooth-companion.sh [options]

Build the independent Termux Bluetooth Bridge APK from pinned Android/AOSP
build artifacts. This path is intended for WSL with a Windows JDK 17+.

Options:
  --output PATH          signed APK output path
  --adb PATH             adb or adb.exe used to pull framework-res.apk
  --framework-apk PATH   use an existing framework-res.apk instead of adb pull
  --java-home PATH       Windows JDK home as a WSL or Windows path
  --cache-dir PATH       artifact/build cache directory
  --key-dir PATH         private signing keystore directory
  -h, --help             show this help

The signing key and password are generated under --key-dir and are never put in
the skill repository. Keep them to install future updates over the same package.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) [[ $# -ge 2 ]] || die "$1 requires a path"; OUTPUT=$2; shift 2 ;;
    --adb) [[ $# -ge 2 ]] || die "$1 requires a path"; ADB_BIN=$2; shift 2 ;;
    --framework-apk) [[ $# -ge 2 ]] || die "$1 requires a path"; FRAMEWORK_APK=$2; shift 2 ;;
    --java-home) [[ $# -ge 2 ]] || die "$1 requires a path"; JAVA_HOME_WINDOWS=$2; shift 2 ;;
    --cache-dir) [[ $# -ge 2 ]] || die "$1 requires a path"; CACHE_DIR=$2; shift 2 ;;
    --key-dir) [[ $# -ge 2 ]] || die "$1 requires a path"; KEY_DIR=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown option: $1" ;;
  esac
done

for command_name in curl sha256sum unzip openssl wslpath; do
  command -v "$command_name" >/dev/null 2>&1 || die "missing dependency: $command_name"
done

find_adb() {
  if [[ -n "$ADB_BIN" && -x "$ADB_BIN" ]]; then return; fi
  if command -v adb >/dev/null 2>&1; then ADB_BIN=$(command -v adb); return; fi
  local candidate=/mnt/c/Users/${USER}/AppData/Local/Android/platform-tools/adb.exe
  [[ -x "$candidate" ]] && ADB_BIN=$candidate
}

find_java_home() {
  if [[ -n "$JAVA_HOME_WINDOWS" ]]; then return; fi
  local candidate
  for candidate in \
    '/mnt/c/Program Files/Java/jdk-21' \
    '/mnt/c/Program Files/Android/Android Studio/jbr'; do
    if [[ -x "$candidate/bin/java.exe" ]]; then
      JAVA_HOME_WINDOWS=$candidate
      return
    fi
  done
}

winpath() {
  if [[ "$1" =~ ^[A-Za-z]:[\\/] ]]; then printf '%s\n' "$1"; else wslpath -w "$1"; fi
}

adb_host_path() {
  if [[ "$ADB_BIN" == *.exe ]]; then winpath "$1"; else printf '%s\n' "$1"; fi
}

fetch() {
  local url=$1 destination=$2 expected=$3 actual
  if [[ ! -s "$destination" ]]; then
    printf 'Downloading %s\n' "$(basename "$destination")"
    curl -fL --retry 3 "$url" -o "$destination"
  fi
  actual=$(sha256sum "$destination" | awk '{print $1}')
  if [[ "$actual" != "$expected" ]]; then
    die "checksum mismatch for $destination (expected $expected, got $actual)"
  fi
}

find_adb
find_java_home
[[ -n "$JAVA_HOME_WINDOWS" ]] || die 'Windows JDK 17+ not found; pass --java-home'

JAVA_BIN="$JAVA_HOME_WINDOWS/bin/java.exe"
JAVAC_BIN="$JAVA_HOME_WINDOWS/bin/javac.exe"
JAR_BIN="$JAVA_HOME_WINDOWS/bin/jar.exe"
KEYTOOL_BIN="$JAVA_HOME_WINDOWS/bin/keytool.exe"
for tool_path in "$JAVA_BIN" "$JAVAC_BIN" "$JAR_BIN" "$KEYTOOL_BIN"; do
  [[ -x "$tool_path" ]] || die "missing JDK tool: $tool_path"
done
[[ -r "$SOURCE_DIR/AndroidManifest.xml" ]] || die "missing companion source: $SOURCE_DIR"
VERSION_CODE=$(sed -n 's/.*android:versionCode="\([0-9][0-9]*\)".*/\1/p' "$SOURCE_DIR/AndroidManifest.xml" | head -n 1)
VERSION_NAME=$(sed -n 's/.*android:versionName="\([^"]*\)".*/\1/p' "$SOURCE_DIR/AndroidManifest.xml" | head -n 1)
[[ "$VERSION_CODE" =~ ^[0-9]+$ ]] || die 'could not read android:versionCode from the companion manifest'
[[ "$VERSION_NAME" =~ ^[0-9A-Za-z._-]+$ ]] || die 'could not read a safe android:versionName from the companion manifest'

ARTIFACT_DIR="$CACHE_DIR/artifacts"
install -d -m 700 "$ARTIFACT_DIR" "$KEY_DIR"
AAPT2_JAR="$ARTIFACT_DIR/aapt2-windows.jar"
R8_JAR="$ARTIFACT_DIR/r8.jar"
APKSIG_JAR="$ARTIFACT_DIR/apksig.jar"
ANDROID_ALL_JAR="$ARTIFACT_DIR/android-all.jar"

fetch "https://dl.google.com/dl/android/maven2/com/android/tools/build/aapt2/$AAPT2_VERSION/aapt2-$AAPT2_VERSION-windows.jar" "$AAPT2_JAR" "$AAPT2_SHA256"
fetch "https://dl.google.com/dl/android/maven2/com/android/tools/r8/$R8_VERSION/r8-$R8_VERSION.jar" "$R8_JAR" "$R8_SHA256"
fetch "https://dl.google.com/dl/android/maven2/com/android/tools/build/apksig/$APKSIG_VERSION/apksig-$APKSIG_VERSION.jar" "$APKSIG_JAR" "$APKSIG_SHA256"
fetch "https://repo1.maven.org/maven2/org/robolectric/android-all/$ANDROID_ALL_VERSION/android-all-$ANDROID_ALL_VERSION.jar" "$ANDROID_ALL_JAR" "$ANDROID_ALL_SHA256"

WORK_DIR=$(mktemp -d "$CACHE_DIR/work.XXXXXX")
cleanup() {
  if [[ -n ${WORK_DIR:-} && "$WORK_DIR" == "$CACHE_DIR"/work.* && -d "$WORK_DIR" ]]; then
    rm -rf -- "$WORK_DIR"
  fi
}
trap cleanup EXIT

if [[ -n "$FRAMEWORK_APK" ]]; then
  [[ -r "$FRAMEWORK_APK" ]] || die "framework APK is unreadable: $FRAMEWORK_APK"
  cp "$FRAMEWORK_APK" "$WORK_DIR/framework-res.apk"
else
  [[ -n "$ADB_BIN" && -x "$ADB_BIN" ]] || die 'adb is required unless --framework-apk is provided'
  "$ADB_BIN" pull /system/framework/framework-res.apk "$(adb_host_path "$WORK_DIR/framework-res.apk")" >/dev/null
fi
[[ -s "$WORK_DIR/framework-res.apk" ]] || die 'failed to obtain framework-res.apk'

unzip -p "$AAPT2_JAR" aapt2.exe > "$WORK_DIR/aapt2.exe"
chmod 700 "$WORK_DIR/aapt2.exe"
install -d -m 700 "$WORK_DIR/classes" "$WORK_DIR/dex" "$WORK_DIR/signer-classes"

mapfile -t JAVA_SOURCES < <(find "$SOURCE_DIR/src" -type f -name '*.java' -print | sort)
(( ${#JAVA_SOURCES[@]} > 0 )) || die 'no Java sources found'
JAVAC_ARGS=(
  -encoding UTF-8 -source 8 -target 8
  -classpath "$(winpath "$ANDROID_ALL_JAR")"
  -d "$(winpath "$WORK_DIR/classes")"
)
for source_file in "${JAVA_SOURCES[@]}"; do JAVAC_ARGS+=("$(winpath "$source_file")"); done
"$JAVAC_BIN" "${JAVAC_ARGS[@]}"

"$JAR_BIN" --create --file "$(winpath "$WORK_DIR/classes.jar")" \
  -C "$(winpath "$WORK_DIR/classes")" .
"$JAVA_BIN" -cp "$(winpath "$R8_JAR")" com.android.tools.r8.D8 \
  --min-api 26 --output "$(winpath "$WORK_DIR/dex")" "$(winpath "$WORK_DIR/classes.jar")"

"$WORK_DIR/aapt2.exe" link \
  -o "$(winpath "$WORK_DIR/base.apk")" \
  --manifest "$(winpath "$SOURCE_DIR/AndroidManifest.xml")" \
  -I "$(winpath "$WORK_DIR/framework-res.apk")" \
  --min-sdk-version 26 --target-sdk-version 35 \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME"
"$JAR_BIN" --update --file "$(winpath "$WORK_DIR/base.apk")" \
  -C "$(winpath "$WORK_DIR/dex")" classes.dex

"$JAVAC_BIN" -encoding UTF-8 -source 8 -target 8 \
  -classpath "$(winpath "$APKSIG_JAR")" \
  -d "$(winpath "$WORK_DIR/signer-classes")" \
  "$(winpath "$SOURCE_DIR/tools/LocalApkSigner.java")"

KEYSTORE="$KEY_DIR/bluetooth-bridge.p12"
PASS_FILE="$KEY_DIR/bluetooth-bridge.pass"
if [[ ! -s "$KEYSTORE" || ! -s "$PASS_FILE" ]]; then
  [[ ! -e "$KEYSTORE" && ! -e "$PASS_FILE" ]] || die 'incomplete signing-key state; inspect --key-dir manually'
  umask 077
  openssl rand -hex 24 > "$PASS_FILE"
  SIGNING_PASS=$(<"$PASS_FILE")
  "$KEYTOOL_BIN" -J-Duser.language=en -J-Duser.country=US -genkeypair -noprompt \
    -storetype PKCS12 -keystore "$(winpath "$KEYSTORE")" \
    -storepass "$SIGNING_PASS" -keypass "$SIGNING_PASS" \
    -alias termux-bluetooth-bridge -keyalg RSA -keysize 3072 -validity 36500 \
    -dname 'CN=Local Termux Bluetooth Bridge, OU=Device Administration'
  chmod 600 "$KEYSTORE" "$PASS_FILE"
fi

SIGNING_PASS=$(<"$PASS_FILE")
SIGNER_CLASSPATH="$(winpath "$WORK_DIR/signer-classes");$(winpath "$APKSIG_JAR")"
"$JAVA_BIN" -cp "$SIGNER_CLASSPATH" LocalApkSigner sign \
  "$(winpath "$WORK_DIR/base.apk")" "$(winpath "$WORK_DIR/signed.apk")" \
  "$(winpath "$KEYSTORE")" "$SIGNING_PASS" termux-bluetooth-bridge 26
unset SIGNING_PASS

install -m 600 "$WORK_DIR/signed.apk" "$OUTPUT"
"$JAVA_BIN" -cp "$SIGNER_CLASSPATH" LocalApkSigner verify "$(winpath "$OUTPUT")"
printf 'Built: %s\n' "$OUTPUT"
printf 'Signing material (keep private for updates): %s\n' "$KEY_DIR"
