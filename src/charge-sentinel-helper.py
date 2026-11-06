#!/usr/bin/env python3
"""Root-only, narrowly scoped controller for Linux battery charge thresholds."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from charge_sentinel_capabilities import detect_linux, supported_linux_batteries


POWER_SUPPLY_ROOT = Path('/sys/class/power_supply')
SAFE_BEHAVIOURS = {'auto', 'inhibit-charge'}


class ChargeSentinelError(RuntimeError):
    """A request cannot be safely applied to the battery controller."""


def require_root(effective_user_id: int | None = None) -> None:
    if effective_user_id is None:
        effective_user_id = os.geteuid()
    if effective_user_id != 0:
        raise ChargeSentinelError('Changing charge settings requires administrator authentication.')


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8').strip()


def supported_batteries() -> dict[str, Path]:
    return supported_linux_batteries(POWER_SUPPLY_ROOT)


def battery_path(name: str) -> Path:
    batteries = supported_batteries()
    if name not in batteries:
        raise ChargeSentinelError(f'Unsupported battery: {name}')
    return batteries[name]


def write_value(path: Path, value: int | str) -> None:
    try:
        path.write_text(f'{value}\n', encoding='ascii')
    except OSError as error:
        raise ChargeSentinelError(f'Could not write {path.name}: {error.strerror}') from error


def validate_thresholds(start: int, end: int) -> None:
    if not 0 <= start <= 99:
        raise ChargeSentinelError('Start threshold must be between 0 and 99.')
    if not 1 <= end <= 100:
        raise ChargeSentinelError('Stop threshold must be between 1 and 100.')
    if start and start >= end:
        raise ChargeSentinelError('Start threshold must be lower than the stop threshold.')


def set_thresholds(name: str, start: int, end: int) -> dict[str, int | str]:
    require_root()
    validate_thresholds(start, end)
    battery = battery_path(name)
    start_path = battery / 'charge_control_start_threshold'
    end_path = battery / 'charge_control_end_threshold'

    try:
        current_start = int(read_text(start_path))
        current_end = int(read_text(end_path))
    except (OSError, ValueError) as error:
        raise ChargeSentinelError('Could not read current charge thresholds.') from error

    # Keep every intermediate state valid while moving between presets.
    if start > current_end:
        writes = [(end_path, end, current_end), (start_path, start, current_start)]
    elif end < current_start:
        writes = [(start_path, start, current_start), (end_path, end, current_end)]
    else:
        writes = [(start_path, start, current_start), (end_path, end, current_end)]

    applied: list[tuple[Path, int]] = []
    try:
        for path, value, previous_value in writes:
            if value == previous_value:
                continue
            write_value(path, value)
            applied.append((path, previous_value))
    except ChargeSentinelError as error:
        rollback_errors: list[str] = []
        for path, previous_value in reversed(applied):
            try:
                write_value(path, previous_value)
            except ChargeSentinelError:
                rollback_errors.append(path.name)
        if rollback_errors:
            raise ChargeSentinelError(
                'Could not apply charge thresholds and could not restore ' + ', '.join(rollback_errors) + '.'
            ) from error
        raise ChargeSentinelError('Could not apply charge thresholds; previous values were restored.') from error

    return {
        'battery': name,
        'start': int(read_text(start_path)),
        'end': int(read_text(end_path)),
    }


def set_behaviour(name: str, behaviour: str) -> dict[str, str]:
    require_root()
    if behaviour not in SAFE_BEHAVIOURS:
        raise ChargeSentinelError('Only auto and inhibit-charge are supported.')

    battery = battery_path(name)
    behaviour_path = battery / 'charge_behaviour'
    if not behaviour_path.is_file():
        raise ChargeSentinelError('This battery does not support charge behaviour control.')

    advertised = read_text(behaviour_path)
    if behaviour not in advertised.split():
        raise ChargeSentinelError(f'The firmware does not support {behaviour}.')

    write_value(behaviour_path, behaviour)
    return {'battery': name, 'behaviour': read_text(behaviour_path)}


def status() -> dict[str, object]:
    items: list[dict[str, str]] = []
    for name, battery in supported_batteries().items():
        values = {'name': name}
        for attribute in (
            'capacity',
            'status',
            'charge_control_start_threshold',
            'charge_control_end_threshold',
            'charge_behaviour',
        ):
            path = battery / attribute
            if path.is_file():
                values[attribute] = read_text(path)
        items.append(values)
    return {
        'supported': bool(items),
        'batteries': items,
        'capabilities': detect_linux(POWER_SUPPLY_ROOT).to_dict(),
    }


def parser() -> argparse.ArgumentParser:
    argument_parser = argparse.ArgumentParser(description=__doc__)
    subparsers = argument_parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('status', help='Print supported battery status as JSON.')

    thresholds = subparsers.add_parser('set-thresholds', help='Set safe start and stop thresholds.')
    thresholds.add_argument('battery')
    thresholds.add_argument('start', type=int)
    thresholds.add_argument('end', type=int)

    behaviour = subparsers.add_parser('set-behaviour', help='Set a supported charging behaviour.')
    behaviour.add_argument('battery')
    behaviour.add_argument('behaviour', choices=sorted(SAFE_BEHAVIOURS))
    return argument_parser


def main() -> int:
    arguments = parser().parse_args()
    try:
        if arguments.command == 'status':
            result = status()
        elif arguments.command == 'set-thresholds':
            result = set_thresholds(arguments.battery, arguments.start, arguments.end)
        else:
            result = set_behaviour(arguments.battery, arguments.behaviour)
    except ChargeSentinelError as error:
        print(f'Charge Sentinel: {error}', file=sys.stderr)
        return 1

    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
