#!/usr/bin/env python3
"""Diagnose a Charge Sentinel installation without changing system state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
from typing import Callable


UUID = 'charge-sentinel@subinz1.github.io'
EXTENSION_ROOT = Path('/usr/share/gnome-shell/extensions') / UUID
HELPER_PATH = Path('/usr/libexec/charge-sentinel-helper')
HELPER_CAPABILITIES_PATH = Path('/usr/libexec/charge_sentinel_capabilities.py')
POLKIT_POLICY = Path('/usr/share/polkit-1/actions/io.github.subinz1.charge-sentinel.policy')


def command_output(
    arguments: list[str],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    try:
        result = runner(arguments, capture_output=True, check=False, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError) as error:
        return False, str(error)
    return result.returncode == 0, (result.stdout or result.stderr).strip()


def extension_is_enabled(extension_info: str) -> bool:
    """Return whether `gnome-extensions info` reports an enabled extension."""
    match = re.search(
        r'^\s*state:\s*(enabled|active)\s*$',
        extension_info,
        re.IGNORECASE | re.MULTILINE,
    )
    return match is not None


def extension_supports_shell(extension_root: Path, shell_version: str) -> bool:
    match = re.search(r'GNOME Shell\s+(\d+)', shell_version, re.IGNORECASE)
    if match is None:
        return False

    try:
        metadata = json.loads((extension_root / 'metadata.json').read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return False

    supported_versions = metadata.get('shell-version')
    return isinstance(supported_versions, list) and match.group(1) in supported_versions


def diagnose(
    extension_root: Path = EXTENSION_ROOT,
    helper_path: Path = HELPER_PATH,
    polkit_policy: Path = POLKIT_POLICY,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    helper_capabilities_path: Path = HELPER_CAPABILITIES_PATH,
) -> dict[str, object]:
    schema = extension_root / 'schemas' / 'gschemas.compiled'
    checks = {
        'extension_files': (extension_root / 'metadata.json').is_file() and (extension_root / 'extension.js').is_file(),
        'compiled_schema': schema.is_file(),
        'privileged_helper': helper_path.is_file() and helper_path.stat().st_mode & 0o111 != 0,
        'helper_capabilities': helper_capabilities_path.is_file(),
        'polkit_policy': polkit_policy.is_file(),
    }

    shell_found, shell_version = command_output(['gnome-shell', '--version'], runner)
    extension_found, extension_info = command_output(['gnome-extensions', 'info', UUID], runner)
    checks['gnome_shell'] = shell_found
    checks['extension_visible_to_current_session'] = extension_found
    checks['extension_enabled'] = extension_found and extension_is_enabled(extension_info)
    checks['supported_gnome_shell'] = shell_found and extension_supports_shell(extension_root, shell_version)

    actions: list[str] = []
    if not all(
        checks[key]
        for key in (
            'extension_files',
            'compiled_schema',
            'privileged_helper',
            'helper_capabilities',
            'polkit_policy',
        )
    ):
        actions.append('Reinstall the Charge Sentinel RPM to restore missing package files.')
    elif not shell_found:
        actions.append('Run this diagnostic from a GNOME session where gnome-shell is available.')
    elif not checks['supported_gnome_shell']:
        actions.append('Install a Charge Sentinel build that supports the current GNOME Shell version.')
    elif not extension_found:
        actions.append('Log out and back in, then run: gnome-extensions enable ' + UUID)
    elif not checks['extension_enabled']:
        actions.append('Enable the extension with: gnome-extensions enable ' + UUID)
    else:
        actions.append('Charge Sentinel is enabled for the current session.')

    return {
        'healthy': all(checks.values()),
        'checks': checks,
        'gnome_shell': shell_version,
        'extension_info': extension_info,
        'next_steps': actions,
    }


def main() -> int:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument(
        '--check',
        action='store_true',
        help='Exit with a non-zero status when the installation is unhealthy.',
    )
    arguments = argument_parser.parse_args()
    result = diagnose()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result['healthy'] or not arguments.check else 1


if __name__ == '__main__':
    raise SystemExit(main())
