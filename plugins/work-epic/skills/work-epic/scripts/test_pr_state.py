"""Decision-table tests for pr_state.plan_pr and the merge queue.

Run with `python3 -m unittest discover plugins/work-epic/skills/work-epic/scripts`
— stdlib only, no network: plan_pr and queue_merges are pure over gh/hew JSON.
"""

import unittest

from pr_state import (
    BLOCK_ON_NUM,
    RECONCILE_FAIL_MARKER,
    REVIEW_MARKER,
    check_rollup_state,
    parse_args,
    plan_pr,
    queue_merges,
    queue_reconciles,
)

HEAD = "9f2c" + "0" * 36
OLD = "40ba" + "0" * 36
GREEN = [{"status": "COMPLETED", "conclusion": "SUCCESS"}]
PENDING = [{"status": "IN_PROGRESS", "conclusion": ""}]
FAILING = [{"status": "COMPLETED", "conclusion": "FAILURE"}]


def round_comment(head=HEAD):
    return {"body": f"{REVIEW_MARKER}:\n\nclean\n\nreviewed-head: {head}"}


def fail_comment(reason="conflict in pkg/a.go"):
    return {"body": f"{RECONCILE_FAIL_MARKER}:\n\n{reason}"}


def pr(draft=False, merge_state="CLEAN", mergeable="MERGEABLE", rollup=GREEN,
       comments=None, head=HEAD, behind=0, number=34):
    return {
        "number": number,
        "headRefName": "fix/21-child",
        "headRefOid": head,
        "isDraft": draft,
        "mergeStateStatus": merge_state,
        "mergeable": mergeable,
        "statusCheckRollup": rollup,
        "comments": [round_comment()] if comments is None else comments,
        "behindBy": behind,
    }


def action(p, findings=(), block_on="P1", review=True, allow_no_checks=False,
           issue_state="open", reconcile=False):
    return plan_pr(p, 21, issue_state, list(findings), BLOCK_ON_NUM[block_on],
                   review, allow_no_checks, reconcile)["action"]


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
        p = pr(merge_state="BEHIND", comments=[round_comment(OLD)])
        self.assertEqual(action(p), "update_branch")


class ReconcileConflicts(unittest.TestCase):
    def test_flag_turns_a_conflict_into_reconcile(self):
        self.assertEqual(action(pr(merge_state="DIRTY"), reconcile=True),
                         "reconcile")

    def test_without_the_flag_a_conflict_is_reported(self):
        self.assertEqual(action(pr(merge_state="DIRTY")), "conflict")

    def test_open_blocker_suppresses_the_reconciler(self):
        # the human gate owns a held PR; the conflict is still reported
        self.assertEqual(
            action(pr(merge_state="DIRTY"), [{"priority": "P1"}],
                   reconcile=True),
            "conflict",
        )

    def test_one_failed_attempt_still_reconciles(self):
        p = pr(merge_state="DIRTY", comments=[fail_comment()])
        self.assertEqual(action(p, reconcile=True), "reconcile")

    def test_two_failed_attempts_park_it(self):
        p = pr(merge_state="DIRTY", comments=[fail_comment(), fail_comment()])
        self.assertEqual(action(p, reconcile=True), "conflict")

    def test_failures_are_reported(self):
        planned = plan_pr(pr(merge_state="DIRTY", comments=[fail_comment()]),
                          21, "open", [], 1, True, reconcile=True)
        self.assertEqual(planned["reconcileFailures"], 1)

    def test_no_review_ignores_findings_for_reconciliation(self):
        # --no-review makes CI the only gate; findings hold nothing
        self.assertEqual(
            action(pr(merge_state="DIRTY"), [{"priority": "P1"}],
                   review=False, reconcile=True),
            "reconcile",
        )


