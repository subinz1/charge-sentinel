import importlib.util
import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


HELPER_PATH = Path(__file__).parents[1] / 'src' / 'charge-sentinel-helper.py'
sys.path.insert(0, str(HELPER_PATH.parent))
SPEC = importlib.util.spec_from_file_location('charge_sentinel_helper', HELPER_PATH)
HELPER = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(HELPER)


class ChargeSentinelHelperTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.previous_root = HELPER.POWER_SUPPLY_ROOT
        self.previous_require_root = HELPER.require_root
        HELPER.POWER_SUPPLY_ROOT = self.root
        HELPER.require_root = lambda: None
        self.battery = self.root / 'BAT0'
        self.battery.mkdir()
        (self.battery / 'type').write_text('Battery\n', encoding='utf-8')
        (self.battery / 'capacity').write_text('62\n', encoding='utf-8')
        (self.battery / 'status').write_text('Charging\n', encoding='utf-8')
        (self.battery / 'charge_control_start_threshold').write_text('75\n', encoding='utf-8')
        (self.battery / 'charge_control_end_threshold').write_text('80\n', encoding='utf-8')
        (self.battery / 'charge_behaviour').write_text('[auto] inhibit-charge force-discharge\n', encoding='utf-8')

    def tearDown(self):
        HELPER.POWER_SUPPLY_ROOT = self.previous_root
        HELPER.require_root = self.previous_require_root
        self.temporary_directory.cleanup()

    def test_detects_supported_battery(self):
        self.assertEqual(list(HELPER.supported_batteries()), ['BAT0'])
        state = HELPER.status()
        self.assertTrue(state['supported'])
        self.assertEqual(state['batteries'][0]['capacity'], '62')
        self.assertEqual(state['capabilities']['state'], 'supported')

    def test_applies_thresholds_in_a_safe_order(self):
        result = HELPER.set_thresholds('BAT0', 96, 100)
        self.assertEqual(result, {'battery': 'BAT0', 'start': 96, 'end': 100})

    def test_rejects_invalid_thresholds(self):
        with self.assertRaises(HELPER.ChargeSentinelError):
            HELPER.set_thresholds('BAT0', 90, 80)

    def test_accepts_zero_as_a_valid_start_threshold(self):
        result = HELPER.set_thresholds('BAT0', 0, 80)
        self.assertEqual(result, {'battery': 'BAT0', 'start': 0, 'end': 80})

    def test_requires_administrator_access_for_writes(self):
        with self.assertRaises(HELPER.ChargeSentinelError):
            self.previous_require_root(effective_user_id=1000)

    def test_restores_the_previous_threshold_after_a_partial_write_failure(self):
        original_write_value = HELPER.write_value

        def fail_when_setting_start(path, value):
            if path.name == 'charge_control_start_threshold' and value == 96:
                original_write_value(path, value)
                raise HELPER.ChargeSentinelError('simulated firmware failure')
            original_write_value(path, value)

        HELPER.write_value = fail_when_setting_start
        try:
            with self.assertRaisesRegex(HELPER.ChargeSentinelError, 'previous values were restored'):
                HELPER.set_thresholds('BAT0', 96, 100)
        finally:
            HELPER.write_value = original_write_value

        self.assertEqual(
            (self.battery / 'charge_control_start_threshold').read_text(encoding='utf-8'),
            '75\n',
        )
        self.assertEqual(
            (self.battery / 'charge_control_end_threshold').read_text(encoding='utf-8'),
            '80\n',
        )

    def test_restores_thresholds_when_the_controller_silently_rejects_a_write(self):
        original_write_value = HELPER.write_value

        def ignore_start_threshold(path, value):
            if path.name == 'charge_control_start_threshold' and value == 96:
                return
            original_write_value(path, value)

        HELPER.write_value = ignore_start_threshold
        try:
            with self.assertRaisesRegex(HELPER.ChargeSentinelError, 'previous values were restored'):
                HELPER.set_thresholds('BAT0', 96, 100)
        finally:
            HELPER.write_value = original_write_value

        self.assertEqual(
            (self.battery / 'charge_control_start_threshold').read_text(encoding='utf-8'),
            '75\n',
        )
        self.assertEqual(
            (self.battery / 'charge_control_end_threshold').read_text(encoding='utf-8'),
            '80\n',
        )

    def test_only_allows_safe_charge_behaviours(self):
        result = HELPER.set_behaviour('BAT0', 'inhibit-charge')
        self.assertEqual(result['battery'], 'BAT0')
        self.assertEqual((self.battery / 'charge_behaviour').read_text(encoding='utf-8'), 'inhibit-charge\n')
        with self.assertRaises(HELPER.ChargeSentinelError):
            HELPER.set_behaviour('BAT0', 'force-discharge')

    def test_allows_the_bracketed_active_auto_behaviour(self):
        result = HELPER.set_behaviour('BAT0', 'auto')
        self.assertEqual(result['battery'], 'BAT0')
        self.assertEqual((self.battery / 'charge_behaviour').read_text(encoding='utf-8'), 'auto\n')

    def test_restores_the_previous_behaviour_when_the_controller_rejects_a_write(self):
        original_write_value = HELPER.write_value

        def ignore_inhibit_charge(path, value):
            if path.name == 'charge_behaviour' and value == 'inhibit-charge':
                return
            original_write_value(path, value)

        HELPER.write_value = ignore_inhibit_charge
        try:
            with self.assertRaisesRegex(HELPER.ChargeSentinelError, 'did not accept'):
                HELPER.set_behaviour('BAT0', 'inhibit-charge')
        finally:
            HELPER.write_value = original_write_value

        self.assertEqual((self.battery / 'charge_behaviour').read_text(encoding='utf-8'), 'auto\n')

    def test_restores_the_previous_behaviour_when_readback_is_unavailable(self):
        original_read_text = HELPER.read_text
        behaviour_reads = 0

        def fail_after_initial_behaviour_read(path):
            nonlocal behaviour_reads
            if path.name == 'charge_behaviour':
                behaviour_reads += 1
                if behaviour_reads == 2:
                    raise OSError('controller unavailable')
            return original_read_text(path)

        HELPER.read_text = fail_after_initial_behaviour_read
        try:
            with self.assertRaisesRegex(HELPER.ChargeSentinelError, 'previous behaviour was restored'):
                HELPER.set_behaviour('BAT0', 'inhibit-charge')
        finally:
            HELPER.read_text = original_read_text

        self.assertEqual((self.battery / 'charge_behaviour').read_text(encoding='utf-8'), 'auto\n')

    def test_status_skips_an_attribute_that_disappears_during_a_scan(self):
        original_read_text = HELPER.read_text

        def unavailable_capacity(path):
            if path.name == 'capacity':
                raise OSError('battery removed')
            return original_read_text(path)

        HELPER.read_text = unavailable_capacity
        try:
            result = HELPER.status()
        finally:
            HELPER.read_text = original_read_text

        self.assertTrue(result['supported'])
        self.assertNotIn('capacity', result['batteries'][0])

    def test_status_is_json_serializable(self):
        json.dumps(HELPER.status())

    def test_status_command_prints_a_machine_readable_snapshot(self):
        output = io.StringIO()
        with patch.object(sys, 'argv', ['charge-sentinel-helper', 'status']), redirect_stdout(output):
            self.assertEqual(HELPER.main(), 0)

        payload = json.loads(output.getvalue())
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['batteries'][0]['name'], 'BAT0')

    def test_invalid_command_values_return_a_nonzero_status(self):
        error = io.StringIO()
        arguments = ['charge-sentinel-helper', 'set-thresholds', 'BAT0', '90', '80']
        with patch.object(sys, 'argv', arguments), redirect_stderr(error):
            self.assertEqual(HELPER.main(), 1)

        self.assertIn('Start threshold must be lower', error.getvalue())
