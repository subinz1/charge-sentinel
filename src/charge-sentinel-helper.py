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


def read_thresholds(start_path: Path, end_path: Path) -> tuple[int, int]:
    try:
        return int(read_text(start_path)), int(read_text(end_path))
    except (OSError, ValueError) as error:
        raise ChargeSentinelError('Could not read charge thresholds.') from error


def set_thresholds(name: str, start: int, end: int) -> dict[str, int | str]:
    require_root()
    validate_thresholds(start, end)
    battery = battery_path(name)
    start_path = battery / 'charge_control_start_threshold'
    end_path = battery / 'charge_control_end_threshold'

    current_start, current_end = read_thresholds(start_path, end_path)

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
            applied.append((path, previous_value))
            write_value(path, value)

        applied_start, applied_end = read_thresholds(start_path, end_path)
        if (applied_start, applied_end) != (start, end):
            raise ChargeSentinelError('The battery controller did not accept the requested charge thresholds.')
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
        'start': applied_start,
        'end': applied_end,
    }


def active_behaviour(value: str) -> str | None:
    bracketed = [candidate[1:-1] for candidate in value.split() if candidate.startswith('[') and candidate.endswith(']')]
    if len(bracketed) == 1 and bracketed[0] in SAFE_BEHAVIOURS:
        return bracketed[0]

    known = [candidate for candidate in value.split() if candidate in SAFE_BEHAVIOURS]
    return known[0] if len(known) == 1 else None


def set_behaviour(name: str, behaviour: str) -> dict[str, str]:
    require_root()
    if behaviour not in SAFE_BEHAVIOURS:
        raise ChargeSentinelError('Only auto and inhibit-charge are supported.')

    battery = battery_path(name)
    behaviour_path = battery / 'charge_behaviour'
    if not behaviour_path.is_file():
        raise ChargeSentinelError('This battery does not support charge behaviour control.')

    try:
        previous_value = read_text(behaviour_path)
    except OSError as error:
        raise ChargeSentinelError('Could not read supported charge behaviours.') from error

    advertised = {value.strip('[]') for value in previous_value.split()}
    if behaviour not in advertised:
        raise ChargeSentinelError(f'The firmware does not support {behaviour}.')

    write_value(behaviour_path, behaviour)
    try:
        applied_value = read_text(behaviour_path)
        verification_error = None
    except OSError as error:
        applied_value = ''
        verification_error = error

    if verification_error is not None or active_behaviour(applied_value) != behaviour:
        previous_behaviour = active_behaviour(previous_value)
        if previous_behaviour is not None:
            try:
                write_value(behaviour_path, previous_behaviour)
            except ChargeSentinelError as error:
                raise ChargeSentinelError(
                    'Could not apply the requested charging behaviour or restore the previous behaviour.'
                ) from error
        if verification_error is not None:
            raise ChargeSentinelError(
                'Could not verify the requested charging behaviour; previous behaviour was restored.'
            ) from verification_error
        raise ChargeSentinelError('The battery controller did not accept the requested charging behaviour.')

    return {'battery': name, 'behaviour': applied_value}


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
                try:
                    values[attribute] = read_text(path)
                except OSError:
                    continue
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
