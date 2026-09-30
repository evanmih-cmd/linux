#!/bin/bash
set -euo pipefail

STATE_DIR=/var/lib/portable-update
TOP=/run/portable-btrfs-top
LOG=/var/log/portable-update-gate.log
PENDING="$STATE_DIR/reinit-pending"
KEEP_PREUPDATE=4

mkdir -p "$STATE_DIR" "$TOP"
exec >>"$LOG" 2>&1

echo "=== portable update gate: $(date --iso-8601=seconds) ==="

mount_top() {
  if ! mountpoint -q "$TOP"; then
    mount -t btrfs -o subvolid=5 /dev/mapper/portable-root "$TOP"
  fi
}

cleanup() {
  mountpoint -q "$TOP" && umount "$TOP" || true
}
trap cleanup EXIT

snapshot_root() {
  local name="$1"
  mount_top
  btrfs subvolume snapshot -r "$TOP/@root" "$TOP/@snapshots/$name"
}

replace_snapshot() {
  local name="$1"
  mount_top
  if [[ -e "$TOP/@snapshots/$name" ]]; then
    btrfs subvolume delete "$TOP/@snapshots/$name"
  fi
  btrfs subvolume snapshot -r "$TOP/@root" "$TOP/@snapshots/$name"
}

prune_preupdate() {
  mount_top
  mapfile -t snaps < <(
    find "$TOP/@snapshots" -mindepth 1 -maxdepth 1 -type d       -name 'pre-update-*' -printf '%f\n' | sort
  )
  local count="${#snaps[@]}"
  if (( count <= KEEP_PREUPDATE )); then
    return
  fi
  local remove=$((count - KEEP_PREUPDATE))
  local i
  for ((i=0; i<remove; i++)); do
    btrfs subvolume delete "$TOP/@snapshots/${snaps[$i]}"
  done
}

validate_post_reinit() {
  if [[ -s "$PENDING" ]]; then
    echo "Validating post-update execution state."
    if [[ -n "$(dpkg --audit)" ]]; then
      echo "dpkg audit failed; refusing graphical session." >&2
      exit 1
    fi
    replace_snapshot last-known-good
    rm -f "$PENDING"
    prune_preupdate
  fi
}

package_fingerprint() {
  {
    dpkg-query -W -f='${binary:Package}\t${Version}\n' 2>/dev/null || true
    snap list 2>/dev/null || true
  } | sha256sum | awk '{print $1}'
}

newest_kernel() {
  local link
  if [[ -L /boot/vmlinuz ]]; then
    link="$(readlink -f /boot/vmlinuz)"
    basename "$link" | sed 's/^vmlinuz-//'
    return
  fi
  find /boot -maxdepth 1 -type f -name 'vmlinuz-*' -printf '%f\n' |
    sed 's/^vmlinuz-//' | sort -V | tail -n1
}

fail_closed() {
  echo
  echo "Update gate failed. Graphical session remains blocked."
  echo "Use the maintenance console to correct networking/package state,"
  echo "then run: sudo systemctl restart portable-update-gate.service"
  systemctl start getty@tty1.service || true
}

transition_and_wait() {
  local action="$1"
  trap - ERR
  trap - EXIT
  sync
  systemctl "$action" --no-block
  # Do not return success and accidentally release graphical.target while
  # systemd is transitioning execution state.
  while :; do sleep 3600; done
}

trap fail_closed ERR

validate_post_reinit

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
snapshot_root "pre-update-$stamp"

before="$(package_fingerprint)"
before_microcode="$(dpkg-query -W -f='${Version}' amd64-microcode 2>/dev/null || true)"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y full-upgrade

# Block snapd's independent automatic cadence. A system-wide auto-refresh hold
# does not block an explicit general 'snap refresh', so this gate remains the
# single orchestration point.
systemctl start snapd.socket snapd.service || true
snap refresh --hold=forever || true
snap refresh

after="$(package_fingerprint)"
after_microcode="$(dpkg-query -W -f='${Version}' amd64-microcode 2>/dev/null || true)"

if [[ "$before" == "$after" ]]; then
  echo "No executable state changed."
  prune_preupdate
  exit 0
fi

printf 'updated=%s\n' "$(date -u +%Y%m%dT%H%M%SZ)" >"$PENDING"

running_kernel="$(uname -r)"
expected_kernel="$(newest_kernel)"

if [[ -n "$expected_kernel" && "$running_kernel" != "$expected_kernel" ]]; then
  echo "A new kernel is installed ($expected_kernel; running $running_kernel)."
  echo "Cold boot is required before an interactive session."
  transition_and_wait poweroff
fi

if [[ "$before_microcode" != "$after_microcode" ]]; then
  echo "CPU microcode changed. Cold boot is required before an interactive session."
  transition_and_wait poweroff
fi

echo "Userspace changed; performing soft reboot before interactive session."
transition_and_wait soft-reboot
