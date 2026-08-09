import importlib.util
import json
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "update_payloads.py"
spec = importlib.util.spec_from_file_location("update_payloads", MODULE_PATH)
updater = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(updater)


class UpdaterTests(unittest.TestCase):
    def test_exact_asset_wins(self):
        source = {
            "exact_assets": ["CheatRunner.elf"],
            "allowed_extensions": [".elf", ".bin", ".lua"],
        }
        release = {"assets": [
            {"name": "other.elf"},
            {"name": "CheatRunner.elf"},
        ]}
        self.assertEqual(updater.choose_asset(release, source)["name"], "CheatRunner.elf")

    def test_pkg_is_not_pldmgr_payload(self):
        source = {"allowed_extensions": [".elf", ".bin", ".lua"]}
        release = {"assets": [{"name": "InternetBrowser-PS5.pkg"}]}
        self.assertIsNone(updater.choose_asset(release, source))

    def test_single_compatible_asset_is_accepted(self):
        source = {"allowed_extensions": [".elf", ".bin", ".lua"]}
        release = {"assets": [{"name": "future-browser.elf"}, {"name": "readme.txt"}]}
        self.assertEqual(updater.choose_asset(release, source)["name"], "future-browser.elf")

    def test_digest_normalization(self):
        h = "a" * 64
        self.assertEqual(updater.normalize_digest("sha256:" + h), h)
        self.assertIsNone(updater.normalize_digest("md5:" + h))

    def test_catalog_name_precedes_payloads(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / "payloads.json").read_text(encoding="utf-8")
        self.assertLess(text.index('"name"'), text.index('"payloads"'))
        data = json.loads(text)
        self.assertIsInstance(data["payloads"], list)


if __name__ == "__main__":
    unittest.main()
