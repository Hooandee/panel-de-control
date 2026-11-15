import hashlib
import json
import pathlib
import unittest

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / 'themes' / 'terciopelo'


class ThemePackageTests(unittest.TestCase):
    def test_original_resources_match_inventory(self):
        manifest = json.loads((PACKAGE / 'theme.json').read_text())
        for asset in manifest['assets']:
            path = PACKAGE / asset['path']
            self.assertTrue(path.resolve().is_relative_to(PACKAGE.resolve()))
            data = path.read_bytes()
            self.assertEqual(asset['bytes'], len(data), asset['path'])
            self.assertEqual(asset['sha256'], hashlib.sha256(data).hexdigest(), asset['path'])
        files = {item['path'] for item in manifest['assets']}
        self.assertTrue(set(manifest['keyFaces']['states'].values()).issubset(files))

    def test_unobserved_keyboard_bindings_cannot_enable_application(self):
        manifest = json.loads((PACKAGE / 'theme.json').read_text())
        self.assertFalse(manifest['applicationEnabled'])
        self.assertEqual([], manifest['bindings'])
        self.assertIn('keyboard_elements_unverified', manifest['blockedBy'])


if __name__ == '__main__':
    unittest.main()
