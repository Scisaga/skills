# Xfce 文件访问与启动器

用于 Thunar 缩略图缺失、SMB 目录体感慢、打开文件再次认证，以及桌面图标启动超时。在当前 Xfce 终端复现，沿用已有的 GVfs 登录和用户窗口。

## Thunar 缩略图和目录加载

1. 查询 `/misc-thumbnail-mode`，并在当前会话调用 `org.freedesktop.thumbnails.Thumbnailer1.GetSupported`。同时检查 URI scheme 和 MIME，特别是 `smb` 与常见图片格式。Debian guest 缺少服务时安装 `tumbler`，按实际格式补相应 loader。需要远程缩略图时启用 Thunar 的「始终显示缩略图」；若已打开的 Thunar 仍持有服务不可用的状态，正常重开并复核原标签。
2. 对同一目录记录枚举总时间、首段文件读取和首轮缩略图生成。目录列表和预览各有独立的等待。缓存命中适用于回访，尚未缓存的预览需要读取原图。用 Thunar 实际查看文件列表和重入后的预览。
3. 某张图长期缺预览时，检查文件头、扩展名和 Tumbler 返回的错误。确认内容类型时可以按真实格式重试生成缩略图。通过当前默认程序从原共享打开图片，核对显示结果。

```bash
xfconf-query -c thunar -p /misc-thumbnail-mode
gdbus call --session --dest org.freedesktop.thumbnails.Thumbnailer1 \
  --object-path /org/freedesktop/thumbnails/Thumbnailer1 \
  --method org.freedesktop.thumbnails.Thumbnailer1.GetSupported
```

缩略图服务与缓存机制见 [Xfce Tumbler 官方说明](https://docs.xfce.org/xfce/tumbler/start)。

## 从 SMB 打开文件

- 文件夹已登录后仍弹认证窗时，核对 Thunar 的实际默认应用、`.desktop` 的 URI 参数、应用进程的会话 D-Bus 和真实文件读取得到的结果。应用的 SMB 客户端和原生启动器可能各自处理 URI；同会话的 GIO/GVfs 程序可复用已挂载的共享。
- 可用支持 URI 的 Ristretto 接管用户选定的常见图片类型。对原生 LibreOffice 启动器明确拒绝的 `smb://` 地址，可将这类文档送给同一 Xfce 会话内的 guest LibreOffice。Debian 的 `libreoffice-gnome` 提供 GIO 组件。保留其他地址原有入口，验证普通 Thunar 操作能读取测试 `.docx` 和 `.xlsx` 的内容，随后移除本轮测试文件。

## 桌面图标超时

Xfdesktop 执行桌面图标时走 Thunar 的文件管理 D-Bus 入口。若超时而程序已安装、路径及执行位正确，检查当前会话是否还开着启动确认框，以及这个 `.desktop` 的 `metadata::xfce-exe-checksum`。对已经核对命令的本机图标，可通过 Xfce 的信任确认补标记。再从同一个图标启动一次，核对请求、窗口和自启动配置。修改启动器内容后应复核其信任标记。[Xfdesktop 执行入口](https://github.com/xfce-mirror/xfdesktop/blob/xfdesktop-4.20.1/src/xfdesktop-file-utils.c#L1353-L1453)

启用了 Thunar 专用触控模块时，还要复核后台 D-Bus 自动激活的 Thunar。菜单入口与 D-Bus 入口都应加载设备已验收的包装器。用会话总线的进程身份和实际模块映射核对，并回到原窗口验证手势。

重装前把相关入口、选定 MIME、缩略图设置及包版本纳入 [桌面配置基线](desktop-verification.md#桌面配置基线)。
