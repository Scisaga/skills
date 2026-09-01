# 蓝牙 companion

## 为什么不能直接给 Termux:API 授权

Android 的运行时授权必须同时满足：APK 的 manifest 声明权限、权限本身允许运行时授予、用户或受授权的部署通道完成授予。官方 F-Droid Termux:API 0.53.0 没有声明 `BLUETOOTH_SCAN`、`BLUETOOTH_CONNECT` 或 `BLUETOOTH_ADVERTISE`，因此 `pm grant` 和 AppOps 不能把它补成蓝牙 API。

官方 Termux:API 当前也没有已发布的蓝牙命令；蓝牙扫描仍是未合并 PR：<https://github.com/termux/termux-api/pull/686>

不要为了蓝牙单独替换一个重签名 Termux 插件。Termux、Termux:API 和 Termux:Boot 使用共享 UID/同签名关系，混装会安装失败或破坏现有应用链。

## 独立 companion 的边界

本 skill 在 `assets/bluetooth-companion/` 提供最小 Java companion 源码：

- 独立包名 `io.github.scisaga.termuxbluetoothbridge`，不加入 Termux 共享 UID。
- 只申请扫描和访问已配对设备需要的蓝牙权限；不申请蓝牙广播权限。
- 扫描声明 `neverForLocation`，不申请 Android 12+ 位置权限；代价是系统可能过滤部分 BLE beacon。
- 前台服务只监听 `127.0.0.1:18765`，不会暴露到 Wi-Fi/LAN。
- 每台设备使用随机 256-bit bearer token；companion 私有存储和 Termux `0600` 文件各保存一份。
- 只实现状态、已配对设备列表和限时 BLE 扫描。通用“连接蓝牙设备”不存在统一动作，GATT、串口、音频、HID 等协议需要分别实现。
- 普通 Android 应用不能静默开关蓝牙；`termux-bluetooth settings` 只打开系统设置页。

这是本地管理扩展，不是 F-Droid 或 Termux 官方组件。安装前应审核源码；对外分发时应建立独立发布、签名和更新流程。

## 构建

构建脚本使用固定版本和 SHA-256 的 AAPT2、R8、apksig 与 Robolectric AOSP framework artifact，并用仓库内可审计的小型 Java 入口生成 APK；当前 minSdk 下 apksig 生成并校验 v2/v3 签名。脚本不自动接受 Android SDK License，也不把签名私钥放进仓库。WSL 主机需要 Windows JDK 17+、`curl`、`unzip`、`openssl` 和初次构建时可读的目标设备 `framework-res.apk`。

```bash
bash skills/android-termux-ssh/scripts/build-bluetooth-companion.sh \
  --adb /path/to/adb.exe \
  --output /tmp/termux-bluetooth-bridge.apk
```

签名材料默认保存在：

```text
~/.config/android-termux-ssh/bluetooth-bridge.p12
~/.config/android-termux-ssh/bluetooth-bridge.pass
```

丢失签名材料后无法覆盖升级已安装 companion，只能先卸载旧包；卸载会清除 companion 私有 token。不要提交或同步这些文件到公开仓库。

## 首次部署

ADB 只用于安装 APK 和授予 Android 权限。部署前必须已有不经 ADB forward 的局域网 SSH：

```bash
bash skills/android-termux-ssh/scripts/deploy-bluetooth-companion.sh \
  --apk /tmp/termux-bluetooth-bridge.apk \
  --serial SERIAL \
  --ssh-host root@PHONE_IP \
  --ssh-port 8022
```

若 companion 已经打开过并自行生成了不同 token，只有在用户授权清除这个新 companion 自身的设置后才加 `--reset-companion-data`。它不清除 Termux 数据；会重置 companion 的 token 和 Android 运行时权限，然后由部署脚本重新配置。不要在无关应用上使用 `pm clear`。

HyperOS 设备在已获用户授权时可加 `--hyperos-exempt`，只把 companion 包追加到 Greeze 用户豁免列表。脚本不会关闭整机省电策略。

若 HyperOS 以 `INSTALL_FAILED_USER_RESTRICTED` 拒绝 ADB 安装，不要关闭 MIUI/HyperOS 优化。把 APK 精确复制到 `~/storage/downloads`，临时启用 `allow-external-apps=true`，用 `termux-open --view APK_PATH` 打开系统安装器并完成可见确认；安装完成时选择“完成”，先不要打开 companion。随后恢复原 `termux.properties`、删除 APK 副本，再用 `--skip-install` 执行上面的部署脚本。不要把 Termux 永久记为可信安装来源。

部署后关闭 ADB server，再通过局域网 SSH 验证：

```bash
termux-bluetooth status
termux-bluetooth bonded
termux-bluetooth scan 8
```

扫描结果属于附近设备信息。除非用户明确要求，不要保存、上传或长期记录 MAC 地址、设备名和 RSSI。

## 重启与排障

companion 使用自己的 `BOOT_COMPLETED` receiver 启动前台服务。Android 或厂商 ROM 仍可能阻止自启动；先检查通知权限、附近设备权限、应用自启动开关、电池“无限制”和 Greeze 豁免。打开 companion Activity 会再次启动服务：

```bash
termux-bluetooth open
```

如果 `status` 连接被拒绝，先确认 companion 前台通知是否存在。若状态可用但扫描返回 Bluetooth disabled，使用：

```bash
termux-bluetooth settings
```

由用户在系统界面开启蓝牙。不要用 ADB shell 的 `cmd bluetooth_manager enable` 冒充 Termux 独立能力。
