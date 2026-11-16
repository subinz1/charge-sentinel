import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch


DOCTOR_PATH = Path(__file__).parents[1] / 'src' / 'charge-sentinel-doctor.py'
SPEC = importlib.util.spec_from_file_location('charge_sentinel_doctor', DOCTOR_PATH)
DOCTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DOCTOR)


def completed(arguments, **_kwargs):
    if arguments[:2] == ['gnome-shell', '--version']:
        return subprocess.CompletedProcess(arguments, 0, stdout='GNOME Shell 50.5\n', stderr='')
    return subprocess.CompletedProcess(arguments, 1, stdout='', stderr='Extension does not exist\n')


def disabled_extension(arguments, **_kwargs):
    if arguments[:2] == ['gnome-shell', '--version']:
        return subprocess.CompletedProcess(arguments, 0, stdout='GNOME Shell 50.5\n', stderr='')
    return subprocess.CompletedProcess(arguments, 0, stdout='State: DISABLED\n', stderr='')


def unsupported_shell(arguments, **_kwargs):
    if arguments[:2] == ['gnome-shell', '--version']:
        return subprocess.CompletedProcess(arguments, 0, stdout='GNOME Shell 49.5\n', stderr='')
    return subprocess.CompletedProcess(arguments, 0, stdout='State: ACTIVE\n', stderr='')


class ChargeSentinelDoctorTests(unittest.TestCase):
    def test_check_mode_succeeds_for_a_healthy_installation(self):
        output = io.StringIO()
        with (
            patch.object(sys, 'argv', ['charge-sentinel-doctor', '--check']),
            patch.object(DOCTOR, 'diagnose', return_value={'healthy': True}),
            redirect_stdout(output),
        ):
            self.assertEqual(DOCTOR.main(), 0)

        self.assertEqual(output.getvalue(), '{\n  "healthy": true\n}\n')

    def test_check_mode_fails_for_an_unhealthy_installation(self):
        output = io.StringIO()
        with (
            patch.object(sys, 'argv', ['charge-sentinel-doctor', '--check']),
            patch.object(DOCTOR, 'diagnose', return_value={'healthy': False}),
            redirect_stdout(output),
        ):
            self.assertEqual(DOCTOR.main(), 1)

        self.assertEqual(output.getvalue(), '{\n  "healthy": false\n}\n')

    def test_reports_a_fresh_session_that_has_not_seen_the_extension(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            extension = root / 'extension'
            schema = extension / 'schemas'
            schema.mkdir(parents=True)
            (extension / 'metadata.json').write_text(
                '{"shell-version": ["50"]}', encoding='utf-8'
            )
            (extension / 'extension.js').write_text('', encoding='utf-8')
            (schema / 'gschemas.compiled').write_bytes(b'compiled')
            helper = root / 'charge-sentinel-helper'
            helper.write_text('#!/bin/sh\n', encoding='utf-8')
            helper.chmod(0o755)
            capabilities = root / 'charge_sentinel_capabilities.py'
            capabilities.write_text('', encoding='utf-8')
            policy = root / 'charge-sentinel.policy'
            policy.write_text('<policyconfig/>', encoding='utf-8')

            result = DOCTOR.diagnose(extension, helper, policy, completed, capabilities)

        self.assertFalse(result['healthy'])
        self.assertTrue(result['checks']['extension_files'])
        self.assertIn('Log out and back in', result['next_steps'][0])

    def test_reports_missing_package_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = DOCTOR.diagnose(root / 'missing', root / 'helper', root / 'policy', completed)

        self.assertFalse(result['healthy'])
        self.assertIn('Reinstall the Charge Sentinel RPM', result['next_steps'][0])

    def test_reports_a_visible_but_disabled_extension(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            extension = root / 'extension'
            schema = extension / 'schemas'
            schema.mkdir(parents=True)
            (extension / 'metadata.json').write_text(
                '{"shell-version": ["50"]}', encoding='utf-8'
            )
            (extension / 'extension.js').write_text('', encoding='utf-8')
            (schema / 'gschemas.compiled').write_bytes(b'compiled')
            helper = root / 'charge-sentinel-helper'
            helper.write_text('#!/bin/sh\n', encoding='utf-8')
            helper.chmod(0o755)
            capabilities = root / 'charge_sentinel_capabilities.py'
            capabilities.write_text('', encoding='utf-8')
            policy = root / 'charge-sentinel.policy'
            policy.write_text('<policyconfig/>', encoding='utf-8')

            result = DOCTOR.diagnose(extension, helper, policy, disabled_extension, capabilities)

        self.assertFalse(result['healthy'])
        self.assertTrue(result['checks']['extension_visible_to_current_session'])
        self.assertFalse(result['checks']['extension_enabled'])
        self.assertIn('Enable the extension', result['next_steps'][0])

    def test_reports_an_incompatible_gnome_shell_version(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            extension = root / 'extension'
            schema = extension / 'schemas'
            schema.mkdir(parents=True)
            (extension / 'metadata.json').write_text(
                '{"shell-version": ["50"]}', encoding='utf-8'
            )
            (extension / 'extension.js').write_text('', encoding='utf-8')
            (schema / 'gschemas.compiled').write_bytes(b'compiled')
            helper = root / 'charge-sentinel-helper'
            helper.write_text('#!/bin/sh\n', encoding='utf-8')
            helper.chmod(0o755)
            capabilities = root / 'charge_sentinel_capabilities.py'
            capabilities.write_text('', encoding='utf-8')
            policy = root / 'charge-sentinel.policy'
            policy.write_text('<policyconfig/>', encoding='utf-8')

            result = DOCTOR.diagnose(extension, helper, policy, unsupported_shell, capabilities)

        self.assertFalse(result['healthy'])
        self.assertFalse(result['checks']['supported_gnome_shell'])
        self.assertIn('supports the current GNOME Shell version', result['next_steps'][0])

    def test_reports_a_missing_helper_capability_module(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            extension = root / 'extension'
            schema = extension / 'schemas'
            schema.mkdir(parents=True)
            (extension / 'metadata.json').write_text(
                '{"shell-version": ["50"]}', encoding='utf-8'
            )
            (extension / 'extension.js').write_text('', encoding='utf-8')
            (schema / 'gschemas.compiled').write_bytes(b'compiled')
            helper = root / 'charge-sentinel-helper'
            helper.write_text('#!/bin/sh\n', encoding='utf-8')
            helper.chmod(0o755)
            policy = root / 'charge-sentinel.policy'
            policy.write_text('<policyconfig/>', encoding='utf-8')

            result = DOCTOR.diagnose(
                extension,
                helper,
                policy,
                disabled_extension,
                root / 'charge_sentinel_capabilities.py',
            )

        self.assertFalse(result['healthy'])
        self.assertFalse(result['checks']['helper_capabilities'])
        self.assertIn('Reinstall the Charge Sentinel RPM', result['next_steps'][0])
