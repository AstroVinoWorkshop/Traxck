from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'frontend' / 'src'


class PlugSetupUiTest(unittest.TestCase):
    def test_setup_navigation_contains_plug_settings(self):
        main = (ROOT / 'main.tsx').read_text()
        self.assertIn("['connection','Setup'", main)
        self.assertIn('<RailwayPlugSetup/>', main)

    def test_setup_never_sends_switch_command(self):
        setup = (ROOT / 'RailwayPlugSetup.tsx').read_text()
        self.assertIn("/api/railway-plug/config", setup)
        self.assertNotIn("fetch('/api/railway-plug'", setup)

    def test_mains_control_uses_inline_confirmation_not_browser_dialog(self):
        plug = (ROOT / 'RailwayPlug.tsx').read_text()
        self.assertNotIn('window.confirm', plug)
        self.assertIn('railway-plug-confirm', plug)
        self.assertIn('pending===null||!plug?.available||busy', plug)
        self.assertIn('This energises DCC-EX and other railway equipment', plug)
        self.assertIn('Confirm turn off', plug)


if __name__ == '__main__':
    unittest.main()
