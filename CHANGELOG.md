# Changelog

## Unreleased

- Add automatic and explicit battery selection for multi-battery systems.
- Show each supported battery's live charge and status in the Quick Settings picker.
- Mark the active charge profile and prevent invalid custom ranges from invoking the helper.
- Add `charge-sentinel-doctor --check` for scriptable installation health checks.

## 0.1.1 — 2026-11-06

- Require administrator privileges for every battery-controller write.
- Restore the prior charge thresholds when a multi-step update fails.
- Add `charge-sentinel-doctor` for read-only installation diagnostics.
- Verify the RPM contents and install it in a disposable Fedora CI environment.

## 0.1.0 — 2026-11-05

- Initial Fedora 44 release with a GNOME Quick Settings extension.
- ThinkPad threshold controls, charge presets, and a Polkit-protected helper.
