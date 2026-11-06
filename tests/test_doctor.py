import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest


DOCTOR_PATH = Path(__file__).parents[1] / 'src' / 'charge-sentinel-doctor.py'
SPEC = importlib.util.spec_from_file_location('charge_sentinel_doctor', DOCTOR_PATH)
DOCTOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(DOCTOR)


def completed(arguments, **_kwargs):
    if arguments[:2] == ['gnome-shell', '--version']:
        return subprocess.CompletedProcess(arguments, 0, stdout='GNOME Shell 50.5\n', stderr='')
    return subprocess.CompletedProcess(arguments, 1, stdout='', stderr='Extension does not exist\n')


class ChargeSentinelDoctorTests(unittest.TestCase):
    def test_reports_a_fresh_session_that_has_not_seen_the_extension(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            extension = root / 'extension'
            schema = extension / 'schemas'
            schema.mkdir(parents=True)
            (extension / 'metadata.json').write_text('{}', encoding='utf-8')
            (extension / 'extension.js').write_text('', encoding='utf-8')
            (schema / 'gschemas.compiled').write_bytes(b'compiled')
            helper = root / 'charge-sentinel-helper'
            helper.write_text('#!/bin/sh\n', encoding='utf-8')
            helper.chmod(0o755)
            policy = root / 'charge-sentinel.policy'
            policy.write_text('<policyconfig/>', encoding='utf-8')

            result = DOCTOR.diagnose(extension, helper, policy, completed)

        self.assertFalse(result['healthy'])
        self.assertTrue(result['checks']['extension_files'])
        self.assertIn('Log out and back in', result['next_steps'][0])

    def test_reports_missing_package_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            result = DOCTOR.diagnose(root / 'missing', root / 'helper', root / 'policy', completed)

        self.assertFalse(result['healthy'])
        self.assertIn('Reinstall the Charge Sentinel RPM', result['next_steps'][0])
