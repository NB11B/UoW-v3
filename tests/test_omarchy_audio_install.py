import json
import pathlib
import tempfile
import unittest

from integrations.omarchy_uow.install_audio_plugin import install, uninstall


class InstallTests(unittest.TestCase):
    def test_local_install_refuses_conflicts_and_keeps_tokens_private(self):
        repo = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            installed = install(repo, home)
            plugin = home / ".config/omarchy/plugins/nb11b.adaptive-audio"
            self.assertEqual(json.loads((plugin / "manifest.json").read_text())["entryPoints"]["barWidget"], "BarWidget.qml")
            self.assertTrue((plugin / "Panel.qml").exists())
            self.assertEqual((home / ".local/state/omarchy-uow-audio/tokens.json").stat().st_mode & 0o077, 0)
            self.assertIn("gateway", installed)
            with self.assertRaises(FileExistsError):
                install(repo, home)

    def test_uninstall_refuses_edits_and_preserves_receipts(self):
        repo = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            install(repo, home)
            plugin = home / ".config/omarchy/plugins/nb11b.adaptive-audio"
            panel = plugin / "Panel.qml"
            original = panel.read_text()
            panel.write_text(original + "\n// local edit\n")
            with self.assertRaises(ValueError):
                uninstall(home, stop=lambda: None)
            self.assertTrue(panel.exists())
            panel.write_text(original)
            state = home / ".local/state/omarchy-uow-audio"
            (state / "uow.db").write_text("receipt-placeholder")
            uninstall(home, stop=lambda: None)
            self.assertFalse(plugin.exists())
            self.assertFalse((home / ".local/bin/omarchy-audio-worker").exists())
            self.assertEqual((state / "uow.db").read_text(), "receipt-placeholder")


if __name__ == "__main__":
    unittest.main()