class ReconcileQueue(unittest.TestCase):
    def reconciled(self, number, **kw):
        planned = plan_pr(pr(number=number, merge_state="DIRTY", **kw), 21,
                          "open", [], 1, True, reconcile=True)
        self.assertEqual(planned["action"], "reconcile")
        return planned

    def test_one_reconciler_at_a_time(self):
        head = queue_reconciles([self.reconciled(35), self.reconciled(34)], None)
        self.assertEqual(head, 34)

    def test_siblings_queue_behind_the_reconciliation_head(self):
        prs = [self.reconciled(34), self.reconciled(35)]
        queue_reconciles(prs, None)
        self.assertEqual([(p["number"], p["action"]) for p in prs],
                         [(34, "reconcile"), (35, "queued")])

    def test_no_reconciliation_while_main_is_moving(self):
        # a merge landing mid-reconciliation would re-conflict it
        prs = [self.reconciled(34)]
        self.assertIsNone(queue_reconciles(prs, 99))
        self.assertEqual(prs[0]["action"], "queued")

    def test_conflicts_without_the_flag_are_not_touched(self):
        p = plan_pr(pr(merge_state="DIRTY"), 21, "open", [], 1, True)
        self.assertIsNone(queue_reconciles([p], None))
        self.assertEqual(p["action"], "conflict")


class Freshness(unittest.TestCase):
    def test_behind_without_strict_protection_is_updated_not_merged(self):
        # without "require up to date" GitHub reports a stale PR as CLEAN
        self.assertEqual(action(pr(merge_state="CLEAN", behind=3)), "update_branch")

    def test_behind_draft_is_readied_not_updated(self):
        # a draft is not next to merge, and moving its head spends a review round
        p = pr(draft=True, merge_state="DRAFT", behind=3)
        self.assertEqual(action(p), "mark_ready")

    def test_unknown_behind_count_never_merges(self):
        self.assertEqual(action(pr(behind=None)), "wait")

    def test_current_pr_with_running_ci_is_in_flight(self):
        planned = plan_pr(pr(rollup=PENDING), 21, "open", [], 1, True)
        self.assertEqual((planned["action"], planned.get("inFlight")), ("wait", True))

    def test_failing_pr_is_not_in_flight(self):
        planned = plan_pr(pr(rollup=FAILING), 21, "open", [], 1, True)
        self.assertIsNone(planned.get("inFlight"))


def planned(number, **kw):
    return plan_pr(pr(number=number, **kw), 21, "open", [], 1, True)


class Queue(unittest.TestCase):
    def actions(self, prs):
        head = queue_merges(prs)
        return head, {p["number"]: p["action"] for p in prs}

    def test_one_merge_per_plan(self):
        # merging both lands the second on CI that never saw the first
        got = self.actions([planned(35), planned(34)])
        self.assertEqual(got, (34, {34: "merge", 35: "queued"}))

    def test_merge_queues_every_update(self):
        got = self.actions([planned(34, behind=1), planned(35)])
        self.assertEqual(got, (35, {34: "queued", 35: "merge"}))

    def test_running_ci_holds_the_queue(self):
        got = self.actions([planned(34, rollup=PENDING), planned(35, behind=2)])
        self.assertEqual(got, (34, {34: "wait", 35: "queued"}))

    def test_failing_pr_does_not_hold_the_queue(self):
        got = self.actions([planned(34, rollup=FAILING), planned(35, behind=2)])
        self.assertEqual(got, (35, {34: "wait", 35: "update_branch"}))

    def test_update_prefers_passing_checks_then_oldest(self):
        got = self.actions([planned(34, behind=1, rollup=FAILING),
                            planned(36, behind=1), planned(35, behind=1)])
        self.assertEqual(got, (35, {34: "queued", 35: "update_branch", 36: "queued"}))

    def test_held_and_draft_prs_are_outside_the_queue(self):
        held = plan_pr(pr(number=34, behind=1), 21, "open", [{"priority": "P1"}], 1, True)
        got = self.actions([held, planned(35, draft=True, merge_state="DRAFT"),
                            planned(36, behind=1)])
        self.assertEqual(got, (36, {34: "hold", 35: "mark_ready", 36: "update_branch"}))

    def test_nothing_moving(self):
        self.assertEqual(self.actions([planned(34, rollup=FAILING)]), (None, {34: "wait"}))


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
                         ("12", None, "none", False, False, False))

    def test_flags_before_epic_number(self):
        self.assertEqual(parse_args(["--allow-no-checks", "--repo", "o/r", "12"]),
                         ("12", "o/r", "P1", True, True, False))

    def test_resolve_conflicts_flag(self):
        self.assertEqual(parse_args(["12", "--resolve-conflicts"]),
                         ("12", None, "P1", True, False, True))


class NoReview(unittest.TestCase):
    def test_findings_ignored(self):
        p = pr(comments=[])
        self.assertEqual(action(p, [{"priority": "P1"}], review=False), "merge")


if __name__ == "__main__":
    unittest.main()
