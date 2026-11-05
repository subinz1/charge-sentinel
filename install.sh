#!/usr/bin/env bash
set -Eeuo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uuid="charge-sentinel@subinz1.github.io"
extension_dir="$HOME/.local/share/gnome-shell/extensions/$uuid"
schema="schemas/org.gnome.shell.extensions.charge-sentinel.gschema.xml"

mkdir -p "$extension_dir/schemas"
install -m 0644 "$root_dir/metadata.json" "$root_dir/extension.js" "$root_dir/prefs.js" "$extension_dir/"
install -m 0644 "$root_dir/$schema" "$extension_dir/schemas/"
glib-compile-schemas "$extension_dir/schemas"

sudo install -D -o root -g root -m 0755 \
  "$root_dir/src/charge-sentinel-helper.py" \
  /usr/local/libexec/charge-sentinel-helper
sudo install -D -o root -g root -m 0644 \
  "$root_dir/src/charge_sentinel_capabilities.py" \
  /usr/local/libexec/charge_sentinel_capabilities.py
sudo install -D -o root -g root -m 0644 \
  "$root_dir/polkit/io.github.subinz1.charge-sentinel.policy" \
  /usr/share/polkit-1/actions/io.github.subinz1.charge-sentinel.policy

gnome-extensions enable "$uuid" || true
printf 'Installed %s. Log out and back in to load a new extension on Wayland.\n' "$uuid"
