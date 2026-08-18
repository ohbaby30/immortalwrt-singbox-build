# ImmortalWrt SingBox GitHub Actions 自动编译

![Build R4S](https://github.com/ohbaby30/immortalwrt-singbox-build/actions/workflows/build-r4s.yml/badge.svg)
![Build x86_64](https://github.com/ohbaby30/immortalwrt-singbox-build/actions/workflows/build-x86_64.yml/badge.svg)

本仓库使用 GitHub Actions 自动编译 ImmortalWrt `master` 固件，支持 x86_64 和 FriendlyARM NanoPi R4S 两个目标平台，集成 SingBox + Passwall2。

## 构建目标

| 平台 | 配置文件 | 自定义文件 | 首次启动 LAN IP | 固件文件名 |
|------|----------|------------|-----------------|------------|
| x86_64 | `configs/x86_64.config` | `files-x86_64/` | `10.10.10.123/24` | `immortalwrt-x86-64-generic-squashfs-combined-efi.img.gz` |
| R4S | `configs/r4s.config` | `files-r4s/` | `192.168.50.254/24` | `immortalwrt-rockchip-armv8-friendlyarm_nanopi-r4s-squashfs-sysupgrade.img.gz` |

两个目标的软件包配置一致，Passwall2 仅使用 SingBox 基础核心。

## ⚠️ 安全警告

固件首次启动时 **root 密码为空**（无密码），方便调试但存在安全风险。

**刷入固件后，请立即通过 SSH 或 LuCI 设置 root 密码：**

```sh
passwd root
```

请勿在设置密码前将设备暴露在公网或不受信任的网络中。

## 使用方法

1. 将本仓库内容（不含外层目录）上传到一个 GitHub 仓库根目录
2. 打开 `Actions` 页面，选择对应的 x86_64 或 R4S 工作流
3. 点击 `Run workflow` 手动触发编译

也可以等待每周日凌晨 02:00（北京时间）的自动定时编译。

## 构建产物

每次构建会发布以下文件到 GitHub Releases：

- 对应平台的固件镜像（`.img.gz`）
- Passwall2 的 `.apk` 安装包
- `SHA256SUMS` 校验和文件，用于验证下载完整性
