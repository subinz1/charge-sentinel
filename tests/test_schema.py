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


if __name__ == '__main__':
    unittest.main()
