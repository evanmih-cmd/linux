#!/bin/bash
set -euo pipefail

TARGET="${1:-/target}"
STATE="${2:-/run/portable-installer/state.env}"

if [[ ! -d "$TARGET" || ! -f "$STATE" ]]; then
  echo "usage: postinstall.sh TARGET STATE" >&2
  exit 2
fi

# shellcheck disable=SC1090
source "$STATE"

install -d -m 0755 "$TARGET/usr/local/sbin"
install -d -m 0755 "$TARGET/etc/systemd/system"
install -d -m 0755 "$TARGET/etc/systemd/system/portable-maintenance.target.wants"
install -d -m 0755 "$TARGET/etc/apt/apt.conf.d"

cat >"$TARGET/etc/crypttab" <<EOF
portable-root UUID=$LUKS_UUID none luks
EOF
chmod 0600 "$TARGET/etc/crypttab"

# Keep the ESP available to the system but immutable during ordinary runtime.
tmp_fstab="$(mktemp)"
awk '$2 != "/efi" { print }' "$TARGET/etc/fstab" >"$tmp_fstab"
cat "$tmp_fstab" >"$TARGET/etc/fstab"
rm -f "$tmp_fstab"
printf 'UUID=%s /efi vfat ro,umask=0077 0 1\n' "$ESP_UUID" >>"$TARGET/etc/fstab"

# Executable state is mutated only by the mandatory boot gate.
cat >"$TARGET/etc/apt/apt.conf.d/20auto-upgrades" <<'EOF'
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
EOF

# No disk-backed hibernation path.
chroot "$TARGET" systemctl mask hibernate.target hybrid-sleep.target >/dev/null

# zram is intentionally modest; it is a pressure valve, not capacity planning.
cat >"$TARGET/etc/systemd/zram-generator.conf" <<'EOF'
[zram0]
zram-size = min(ram / 4, 8192)
compression-algorithm = zstd
swap-priority = 100
EOF

# Install the mandatory boot-time update gate.
install -m 0755 /cdrom/portable/runtime/portable-update-gate.sh   "$TARGET/usr/local/sbin/portable-update-gate"
install -m 0644 /cdrom/portable/runtime/portable-update-gate.service   "$TARGET/etc/systemd/system/portable-update-gate.service"
install -m 0644 /cdrom/portable/runtime/portable-maintenance.target   "$TARGET/etc/systemd/system/portable-maintenance.target"

ln -sfn ../portable-update-gate.service   "$TARGET/etc/systemd/system/portable-maintenance.target.wants/portable-update-gate.service"
ln -sfn /etc/systemd/system/portable-maintenance.target   "$TARGET/etc/systemd/system/default.target"

# Ensure initramfs knows how to unlock the root device.
chroot "$TARGET" update-initramfs -u -k all

# Install a Secure-Boot-capable removable-media path and never write UEFI NVRAM.
# Curtin is also configured with update_nvram=false; this final installation
# makes the fallback path explicit.
mount -o remount,rw "$TARGET/efi"
chroot "$TARGET" grub-install   --target=x86_64-efi   --efi-directory=/efi   --boot-directory=/boot   --removable   --no-nvram   --uefi-secure-boot
chroot "$TARGET" update-grub
mount -o remount,ro "$TARGET/efi"

# Baseline snapshots are created only on a new installation. A reinstall
# intentionally keeps the historical factory baseline.
TOP=/mnt/portable-postinstall-top
mkdir -p "$TOP"
mount -t btrfs -o subvolid=5 /dev/mapper/portable-root "$TOP"
cleanup() {
  mountpoint -q "$TOP" && umount "$TOP" || true
}
trap cleanup EXIT

if [[ "$MODE" == "fresh" ]]; then
  btrfs subvolume snapshot -r "$TOP/@root" "$TOP/@snapshots/factory-good"
  btrfs subvolume snapshot -r "$TOP/@root" "$TOP/@snapshots/last-known-good"
fi
