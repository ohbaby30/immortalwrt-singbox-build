# ImmortalWrt SingBox GitHub Actions Builder

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

Both targets keep the same package choices as the Xray build, while Passwall2 includes both SingBox and Xray basic cores.

## Usage

Upload the contents of this `build-singbox/` directory to a GitHub repository root. Do not upload the outer `build-singbox/` folder itself.

Then open `Actions`, choose the x86_64 or R4S workflow, and click `Run workflow`.
