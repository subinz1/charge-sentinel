#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uuid="charge-sentinel@subinz1.github.io"
extension_dir="$HOME/.local/share/gnome-shell/extensions/$uuid"
schema="schemas/org.gnome.shell.extensions.charge-sentinel.gschema.xml"

if [[ "${1:-}" == "--help" ]]; then
  printf 'Usage: %s\n' "${BASH_SOURCE[0]}"
  printf 'Install Charge Sentinel from this checkout for the current user.\n'
  exit 0
fi

if [[ $# -ne 0 ]]; then
  printf 'Unexpected argument. Run %s --help for usage.\n' "${BASH_SOURCE[0]}" >&2
  exit 2
fi

if command -v rpm >/dev/null && rpm -q charge-sentinel >/dev/null 2>&1; then
  printf 'Charge Sentinel is already installed from an RPM. Update it with dnf instead of the local installer.\n' >&2
  exit 1
fi

mkdir -p "$extension_dir/schemas"
install -m 0644 "$root_dir/metadata.json" "$root_dir/extension.js" "$root_dir/prefs.js" "$extension_dir/"
install -m 0644 "$root_dir/$schema" "$extension_dir/schemas/"
glib-compile-schemas "$extension_dir/schemas"

sudo install -D -o root -g root -m 0755 \
  "$root_dir/src/charge-sentinel-helper.py" \
  /usr/libexec/charge-sentinel-helper
sudo install -D -o root -g root -m 0644 \
  "$root_dir/src/charge_sentinel_capabilities.py" \
  /usr/libexec/charge_sentinel_capabilities.py
sudo install -D -o root -g root -m 0755 \
  "$root_dir/src/charge-sentinel-doctor.py" \
  /usr/bin/charge-sentinel-doctor
sudo install -D -o root -g root -m 0644 \
  "$root_dir/polkit/io.github.subinz1.charge-sentinel.policy" \
  /usr/share/polkit-1/actions/io.github.subinz1.charge-sentinel.policy

if gnome-extensions enable "$uuid"; then
  printf 'Installed and enabled %s. Log out and back in to load a new extension on Wayland.\n' "$uuid"
else
  printf 'Installed %s, but it could not be enabled in this session. Log out and back in, then run charge-sentinel-doctor if it remains unavailable.\n' "$uuid" >&2
fi
