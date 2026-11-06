#!/usr/bin/env python3
"""Diagnose a Charge Sentinel installation without changing system state."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Callable


UUID = 'charge-sentinel@subinz1.github.io'
EXTENSION_ROOT = Path('/usr/share/gnome-shell/extensions') / UUID
HELPER_PATH = Path('/usr/libexec/charge-sentinel-helper')
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


def diagnose(
    extension_root: Path = EXTENSION_ROOT,
    helper_path: Path = HELPER_PATH,
    polkit_policy: Path = POLKIT_POLICY,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    schema = extension_root / 'schemas' / 'gschemas.compiled'
    checks = {
        'extension_files': (extension_root / 'metadata.json').is_file() and (extension_root / 'extension.js').is_file(),
        'compiled_schema': schema.is_file(),
        'privileged_helper': helper_path.is_file() and helper_path.stat().st_mode & 0o111 != 0,
        'polkit_policy': polkit_policy.is_file(),
    }

    shell_found, shell_version = command_output(['gnome-shell', '--version'], runner)
    extension_found, extension_info = command_output(['gnome-extensions', 'info', UUID], runner)
    checks['gnome_shell'] = shell_found
    checks['extension_visible_to_current_session'] = extension_found

    actions: list[str] = []
    if not all(checks[key] for key in ('extension_files', 'compiled_schema', 'privileged_helper', 'polkit_policy')):
        actions.append('Reinstall the Charge Sentinel RPM to restore missing package files.')
    elif not extension_found:
        actions.append('Log out and back in, then run: gnome-extensions enable ' + UUID)
    else:
        actions.append('Enable the extension with: gnome-extensions enable ' + UUID)

    return {
        'healthy': all(checks.values()),
        'checks': checks,
        'gnome_shell': shell_version,
        'extension_info': extension_info,
        'next_steps': actions,
    }


if __name__ == '__main__':
    print(json.dumps(diagnose(), indent=2, sort_keys=True))
