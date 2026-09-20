import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import doctor


class DoctorTests(unittest.TestCase):
    def test_core_does_not_probe_optional_dependencies(self):
        for system in ("Windows", "Darwin", "Linux"):
            with self.subTest(system=system), patch.object(doctor.platform, "system", return_value=system), patch.object(doctor.shutil, "which", side_effect=AssertionError("optional probe")):
                self.assertEqual("ok", doctor.inspect_environment()["status"])

    def test_old_python(self):
        with patch.object(doctor.sys, "version_info", (3, 9)):
            self.assertEqual("attention", doctor.inspect_environment()["status"])

    def test_missing_reader(self):
        with patch.object(doctor.importlib.util, "find_spec", return_value=None), patch.object(doctor.shutil, "which", return_value=None):
            self.assertEqual("attention", doctor.inspect_environment("pdf-source")["status"])

    def test_pdftotext_fallback(self):
        with patch.object(doctor.importlib.util, "find_spec", return_value=None), patch.object(doctor.shutil, "which", return_value="pdftotext"):
            self.assertEqual("ok", doctor.inspect_environment("pdf-source")["status"])

    def test_missing_node(self):
        with patch.object(doctor.shutil, "which", return_value=None):
            self.assertEqual("attention", doctor.inspect_environment("pdf-export")["status"])

    def test_browser_timeout(self):
        with patch.object(doctor.platform, "system", return_value="Windows"), patch.object(doctor.shutil, "which", return_value="node"), patch.object(doctor.subprocess, "run", side_effect=doctor.subprocess.TimeoutExpired("node", 60)):
            self.assertEqual("attention", doctor.inspect_environment("pdf-export")["status"])


if __name__ == "__main__":
    unittest.main()
