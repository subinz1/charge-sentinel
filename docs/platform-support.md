# Cross-platform support model

Charge Sentinel uses a hardware-aware adapter model. A device is never marked as controllable merely because its operating system can report battery percentage.

## Capability states

| State | Meaning in the app |
| --- | --- |
| `supported` | A tested adapter can read and apply validated thresholds. |
| `native-only` | The operating system owns the feature; Charge Sentinel shows the feature and deep-links to its settings, but does not use private APIs. |
| `requires-vendor-tool` | A documented vendor command interface exists but is not installed. |
| `requires-vendor-adapter` | The vendor application exposes a feature, but Charge Sentinel does not yet have a supported automation adapter. |
| `unsupported` | No safe, documented control is available. The app must not offer an Apply button. |

## Adapter matrix

| Platform | Adapter | Capability | Threshold range | Status |
| --- | --- | --- | --- | --- |
| Fedora and other Linux distributions | Linux sysfs | Standard `charge_control_start_threshold` and `charge_control_end_threshold` files | Driver-defined; ThinkPad `0–99%` start and `1–100%` stop | Supported now |
| Fedora ThinkPads | `thinkpad_acpi` | Thresholds plus safe pause/resume where `inhibit-charge` is exposed | `0–99%` start, `1–100%` stop | Supported now |
| Windows Dell | Dell Command \| Configure | Custom BIOS charge configuration | `50–95%` start, `55–100%` stop, minimum 5% gap | Supported after Dell tool detection |
| Windows Lenovo | Lenovo Vantage | Vendor UI exposes thresholds on compatible models | Model-dependent | Detection only until a documented automation adapter is implemented |
| Windows, other manufacturers | Windows generic | Battery reporting only | None | Unsupported for control |
| macOS Tahoe 26.4+ on Apple silicon | macOS Charge Limit | Native System Settings control | `80–100%` stop only | Native-only |
| Older macOS or Intel Mac | Optimized Battery Charging | OS-managed optimization | No user-set range | Native-only |
| ChromeOS | Optimized Charging | Adaptive charging or OS-managed 80% limit | 80% stop only | Native-only |

## Why presets are validated per device

The same percentage values are not portable:

- The current ThinkPad adapter accepts **Optimal 20% → 95%**.
- Dell’s documented custom mode rejects a 20% start; it requires at least 50% and a 5% gap.
- macOS only supplies an upper charge limit, so it cannot implement a 20% lower threshold.
- Consumer ChromeOS exposes a fixed 80% charge-limit mode rather than arbitrary values.

The shared UI must request `capabilities`, render only compatible presets, and label unavailable choices with the reason. It must never silently substitute a different range.

## References

- [Linux ThinkPad ACPI charge threshold documentation](https://docs.kernel.org/admin-guide/laptops/thinkpad-acpi.html)
- [TLP’s ThinkPad charge-threshold ranges](https://linrunner.de/tlp/settings/bc-vendors.html)
- [Dell Command custom battery configuration](https://www.dell.com/support/manuals/en-us/command-powershell-provider/dcpp_2_8_ref_guide/powermanagement)
- [Apple Charge Limit support](https://support.apple.com/102338)
- [ChromeOS Optimized Charging support](https://support.google.com/chromebook/answer/14236882)
