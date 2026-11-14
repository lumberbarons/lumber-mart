"""Discovery tests for work_epic.find_skill_dir.

Run with `python3 -m unittest discover tests/work-epic/work-epic`
— stdlib only, no network: the search order is pure over the filesystem, with
Path.home redirected into a temporary directory.
"""

import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "plugins/work-epic/skills/work-epic/scripts"
sys.path.insert(0, str(SCRIPTS))

import work_epic

NAME = "demo-skill"
ENV = "WORK_EPIC_DEMO_DIR"


def skill(root, *parts):
    """Create <root>/<parts>/<NAME>/SKILL.md and return the skill directory."""
    d = Path(root).joinpath(*parts, NAME)
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("---\nname: demo-skill\n---\n")
    return d


class FindSkillDir(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()

        env = patch.dict(os.environ)
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop(ENV, None)

        home = patch.object(Path, "home", return_value=self.home)
        home.start()
        self.addCleanup(home.stop)

    def find(self, *roots):
        return work_epic.find_skill_dir(NAME, ENV, roots)

    def test_env_override_wins_even_without_a_skill_md(self):
        override = self.tmp / "override"
        override.mkdir()
        os.environ[ENV] = str(override)
        repo = self.tmp / "repo"
        skill(repo, ".agents", "skills")
        self.assertEqual(self.find(repo), str(override))

    def test_repo_agents_layout_is_found(self):
        repo = self.tmp / "repo"
        expected = skill(repo, ".agents", "skills")
        self.assertEqual(self.find(repo), str(expected))

    def test_repo_claude_layout_is_found(self):
        repo = self.tmp / "repo"
        expected = skill(repo, ".claude", "skills")
        self.assertEqual(self.find(repo), str(expected))

    def test_agents_layout_beats_claude_in_the_same_root(self):
        repo = self.tmp / "repo"
        expected = skill(repo, ".agents", "skills")
        skill(repo, ".claude", "skills")
        self.assertEqual(self.find(repo), str(expected))

    def test_first_repo_root_wins(self):
        worktree, main = self.tmp / "worktree", self.tmp / "main"
        expected = skill(worktree, ".agents", "skills")
        skill(main, ".agents", "skills")
        self.assertEqual(self.find(worktree, main), str(expected))

    def test_repo_local_beats_user_skills(self):
        repo = self.tmp / "repo"
        expected = skill(repo, ".agents", "skills")
        skill(self.home, ".agents", "skills")
        self.assertEqual(self.find(repo), str(expected))

    def test_user_skill_is_the_fallback(self):
        expected = skill(self.home, ".agents", "skills")
        self.assertEqual(self.find(self.tmp / "empty"), str(expected))

    def test_a_directory_without_skill_md_falls_through(self):
        repo = self.tmp / "repo"
        (repo / ".agents" / "skills" / NAME).mkdir(parents=True)
        expected = skill(self.home, ".agents", "skills")
        self.assertEqual(self.find(repo), str(expected))

    def test_not_found_names_the_override(self):
        err = io.StringIO()
        with redirect_stderr(err), self.assertRaises(SystemExit) as raised:
            self.find(self.tmp / "empty")
        self.assertEqual(raised.exception.code, 1)
        self.assertIn(ENV, err.getvalue())
