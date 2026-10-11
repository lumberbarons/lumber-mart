"""Protect APM layout eligibility and read-only generated-file checks."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "sync_apm", Path(__file__).with_name("sync-apm-manifests.py")
)
sync_apm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync_apm)


class ApmGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.plugin = self.root / "plugins/example"
        self.plugin.mkdir(parents=True)
        self.manifest = {"name": "example", "version": "1.0.0", "description": "Example",
                         "author": {"name": "Example"}, "license": "MIT"}
        self.source = self.plugin / "plugin.json"
        self.source.write_text(json.dumps(self.manifest))
        sync_apm.sync(self.root, check=False)

    def test_missing_layout_marker_fails_check_without_recreating_it(self):
        marker = self.plugin / ".apm/README.md"
        marker.unlink()
        marker.parent.rmdir()
        self.assertEqual(sync_apm.sync(self.root, check=True),
                         ["out of sync: plugins/example/.apm/README.md"])
        self.assertFalse(marker.parent.exists())

    def test_metadata_drift_is_read_only_and_can_be_regenerated(self):
        generated = self.plugin / "apm.yml"
        previous = generated.read_bytes()
        self.manifest["version"] = "1.1.0"
        self.source.write_text(json.dumps(self.manifest))
        self.assertEqual(sync_apm.sync(self.root, check=True),
                         ["out of sync: plugins/example/apm.yml"])
        self.assertEqual(generated.read_bytes(), previous)
        sync_apm.sync(self.root, check=False)
        self.assertEqual(sync_apm.sync(self.root, check=True), [])
        self.assertIn('version: "1.1.0"', generated.read_text())


if __name__ == "__main__":
    unittest.main()
