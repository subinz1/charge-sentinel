import unittest
import xml.etree.ElementTree as element_tree
from pathlib import Path


SCHEMA_PATH = (
    Path(__file__).parents[1]
    / 'schemas'
    / 'org.gnome.shell.extensions.charge-sentinel.gschema.xml'
)


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


if __name__ == '__main__':
    unittest.main()
