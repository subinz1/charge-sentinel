# Charge Sentinel

Charge Sentinel is a Fedora-first GNOME Shell extension that protects supported laptop batteries from spending months at 100% charge.

It adds a compact status icon and a Quick Settings tile to GNOME. The tile shows the current battery state, applies practical charge-limit presets, and opens settings for custom limits.

## What it controls

On laptops whose Linux battery driver exposes charge thresholds, Charge Sentinel tells the embedded controller to:

- start charging below a chosen lower limit;
- stop charging at a chosen upper limit;
- optionally pause charging immediately while the charger remains connected.

It does **not** cut AC power or pretend to work on unsupported hardware. For example, ThinkPads expose these controls through `thinkpad_acpi` at `/sys/class/power_supply/BAT*/charge_control_{start,end}_threshold`.

The initial target is Fedora GNOME 50+ and modern ThinkPads. The helper auto-detects supported batteries before it writes anything.

## Presets

| Preset | Start | Stop | Intended use |
| --- | ---: | ---: | --- |
| Desk | 75% | 80% | Laptop stays connected most of the time |
| Balanced | 70% | 85% | Mix of desk and portable use |
| Optimal | 20% | 95% | Your preferred broad operating range |
| Travel | 96% | 100% | Maximum runtime for a trip |

Users can set custom values as well. A wide range such as 20% → 100% is technically valid on supported ThinkPads, but it is not the default because it does not limit time spent at a high state of charge.

## Architecture

```text
GNOME Shell extension
  ├─ reads battery status from /sys/class/power_supply
  └─ invokes a narrowly scoped Polkit helper for changes
       └─ validates values and writes only known battery-control files
```

The GNOME extension never runs as root. The helper only accepts a battery name discovered beneath `/sys/class/power_supply`, validates threshold ranges, and writes the two kernel-supported controls.

## Development

Requirements: Fedora GNOME, `gjs`, `gnome-extensions`, `glib2`, Python 3, and Polkit.

```bash
make validate
make package
```

The generated extension bundle is placed in `dist/`.

For a local installation, review the files first, then run:

```bash
bash install.sh
```

This installs the extension for the current user and asks for administrator authentication only to install the root-owned helper and its Polkit rule. Restart the GNOME Shell session or log out and back in after installation on Wayland.

## Current hardware support

Charge Sentinel detects the standard Linux `charge_control_start_threshold`, `charge_control_end_threshold`, and optional `charge_behaviour` attributes. Actual support and valid ranges are determined by the laptop firmware and its kernel driver.

For the ThinkPad P1 Gen 7 used during development, the driver exposes both threshold controls and `auto`, `inhibit-charge`, and `force-discharge` charge behaviours. Charge Sentinel only surfaces the safe `auto` and `inhibit-charge` behaviours.
