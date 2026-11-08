"""Fix-mode output must not turn completed repairs into new tracker work."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CONVERTER = (Path(__file__).resolve().parents[2]
             / "hew/skills/raise-issues/scripts/findings_to_plan.py")


def finding(title):
    return {
        "priority": "P2", "pattern": "logic-error", "title": title,
        "files": ["src/app.py"], "locations": ["src/app.py:12"],
        "explanation": "The input takes the wrong branch.",
        "fix": "Correct the branch condition.", "done_when": "The input reaches the correct branch.",
    }


class RepairFindingsTests(unittest.TestCase):
    def convert(self, unresolved):
        repaired = dict(finding("Already repaired"), verification="Targeted regression passed")
        data = {"skill": "code", "status": "reviewed", "mode": "fix",
                "mode_reason": "clean development-branch change review",
                "findings": unresolved, "repaired": [repaired]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "findings.json"
            path.write_text(json.dumps(data))
            result = subprocess.run([sys.executable, str(CONVERTER), str(path)],
                                    text=True, capture_output=True, check=True)
        return [json.loads(line) for line in result.stdout.splitlines()]

    def test_only_unresolved_finding_becomes_an_issue_plan(self):
        plans = self.convert([finding("Needs a decision")])
        self.assertEqual([p["title"] for p in plans], ["Needs a decision"])

    def test_all_repaired_produces_no_issue_plan(self):
        self.assertEqual(self.convert([]), [])


if __name__ == "__main__":
    unittest.main()
