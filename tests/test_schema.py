import unittest
import xml.etree.ElementTree as element_tree
from pathlib import Path


SCHEMA_PATH = (
    Path(__file__).parents[1]
    / 'schemas'
    / 'org.gnome.shell.extensions.charge-sentinel.gschema.xml'
)
EXTENSION_PATH = Path(__file__).parents[1] / 'extension.js'
INSTALLER_PATH = Path(__file__).parents[1] / 'install.sh'
RELEASE_WORKFLOW_PATH = Path(__file__).parents[1] / '.github' / 'workflows' / 'fedora-rpm.yml'


class ChargeSentinelSchemaTests(unittest.TestCase):
    def test_custom_threshold_ranges_match_the_helper_contract(self):
        schema = element_tree.parse(SCHEMA_PATH).getroot()
        ranges = {
            key.attrib['name']: key.find('range').attrib
            for key in schema.findall('.//key')
            if key.find('range') is not None
        }

        self.assertEqual(ranges['custom-start'], {'min': '0', 'max': '99'})
        self.assertEqual(ranges['custom-end'], {'min': '1', 'max': '100'})

    def test_selected_battery_setting_defaults_to_automatic_selection(self):
        schema = element_tree.parse(SCHEMA_PATH).getroot()
        selected_battery = schema.find(".//key[@name='selected-battery']")

        self.assertIsNotNone(selected_battery)
        self.assertEqual(selected_battery.attrib['type'], 's')
        self.assertEqual(selected_battery.findtext('default'), "''")

    def test_multi_battery_menu_keeps_an_automatic_selection_option(self):
        extension = EXTENSION_PATH.read_text(encoding='utf-8')

        self.assertIn('Automatic (${this._state.name})', extension)
        self.assertIn("set_string('selected-battery', '')", extension)

    def test_extension_marks_the_active_charge_profile(self):
        extension = EXTENSION_PATH.read_text(encoding='utf-8')

        self.assertIn('_syncProfileSelection()', extension)
        self.assertIn('Apply custom limits (${customStart}% → ${customEnd}%)', extension)

    def test_extension_disables_an_invalid_custom_charge_range(self):
        extension = EXTENSION_PATH.read_text(encoding='utf-8')

        self.assertIn('const customValid = customStart < customEnd;', extension)
        self.assertIn('Custom limits need a lower start value', extension)

    def test_extension_has_a_manual_battery_status_refresh(self):
        extension = EXTENSION_PATH.read_text(encoding='utf-8')

        self.assertIn("addAction('Refresh battery status', () => this._refresh())", extension)
        self.assertIn('this._syncBatteryMenu([]);', extension)

    def test_extension_preserves_helper_diagnostics_for_failed_changes(self):
        extension = EXTENSION_PATH.read_text(encoding='utf-8')

        self.assertIn('Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE', extension)
        self.assertIn('communicate_utf8_async', extension)
        self.assertIn('Could not apply change:', extension)

    def test_extension_ignores_helper_callbacks_after_it_is_destroyed(self):
        extension = EXTENSION_PATH.read_text(encoding='utf-8')

        self.assertIn('this._destroyed = false;', extension)
        self.assertIn('if (this._destroyed)', extension)
        self.assertIn('this._destroyed = true;', extension)

    def test_extension_does_not_start_overlapping_privileged_changes(self):
        extension = EXTENSION_PATH.read_text(encoding='utf-8')

        self.assertIn('this._helperRunning = false;', extension)
        self.assertIn('if (this._helperRunning)', extension)
        self.assertIn('A charge change is already in progress.', extension)

    def test_local_installer_does_not_overwrite_an_rpm_installation(self):
        installer = INSTALLER_PATH.read_text(encoding='utf-8')

        self.assertIn('rpm -q charge-sentinel', installer)
        self.assertIn('Update it with dnf instead of the local installer.', installer)

    def test_release_workflow_validates_main_and_checks_extension_syntax(self):
        workflow = RELEASE_WORKFLOW_PATH.read_text(encoding='utf-8')
        makefile = (Path(__file__).parents[1] / 'Makefile').read_text(encoding='utf-8')

        self.assertIn('branches:\n      - main', workflow)
        self.assertIn('nodejs', workflow)
        self.assertIn('node --check extension.js', makefile)
        self.assertIn('node --check prefs.js', makefile)


if __name__ == '__main__':
    unittest.main()
