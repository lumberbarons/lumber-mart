"""Classification tests for resolve_ready.classify.

Run with `python3 -m unittest discover plugins/work-epic/skills/work-epic/scripts`
— stdlib only, no network: classify is pure over hew JSON plus the PR and
branch indexes.
"""

import unittest

from resolve_ready import classify, delivery_index, parse_args, spawn_budget

ME = "orchestrator"


def child(n, **kw):
    c = {"number": n, "title": f"child {n}", "state": "open", "priority": "P2",
         "type": "task", "body": ""}
    c.update(kw)
    return c


def mine(n):
    return child(n, inProgress=True, assignees=[ME])


def reasons(children, prs=(), branches=(), resume=False, me=ME):
    pr_by_issue, branch_by_issue = delivery_index(list(prs), list(branches))
    eligible, skipped, _ = classify(children, me, pr_by_issue, branch_by_issue, resume)
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
        self.assertEqual(parse_args(["12", "--max-open-prs", "3"]), ("12", None, False, 3))


if __name__ == "__main__":
    unittest.main()
