"""Decision-table tests for pr_state.plan_pr.

Run with `python3 -m unittest discover plugins/work-epic/skills/work-epic/scripts`
— stdlib only, no network: plan_pr is pure over gh/hew JSON.
"""

import unittest

from pr_state import BLOCK_ON_NUM, REVIEW_MARKER, check_rollup_state, parse_args, plan_pr

HEAD = "9f2c" + "0" * 36
OLD = "40ba" + "0" * 36
GREEN = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]


def round_comment(head=HEAD):
    return {"body": f"{REVIEW_MARKER}:\n\nclean\n\nreviewed-head: {head}"}


def pr(draft=False, merge_state="CLEAN", mergeable="MERGEABLE", rollup=GREEN,
       comments=None, head=HEAD):
    return {
        "number": 34,
        "headRefName": "fix/21-child",
        "headRefOid": head,
        "isDraft": draft,
        "mergeStateStatus": merge_state,
        "mergeable": mergeable,
        "statusCheckRollup": rollup,
        "comments": [round_comment()] if comments is None else comments,
    }


def action(p, findings=(), block_on="P1", review=True, allow_no_checks=False,
           issue_state="open"):
    return plan_pr(p, 21, issue_state, list(findings), BLOCK_ON_NUM[block_on],
                   review, allow_no_checks)["action"]


class BlockOn(unittest.TestCase):
    def test_none_blocks_no_severity(self):
        self.assertEqual(action(pr(), [{"priority": "P1"}], block_on="none"), "merge")

    def test_p1_holds_on_p1_only(self):
        self.assertEqual(action(pr(), [{"priority": "P1"}]), "hold")
        self.assertEqual(action(pr(), [{"priority": "P2"}]), "merge")

    def test_p2_holds_on_p2(self):
        self.assertEqual(action(pr(), [{"priority": "P2"}], block_on="P2"), "hold")


class ReviewRounds(unittest.TestCase):
    def test_no_round_waits(self):
        self.assertEqual(action(pr(draft=True, comments=[])), "wait")

    def test_readied_pr_without_round_still_waits(self):
        self.assertEqual(action(pr(comments=[])), "wait")

    def test_below_block_on_round_proceeds(self):
        # a P2-only review under --block-on P1 posts a round and moves on
        self.assertEqual(action(pr(draft=True), [{"priority": "P2"}]), "mark_ready")

    def test_unreadable_comments_wait(self):
        p = pr()
        p["comments"] = None
        self.assertEqual(action(p), "wait")

    def test_stale_draft_re_reviews(self):
        p = pr(draft=True, comments=[round_comment(OLD)])
        self.assertEqual(action(p), "re_review")

    def test_abbreviated_reviewed_head_is_current(self):
        p = pr(draft=True, comments=[round_comment(HEAD[:7])])
        self.assertEqual(action(p), "mark_ready")

    def test_two_rounds_with_blocker_escalate(self):
        p = pr(draft=True, comments=[round_comment(OLD), round_comment()])
        self.assertEqual(action(p, [{"priority": "P1"}]), "escalate")


class HoldOrdering(unittest.TestCase):
    def test_held_pr_is_not_branch_updated(self):
        # updating a held PR moves its head and burns a review round
        p = pr(draft=True, merge_state="BEHIND")
        self.assertEqual(action(p, [{"priority": "P1"}]), "hold")

    def test_conflict_reported_even_when_held(self):
        p = pr(draft=True, merge_state="DIRTY")
        self.assertEqual(action(p, [{"priority": "P1"}]), "conflict")

    def test_behind_updates_before_re_review(self):
        p = pr(draft=True, merge_state="BEHIND", comments=[round_comment(OLD)])
        self.assertEqual(action(p), "update_branch")


class Checks(unittest.TestCase):
    def test_no_checks_wait_by_default(self):
        self.assertEqual(action(pr(rollup=[])), "wait")

    def test_no_checks_merge_when_allowed(self):
        self.assertEqual(action(pr(rollup=[]), allow_no_checks=True), "merge")

    def test_failing_checks_wait(self):
        failing = [{"status": "COMPLETED", "conclusion": "FAILURE"}]
        self.assertEqual(action(pr(rollup=failing)), "wait")

    def test_rollup_collapse(self):
        self.assertEqual(check_rollup_state([]), "none")
        self.assertEqual(check_rollup_state([{"state": "PENDING"}] + GREEN), "pending")
        self.assertEqual(check_rollup_state([{"state": "ERROR"}] + GREEN), "fail")


class MergeState(unittest.TestCase):
    def test_draft_is_readied_not_merged(self):
        # GitHub reports DRAFT for a draft, masking BEHIND/BLOCKED
        self.assertEqual(action(pr(draft=True, merge_state="DRAFT"), review=False),
                         "mark_ready")

    def test_conflicting_draft_is_a_conflict(self):
        p = pr(draft=True, merge_state="DRAFT", mergeable="CONFLICTING")
        self.assertEqual(action(p, review=False), "conflict")

    def test_blocked_with_green_checks_is_protected(self):
        self.assertEqual(action(pr(merge_state="BLOCKED")), "protected")

    def test_unknown_waits(self):
        self.assertEqual(action(pr(merge_state="UNKNOWN")), "wait")

    def test_closed_issue_waits(self):
        self.assertEqual(action(pr(), issue_state="closed"), "wait")


class Args(unittest.TestCase):
    def test_flags_after_epic_number(self):
        # the skill's own invocation order
        self.assertEqual(parse_args(["12", "--block-on", "none", "--no-review"]),
                         ("12", None, "none", False, False))

    def test_flags_before_epic_number(self):
        self.assertEqual(parse_args(["--allow-no-checks", "--repo", "o/r", "12"]),
                         ("12", "o/r", "P1", True, True))


class NoReview(unittest.TestCase):
    def test_findings_ignored(self):
        p = pr(comments=[])
        self.assertEqual(action(p, [{"priority": "P1"}], review=False), "merge")


if __name__ == "__main__":
    unittest.main()
