# ImmortalWrt SingBox GitHub Actions Builder

![Build R4S](https://github.com/ohbaby30/immortalwrt-singbox-build/actions/workflows/build-r4s.yml/badge.svg)
![Build x86_64](https://github.com/ohbaby30/immortalwrt-singbox-build/actions/workflows/build-x86_64.yml/badge.svg)

This repository builds ImmortalWrt `master` firmware for both x86_64 and FriendlyARM NanoPi R4S with GitHub Actions.

## Targets

- `Build ImmortalWrt x86_64 SingBox`
  - Config: `configs/x86_64.config`
  - Custom files: `files-x86_64/`
  - First boot LAN IP: `10.10.10.123/24`
  - Firmware: `immortalwrt-x86-64-generic-squashfs-combined-efi.img.gz`

- `Build ImmortalWrt R4S SingBox`
  - Config: `configs/r4s.config`
  - Custom files: `files-r4s/`
  - First boot LAN IP: `192.168.50.254/24`
  - Firmware: `immortalwrt-rockchip-armv8-friendlyarm_nanopi-r4s-squashfs-sysupgrade.img.gz`

Both targets keep the same package choices as the Xray build, except Passwall2 uses only the SingBox basic core.

## Usage

Upload the contents of this `build-singbox/` directory to a GitHub repository root. Do not upload the outer `build-singbox/` folder itself.

Then open `Actions`, choose the x86_64 or R4S workflow, and click `Run workflow`.
