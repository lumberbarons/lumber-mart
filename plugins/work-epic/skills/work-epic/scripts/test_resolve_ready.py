"""Classification tests for resolve_ready.classify.

Run with `python3 -m unittest discover plugins/work-epic/skills/work-epic/scripts`
— stdlib only, no network: classify is pure over hew JSON plus the PR and
branch indexes.
"""

import json
import unittest
from unittest.mock import patch

from resolve_ready import (
    classify,
    count_by_reason,
    delivery_index,
    parse_args,
    resolve,
    spawn_budget,
)

ME = "orchestrator"


def child(n, **kw):
    c = {"number": n, "title": f"child {n}", "state": "open", "priority": "P2",
         "type": "task", "body": ""}
    c.update(kw)
    return c


def mine(n):
    return child(n, inProgress=True, assignees=[ME])


def finding(n, reviewed, **kw):
    """A raise-issues finding at generation 1 unless reviewed is a finding."""
    body = (
        "### Where\n\n`internal/store/store.go`\n\n"
        "review-key: code/leaky-abstraction/internal/store/store.go\n\n"
        f"review-of: #{reviewed}"
    )
    return child(n, body=body, **kw)


def reasons(children, prs=(), branches=(), resume=False, me=ME,
            finding_depth=1, bodies=None):
    pr_by_issue, branch_by_issue = delivery_index(list(prs), list(branches))
    eligible, skipped, _ = classify(
        children, me, pr_by_issue, branch_by_issue, resume,
        finding_depth=finding_depth, bodies=bodies,
    )
    out = {e["number"]: "eligible" for e in eligible}
    out.update({s["number"]: s["reason"] for s in skipped})
    return out


class OwnClaims(unittest.TestCase):
    def test_delivered_child_is_in_review(self):
        prs = [{"number": 34, "headRefName": "fix/21-child"}]
        self.assertEqual(reasons([mine(21)], prs=prs), {21: "in_review"})

    def test_open_pr_wins_over_other_claims(self):
        prs = [{"number": 34, "headRefName": "feat/21-child"}]
        c = child(21, inProgress=True, assignees=["someone"])
        self.assertEqual(reasons([c], prs=prs), {21: "in_review"})

    def test_failed_worker_is_stalled_even_with_resume(self):
        self.assertEqual(reasons([mine(21)], branches=["fix/21-child"], resume=True),
                         {21: "stalled"})

    def test_in_flight_claim_is_not_respawned(self):
        self.assertEqual(reasons([mine(21)]), {21: "claimed"})

    def test_resume_opts_bare_claim_back_in(self):
        pr_by_issue, branch_by_issue = delivery_index([], [])
        eligible, _, _ = classify([mine(21)], ME, pr_by_issue, branch_by_issue, True)
        self.assertEqual([(e["number"], e["resume"]) for e in eligible], [(21, True)])

    def test_unknown_user_treats_claims_as_foreign(self):
        self.assertEqual(reasons([mine(21)], resume=True, me=None), {21: "claimed"})


class Basics(unittest.TestCase):
    def test_unclaimed_ready_child_is_eligible(self):
        self.assertEqual(reasons([child(21)]), {21: "eligible"})

    def test_blocked_and_untriaged(self):
        got = reasons([child(21, openBlockers=[20]), child(22, untriaged=True)])
        self.assertEqual(got, {21: "blocked", 22: "untriaged"})

    def test_unrelated_branches_are_ignored(self):
        got = reasons([child(21)], branches=["main", "worktree-fix+x", "fix/210-other"])
        self.assertEqual(got, {21: "eligible"})

    def test_reviewed_issue_is_reported_on_eligible_findings(self):
        pr_by_issue, branch_by_issue = delivery_index([], [])
        eligible, _, _ = classify([child(20), finding(30, 20)], ME,
                                  pr_by_issue, branch_by_issue)
        by_number = {e["number"]: e for e in eligible}
        self.assertEqual(by_number[30]["reviewOf"], 20)
        self.assertIsNone(by_number[20]["reviewOf"])


