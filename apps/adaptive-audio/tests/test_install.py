import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from install_local import install


class AppInstallTests(unittest.TestCase):
    def test_installs_user_owned_app_and_refuses_conflict(self):
        project = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            result = install(project, home)
            binary = home / ".local/bin/adaptive-audio"
            self.assertTrue(binary.is_file())
            self.assertTrue(binary.stat().st_mode & 0o111)
            self.assertIn("adaptive-audio", result["binary"])
            self.assertTrue((home / ".local/share/applications/adaptive-audio.desktop").is_file())
            with self.assertRaises(FileExistsError):
                install(project, home)
            self.assertEqual(binary.read_bytes(), (project / "build/app/adaptive-audio").read_bytes())

    def test_conflicting_binary_is_not_overwritten(self):
        project = pathlib.Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            binary = home / ".local/bin/adaptive-audio"
            binary.parent.mkdir(parents=True)
            binary.write_text("existing")
            with self.assertRaises(FileExistsError):
                install(project, home)
            self.assertEqual(binary.read_text(), "existing")
            self.assertFalse((home / ".local/share/applications/adaptive-audio.desktop").exists())


if __name__ == "__main__":
    unittest.main()
