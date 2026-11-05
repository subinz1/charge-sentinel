import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_DIRECTORY = Path(__file__).parents[1] / 'src'
sys.path.insert(0, str(SOURCE_DIRECTORY))

from charge_sentinel_capabilities import (  # noqa: E402
    detect_chromeos,
    detect_linux,
    detect_macos,
    detect_windows,
)


class ChargeCapabilitiesTests(unittest.TestCase):
    def test_linux_detects_standard_threshold_files(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            battery = root / 'BAT0'
            battery.mkdir()
            (battery / 'type').write_text('Battery\n', encoding='utf-8')
            (battery / 'charge_control_start_threshold').write_text('20\n', encoding='utf-8')
            (battery / 'charge_control_end_threshold').write_text('95\n', encoding='utf-8')
            (battery / 'charge_behaviour').write_text('[auto] inhibit-charge\n', encoding='utf-8')

            capability = detect_linux(root, root / 'no-thinkpad-module')

        self.assertEqual(capability.state, 'supported')
        self.assertEqual(capability.start_range.to_list(), [0, 99])
        self.assertIn('pause-charging', capability.actions)

    def test_dell_windows_adapter_validates_its_own_range(self):
        capability = detect_windows('Dell Inc.', r'C:\\Program Files\\Dell\\cctk.exe')
        self.assertEqual(capability.state, 'supported')
        self.assertEqual(capability.start_range.to_list(), [50, 95])
        self.assertEqual(capability.minimum_gap, 5)

    def test_windows_lenovo_requires_a_dedicated_automation_adapter(self):
        capability = detect_windows('LENOVO')
        self.assertEqual(capability.state, 'requires-vendor-adapter')
        self.assertIsNone(capability.start_range)

    def test_apple_silicon_macos_uses_native_stop_only_limit(self):
        capability = detect_macos('26.4', 'arm64')
        self.assertEqual(capability.state, 'native-only')
        self.assertIsNone(capability.start_range)
        self.assertEqual(capability.end_range.to_list(), [80, 100])

    def test_chromeos_uses_native_eighty_percent_limit(self):
        capability = detect_chromeos()
        self.assertEqual(capability.state, 'native-only')
        self.assertEqual(capability.end_range.to_list(), [80, 80])