class FindingDepth(unittest.TestCase):
    def test_generation_one_finding_is_eligible(self):
        got = reasons([child(20), finding(30, 20)])
        self.assertEqual(got, {20: "eligible", 30: "eligible"})

    def test_generation_two_finding_is_parked(self):
        got = reasons([child(20), finding(30, 20), finding(31, 30)])
        self.assertEqual(got[31], "finding_depth")

    def test_parked_detail_names_the_generation_and_target(self):
        pr_by_issue, branch_by_issue = delivery_index([], [])
        _, skipped, _ = classify([child(20), finding(30, 20), finding(31, 30)],
                                 ME, pr_by_issue, branch_by_issue)
        entry = next(s for s in skipped if s["number"] == 31)
        self.assertIn("generation 2", entry["detail"])
        self.assertIn("#30", entry["detail"])

    def test_flag_raises_the_bound(self):
        children = [child(20), finding(30, 20), finding(31, 30)]
        self.assertEqual(reasons(children, finding_depth=2)[31], "eligible")

    def test_generation_three_needs_depth_three(self):
        children = [child(20), finding(30, 20), finding(31, 30), finding(32, 31)]
        self.assertEqual(reasons(children, finding_depth=2)[32], "finding_depth")
        self.assertEqual(reasons(children, finding_depth=3)[32], "eligible")

    def test_a_finding_without_review_of_is_generation_one(self):
        body = "review-key: code/god-function/internal/http/a.go"
        self.assertEqual(reasons([child(30, body=body)]), {30: "eligible"})

    def test_a_reviewed_issue_we_cannot_read_is_treated_as_product_code(self):
        got = reasons([finding(30, 99)])
        self.assertEqual(got, {30: "eligible"})

    def test_counts_include_finding_depth(self):
        children = [child(20), finding(30, 20), finding(31, 30)]
        pr_by_issue, branch_by_issue = delivery_index([], [])
        eligible, skipped, closed = classify(children, ME, pr_by_issue, branch_by_issue)
        counts = count_by_reason(eligible, skipped, closed)
        self.assertEqual(counts["finding_depth"], 1)
        self.assertEqual(counts["eligible"], 2)
        self.assertEqual(set(counts), {
            "eligible", "blocked", "untriaged", "claimed", "in_review",
            "stalled", "finding_depth", "closed",
        })

    def test_flag_parses(self):
        self.assertEqual(parse_args(["12", "--finding-depth", "2"]),
                         ("12", None, False, None, 2))

    def test_flag_rejects_zero(self):
        with self.assertRaises(SystemExit) as raised:
            parse_args(["12", "--finding-depth", "0"])
        self.assertEqual(raised.exception.code, 2)


class FindingDepthResolution(unittest.TestCase):
    """resolve() wires the depth policy to the tracker reads."""

    def test_closed_reviewed_finding_is_fetched_and_parks_the_next_generation(self):
        open_child = finding(31, 30)
        closed_body = (
            "### Where\n\n`internal/store/store.go`\n\n"
            "review-key: code/leaky-abstraction/internal/store/store.go\n\n"
            "review-of: #20"
        )
        calls = []

        def fake_run(argv):
            calls.append(argv)
            if argv[:2] == ["hew", "show"] and str(argv[2]) == "12":
                return json.dumps({"epic": True, "title": "E"})
            if argv[:2] == ["hew", "list"]:
                return json.dumps(open_child) + "\n"
            if argv[:2] == ["hew", "show"] and str(argv[2]) == "30":
                return json.dumps({"body": closed_body})
            raise AssertionError(f"unexpected command {argv}")

        with patch("resolve_ready.run", side_effect=fake_run), \
             patch("resolve_ready.open_prs", return_value=[]), \
             patch("resolve_ready.remote_branches", return_value=[]), \
             patch("resolve_ready.main_checkout", return_value="/tmp/repo"), \
             patch("resolve_ready.default_branch", return_value="main"), \
             patch("resolve_ready.current_user", return_value=ME):
            out = resolve(12, None, False)

        self.assertEqual(out["counts"]["finding_depth"], 1)
        self.assertEqual(out["eligible"], [])
        self.assertIn("--state", next(c for c in calls if c[:2] == ["hew", "list"]))
        self.assertTrue(any(c[:3] == ["hew", "show", "30"] for c in calls))


def budget(children, prs=(), cap=4, resume=False):
    pr_by_issue, branch_by_issue = delivery_index(list(prs), [])
    _, skipped, _ = classify(children, ME, pr_by_issue, branch_by_issue, resume)
    return spawn_budget(skipped, cap)


class SpawnBudget(unittest.TestCase):
    def test_uncapped_without_flag(self):
        self.assertIsNone(budget([child(21)], cap=None))

    def test_open_prs_and_own_in_flight_claims_count(self):
        prs = [{"number": 34, "headRefName": "fix/21-a"}]
        self.assertEqual(budget([mine(21), mine(22), child(23)], prs=prs), 2)

    def test_foreign_claims_do_not_count(self):
        c = child(21, inProgress=True, assignees=["someone"])
        self.assertEqual(budget([c, child(22)]), 4)

    def test_resumed_claims_are_spawns_not_backlog(self):
        self.assertEqual(budget([mine(21)], resume=True), 4)

    def test_floors_at_zero(self):
        prs = [{"number": 30 + n, "headRefName": f"fix/{n}-x"} for n in range(21, 27)]
        self.assertEqual(budget([child(n) for n in range(21, 27)], prs=prs), 0)

    def test_flag_parses(self):
        self.assertEqual(parse_args(["12", "--max-open-prs", "3"]),
                         ("12", None, False, 3, 1))


if __name__ == "__main__":
    unittest.main()
