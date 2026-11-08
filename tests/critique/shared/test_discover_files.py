"""discover-files.sh must list a repository path whatever directory the caller runs from."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "plugins/critique/scripts"
SCRIPT = SCRIPTS / "discover-files.sh"

class DiscoverFilesPathTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name).resolve()
        self.repo = base / "repo"
        (self.repo / "pkg").mkdir(parents=True)
        (self.repo / "pkg" / "a.py").write_text("a = 1\n")
        (self.repo / "pkg" / "b.py").write_text("b = 2\n")
        self.outside = base / "outside"
        self.outside.mkdir()
        self.env = dict(os.environ, GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        for key in tuple(self.env):
            if key.startswith(("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")):
                del self.env[key]
        self.git("init", "-q", "-b", "main")
        self.git("add", ".")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=self.repo, env=self.env, check=True,
                       capture_output=True, text=True)

    def discover(self, path, cwd):
        return subprocess.run(["bash", str(SCRIPT), str(path)], cwd=cwd, env=self.env,
                              capture_output=True, text=True, check=False)

    def test_absolute_path_from_a_directory_outside_any_repository(self):
        result = self.discover(self.repo / "pkg", self.outside)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(result.stdout.split()),
                         [str(self.repo / "pkg" / "a.py"), str(self.repo / "pkg" / "b.py")])

    def test_path_from_inside_the_repository_is_unchanged(self):
        result = self.discover("pkg", self.repo)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sorted(result.stdout.split()), ["pkg/a.py", "pkg/b.py"])


if __name__ == "__main__":
    unittest.main()
