"""Hardware-aware charge-control capability detection for Charge Sentinel.

This module deliberately separates what a platform can *report* from what
Charge Sentinel is allowed to *change*. A missing or vendor-only interface is
never treated as a generic charge-control capability.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import platform as host_platform
import shutil
import subprocess
from typing import Callable


POWER_SUPPLY_ROOT = Path('/sys/class/power_supply')
THINKPAD_MODULE_ROOT = Path('/sys/module/thinkpad_acpi')


@dataclass(frozen=True)
class IntRange:
    minimum: int
    maximum: int

    def to_list(self) -> list[int]:
        return [self.minimum, self.maximum]


@dataclass(frozen=True)
class ChargeCapabilities:
    """Normalized capability contract used by every Charge Sentinel UI."""

    platform: str
    state: str
    adapter: str
    reason: str
    manufacturer: str | None = None
    battery: str | None = None
    start_range: IntRange | None = None
    end_range: IntRange | None = None
    minimum_gap: int | None = None
    actions: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            'platform': self.platform,
            'state': self.state,
            'adapter': self.adapter,
            'reason': self.reason,
            'manufacturer': self.manufacturer,
            'battery': self.battery,
            'start_range': self.start_range.to_list() if self.start_range else None,
            'end_range': self.end_range.to_list() if self.end_range else None,
            'minimum_gap': self.minimum_gap,
            'actions': list(self.actions),
        }


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8').strip()
    except OSError:
        return None


def supported_linux_batteries(power_supply_root: Path = POWER_SUPPLY_ROOT) -> dict[str, Path]:
    """Return only batteries with both standard Linux threshold files."""
    batteries: dict[str, Path] = {}
    if not power_supply_root.exists():
        return batteries

    for candidate in power_supply_root.iterdir():
        if read_text(candidate / 'type') != 'Battery':
            continue
        if (candidate / 'charge_control_start_threshold').is_file() and (
            candidate / 'charge_control_end_threshold'
        ).is_file():
            batteries[candidate.name] = candidate
    return batteries


def detect_linux(
    power_supply_root: Path = POWER_SUPPLY_ROOT,
    thinkpad_module_root: Path = THINKPAD_MODULE_ROOT,
) -> ChargeCapabilities:
    batteries = supported_linux_batteries(power_supply_root)
    if not batteries:
        return ChargeCapabilities(
            platform='linux',
            state='unsupported',
            adapter='linux-sysfs',
            reason='No battery exposes the standard Linux charge-threshold controls.',
        )

    name, battery = next(iter(sorted(batteries.items())))
    behaviours = (read_text(battery / 'charge_behaviour') or '').split()
    actions = ['set-thresholds']
    if 'inhibit-charge' in behaviours:
        actions.extend(['pause-charging', 'resume-automatic-charging'])

    is_thinkpad = thinkpad_module_root.exists()
    return ChargeCapabilities(
        platform='linux',
        state='supported',
        adapter='thinkpad-acpi-sysfs' if is_thinkpad else 'linux-sysfs',
        reason=(
            'ThinkPad firmware exposes start and stop charge thresholds.'
            if is_thinkpad
            else 'The active Linux battery driver exposes standard charge-threshold controls.'
        ),
        battery=name,
        start_range=IntRange(0, 99),
        end_range=IntRange(1, 100),
        minimum_gap=1,
        actions=tuple(actions),
    )


def detect_windows(manufacturer: str, dell_command_path: str | None = None) -> ChargeCapabilities:
    """Return only vendor capabilities with a documented command interface."""
    normalized = manufacturer.casefold()
    if 'dell' in normalized:
        if dell_command_path:
            return ChargeCapabilities(
                platform='windows',
                state='supported',
                adapter='dell-command-configure',
                manufacturer=manufacturer,
                reason='Dell Command | Configure provides documented custom battery thresholds.',
                start_range=IntRange(50, 95),
                end_range=IntRange(55, 100),
                minimum_gap=5,
                actions=('set-thresholds',),
            )
        return ChargeCapabilities(
            platform='windows',
            state='requires-vendor-tool',
            adapter='dell-command-configure',
            manufacturer=manufacturer,
            reason='Install Dell Command | Configure before Charge Sentinel can set thresholds.',
        )

    if 'lenovo' in normalized:
        return ChargeCapabilities(
            platform='windows',
            state='requires-vendor-adapter',
            adapter='lenovo-vantage',
            manufacturer=manufacturer,
            reason='Lenovo Vantage can expose charge thresholds, but this adapter needs a supported automation interface.',
        )

    return ChargeCapabilities(
        platform='windows',
        state='unsupported',
        adapter='windows-generic',
        manufacturer=manufacturer or None,
        reason='Windows has no generic public API for changing laptop charge thresholds.',
    )


def detect_macos(version: str, machine: str) -> ChargeCapabilities:
    """Describe Apple’s OS-native controls without attempting private APIs."""
    apple_silicon = machine.casefold() in {'arm64', 'aarch64'}
    try:
        major, minor, *_ = (int(part) for part in version.split('.'))
    except ValueError:
        major, minor = 0, 0

    if apple_silicon and (major, minor) >= (26, 4):
        return ChargeCapabilities(
            platform='macos',
            state='native-only',
            adapter='macos-charge-limit',
            reason='macOS provides a native Apple silicon charge limit in System Settings.',
            end_range=IntRange(80, 100),
        )

    return ChargeCapabilities(
        platform='macos',
        state='native-only',
        adapter='macos-optimized-charging',
        reason='Use macOS Optimized Battery Charging; no supported custom start/stop adapter is available.',
    )


def detect_chromeos() -> ChargeCapabilities:
    return ChargeCapabilities(
        platform='chromeos',
        state='native-only',
        adapter='chromeos-optimized-charging',
        reason='ChromeOS offers adaptive charging or an OS-managed 80% charge limit.',
        end_range=IntRange(80, 80),
    )


def _windows_manufacturer(runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> str:
    try:
        result = runner(
            ['powershell.exe', '-NoProfile', '-Command', '(Get-CimInstance Win32_ComputerSystem).Manufacturer'],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def _dell_command_path() -> str | None:
    return shutil.which('cctk.exe') or shutil.which('cctk')


def detect_current_platform() -> ChargeCapabilities:
    system = host_platform.system()
    if system == 'Linux':
        lsb_release = read_text(Path('/etc/lsb-release')) or ''
        if 'CHROMEOS' in lsb_release.upper():
            return detect_chromeos()
        return detect_linux()
    if system == 'Windows':
        return detect_windows(_windows_manufacturer(), _dell_command_path())
    if system == 'Darwin':
        return detect_macos(host_platform.mac_ver()[0], host_platform.machine())
    return ChargeCapabilities(
        platform=system.casefold() or 'unknown',
        state='unsupported',
        adapter='none',
        reason='Charge Sentinel has no adapter for this operating system.',
    )
