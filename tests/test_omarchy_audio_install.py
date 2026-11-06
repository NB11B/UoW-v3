import json
import pathlib
import tempfile
import unittest

from integrations.omarchy_uow.install_audio_plugin import install, uninstall, upgrade, rollback_upgrade


class InstallTests(unittest.TestCase):
    def test_upgrade_preserves_state_and_installs_current_code(self):
        repo = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            install(repo, home)
            state = home / ".local/state/omarchy-uow-audio"
            (state / "uow.db").write_text("existing receipts")
            (state / "enabled.json").write_text('{"enabled":false}')
            original_tokens = (state / "tokens.json").read_bytes()
            panel = home / ".config/omarchy/plugins/nb11b.adaptive-audio/Panel.qml"
            panel.write_text("old panel\n")
            manifest = state / "installed-files.json"
            inventory = json.loads(manifest.read_text())
            import hashlib
            inventory[str(panel)] = hashlib.sha256(panel.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(inventory))
            (state / "policy.json").write_text(json.dumps({"operator": ["audio.stream.start", "audio.stream.stop"], "audio_worker": ["audio.effect.record", "audio.telemetry.ingest"]}))
            upgrade(repo, home)
            self.assertEqual(panel.read_bytes(), (repo / "integrations/omarchy_uow/plugin/Panel.qml").read_bytes())
            self.assertEqual((state / "uow.db").read_text(), "existing receipts")
            self.assertEqual((state / "enabled.json").read_text(), '{"enabled":false}')
            self.assertEqual((state / "tokens.json").read_bytes(), original_tokens)
            self.assertIn("audio.dsp.crossover.set", json.loads((state / "policy.json").read_text())["operator"])

    def test_upgrade_refuses_changed_file_and_rolls_back_failure(self):
        repo = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            install(repo, home)
            panel = home / ".config/omarchy/plugins/nb11b.adaptive-audio/Panel.qml"
            panel.write_text(panel.read_text() + "\n// customized\n")
            with self.assertRaises(ValueError):
                upgrade(repo, home)
            self.assertIn("customized", panel.read_text())
            panel.write_bytes((repo / "integrations/omarchy_uow/plugin/Panel.qml").read_bytes())
            old_manifest = (home / ".local/state/omarchy-uow-audio/installed-files.json").read_bytes()
            calls = [0]
            def fail_after_one(source, destination):
                import os
                calls[0] += 1
                if calls[0] == 2:
                    raise OSError("injected failure")
                os.replace(source, destination)
            with self.assertRaises(OSError):
                upgrade(repo, home, replace=fail_after_one)
            self.assertEqual((home / ".local/state/omarchy-uow-audio/installed-files.json").read_bytes(), old_manifest)
            self.assertEqual(panel.read_bytes(), (repo / "integrations/omarchy_uow/plugin/Panel.qml").read_bytes())

    def test_successful_upgrade_can_be_rolled_back_without_touching_receipts(self):
        repo = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            install(repo, home)
            state = home / ".local/state/omarchy-uow-audio"
            (state / "uow.db").write_text("kept receipts")
            panel = home / ".config/omarchy/plugins/nb11b.adaptive-audio/Panel.qml"
            panel.write_text("prior panel\n")
            manifest = state / "installed-files.json"
            original_inventory = json.loads(manifest.read_text())
            import hashlib
            original_inventory[str(panel)] = hashlib.sha256(panel.read_bytes()).hexdigest()
            manifest.write_text(json.dumps(original_inventory))
            prior_manifest = manifest.read_bytes()
            result = upgrade(repo, home)
            rollback_upgrade(pathlib.Path(result["backup"]), home)
            self.assertEqual(panel.read_text(), "prior panel\n")
            self.assertEqual(manifest.read_bytes(), prior_manifest)
            self.assertEqual((state / "uow.db").read_text(), "kept receipts")

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
