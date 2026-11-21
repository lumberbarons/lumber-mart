"""Tests for orca_api: the envelope, and the shapes captured from a live Orca 1.4.x.

Run with `python3 -m unittest discover tests/work-epic/work-epic`
— stdlib only; `sh` is a scripted fake.
"""

import sys
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
SCRIPTS = REPO / "plugins/work-epic/skills/work-epic/scripts"
sys.path.insert(0, str(SCRIPTS))

from orca_api import (Orca, OrcaError, Proc, find_key, normalise_show, normalise_worker,
                      orca_command, parse_envelope, payload, run_id, settled)

LIVE_RUN_CREATE = {"runId": "run_d449e4281c3a", "objective": "shape probe"}
LIVE_WORKER_ROW = {
    "dispatchId": "ctx_7bc191e00d99",
    "taskId": "task_5b7661f0fbb3",
    "state": "succeeded",
    "liveness": "exited",
    "agent": "opencode",
    "terminal": "term_96847382-6a02-4ec7-bb9e-c99a7fbbbc0e",
    "terminalState": "released",
    "workspace": "01e8a165-4724-4cac-a53b-09b4b16bf530::/Users/jim/orca/workspaces/hew/we-371",
    "host": "local",
}


def ok(result):
    return Proc(0, json.dumps({"id": "x", "ok": True, "result": result}), "")


def err(code, message="m", data=None, result=None, rc=1):
    env = {"id": "x", "ok": False, "error": {"code": code, "message": message, "data": data}}
    if result is not None:
        env["result"] = result
    return Proc(rc, json.dumps(env), "")


class Scripted:
    """An sh fake that returns queued responses and records each argv."""

    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, argv, cwd=None, input=None):
        self.calls.append(argv)
        return self.responses.pop(0)


def orca(*responses):
    sh = Scripted(*responses)
    return Orca(sh, command=["orca"]), sh


class Envelope(unittest.TestCase):
    def test_keepalive_lines_do_not_break_parsing(self):
        text = '{"_keepalive": true}\n{"ok": true, "result": {"a": 1}}\n'
        self.assertEqual(parse_envelope(text)["result"], {"a": 1})

    def test_result_is_returned_and_json_is_requested(self):
        o, sh = orca(ok({"runtime": {"state": "ready"}}))
        self.assertTrue(o.runtime_ready())
        self.assertEqual(sh.calls[0], ["orca", "status", "--json"])

    def test_error_carries_code_data_and_receipt(self):
        o, _ = orca(err("run_required", "No Run is bound", data={"effectsApplied": False},
                        result={"stage": "x"}))
        with self.assertRaises(OrcaError) as raised:
            o.tasks("run_1")
        e = raised.exception
        self.assertEqual((e.code, e.data["effectsApplied"], e.result), ("run_required", False, {"stage": "x"}))

    def test_garbage_is_unparsable_not_a_crash(self):
        o, _ = orca(Proc(1, "Segmentation fault", ""))
        with self.assertRaises(OrcaError) as raised:
            o.runs()
        self.assertEqual(raised.exception.code, "unparsable")

    def test_nonzero_exit_with_ok_true_is_still_a_failure(self):
        o, _ = orca(Proc(1, json.dumps({"ok": True, "result": {}}), ""))
        with self.assertRaises(OrcaError) as raised:
            o.runs()
        self.assertEqual(raised.exception.code, "exit_status")


class Executable(unittest.TestCase):
    def test_override_wins(self):
        with patch.dict(os.environ, {"ORCA_CLI_COMMAND": "orca-dev --flag"}):
            self.assertEqual(orca_command(), ["orca-dev", "--flag"])

    def test_dev_and_ide_come_before_the_screen_reader_name(self):
        with patch.dict(os.environ, {}, clear=False), \
             patch("shutil.which", side_effect=lambda n: "/bin/" + n if n in ("orca", "orca-ide") else None):
            os.environ.pop("ORCA_CLI_COMMAND", None)
            self.assertEqual(orca_command(), ["orca-ide"])

    def test_none_found_is_an_error(self):
        with patch.dict(os.environ, {}), patch("shutil.which", return_value=None):
            os.environ.pop("ORCA_CLI_COMMAND", None)
            with self.assertRaises(OrcaError):
                orca_command()


class Runs(unittest.TestCase):
    def test_run_create_reads_the_flat_run_id(self):
        o, _ = orca(ok(LIVE_RUN_CREATE))
        self.assertEqual(o.run_create("shape probe"), "run_d449e4281c3a")

    def test_run_create_still_reads_the_nested_run(self):
        o, _ = orca(ok({"run": {"id": "run_old", "objective": "shape probe"}}))
        self.assertEqual(o.run_create("shape probe"), "run_old")

    def test_run_current_reads_either_shape_and_null(self):
        o, _ = orca(ok({"runId": "run_new"}), ok({"run": {"id": "run_old"}}), ok({"runId": None}))
        self.assertEqual(o.run_current(), "run_new")
        self.assertEqual(o.run_current(), "run_old")
        self.assertIsNone(o.run_current())

    def test_run_id_helper_tolerates_a_missing_run(self):
        self.assertEqual(run_id({"runId": "run_new"}), "run_new")
        self.assertEqual(run_id({"run": {"id": "run_old"}}), "run_old")
        self.assertIsNone(run_id({}))


class Workers(unittest.TestCase):
    def test_start_receipt_takes_the_worktree_from_effects(self):
        receipt = {"runId": "run_1", "taskId": "task_1", "dispatchId": "ctx_1", "state": "ready",
                   "effects": [{"kind": "terminal", "action": "created", "id": "term_1"},
                               {"kind": "worktree", "action": "created_child", "id": "repo::/wt/we-21"}],
                   "residualResources": []}
        o, sh = orca(ok(receipt))
        got = o.worker_start(spec="do it", title="we-21 · opencode", agent="opencode",
                             worktree="new-child", repo="id:repo", name="we-21",
                             base_branch="origin/main", comment="c", setup="inherit")
        self.assertEqual((got.task, got.dispatch, got.worktree), ("task_1", "ctx_1", "repo::/wt/we-21"))
        argv = sh.calls[0]
        for flag, value in (("--worktree", "new-child"), ("--agent", "opencode"),
                            ("--task-title", "we-21 · opencode"), ("--setup", "inherit")):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertNotIn("--display-name", argv)

    def test_start_receipt_takes_the_flat_workspace(self):
        receipt = {"runId": "run_1", "taskId": "task_1", "dispatchId": "ctx_1", "state": "ready",
                   "agent": "opencode", "terminal": "term_1", "workspace": "repo::/wt/we-21"}
        o, _ = orca(ok(receipt))
        got = o.worker_start(spec="s", title="t", agent="opencode", worktree="new-child")
        self.assertEqual(got.worktree, "repo::/wt/we-21")

    def test_existing_worktree_receipt_has_no_worktree_effect(self):
        o, _ = orca(ok({"taskId": "t", "dispatchId": "d", "effects": []}))
        got = o.worker_start(spec="s", title="t", agent="claude", worktree="id:x")
        self.assertIsNone(got.worktree)

    def test_failed_start_keeps_the_receipt(self):
        o, _ = orca(err("start_failed", result={"failedStage": "launch", "dispatchId": "ctx_9",
                                                 "residualResources": [{"kind": "terminal"}]}))
        with self.assertRaises(OrcaError) as raised:
            o.worker_start(spec="s", title="t", agent="claude", worktree="new-child")
        self.assertEqual(find_key(raised.exception.result, "dispatchId"), "ctx_9")

    def test_workers_follow_pages(self):
        o, sh = orca(ok({"workers": [{"dispatchId": "a"}], "page": {"hasMore": True, "nextCursor": "c1"}}),
                     ok({"workers": [{"dispatchId": "b"}], "page": {"hasMore": False, "nextCursor": None}}))
        self.assertEqual([w["dispatchId"] for w in o.workers("run_1")], ["a", "b"])
        self.assertIn("--cursor", sh.calls[1])

    def test_workers_follow_the_top_level_next_cursor(self):
        first = {"workers": [{"dispatchId": "a", "state": "ready"}], "nextCursor": "c1",
                 "scope": {"run": "run_1", "source": "flag"}}
        second = {"workers": [{"dispatchId": "b", "state": "succeeded"}],
                  "scope": {"run": "run_1", "source": "flag"}}
        o, sh = orca(ok(first), ok(second))
        got = o.workers("run_1")
        self.assertEqual([w["dispatchId"] for w in got], ["a", "b"])
        self.assertEqual(sh.calls[1][sh.calls[1].index("--cursor") + 1], "c1")

    def test_a_settled_flat_row_is_normalised(self):
        o, _ = orca(ok({"workers": [LIVE_WORKER_ROW], "scope": {"run": "run_1"}}))
        (row,) = o.workers("run_1")
        self.assertTrue(settled(row))
        self.assertEqual(row["workerState"], "succeeded")
        self.assertEqual(row["dispatchStatus"], "completed")
        self.assertEqual(row["projection"]["workspace"]["id"], LIVE_WORKER_ROW["workspace"])
        self.assertEqual(row["projection"]["liveness"]["verdict"], "exited")
        self.assertNotIn("attention", row["projection"])

    def test_a_flat_attention_list_becomes_requires_action(self):
        row = normalise_worker({"state": "ready", "liveness": "live", "attention": ["approval"]})
        self.assertEqual(row["projection"]["attention"],
                         {"requiresAction": True, "categories": ["approval"]})
        self.assertFalse(settled(row))

    def test_an_old_nested_row_is_left_alone(self):
        old = {"dispatchId": "d", "workerState": "running", "dispatchStatus": "dispatched",
               "projection": {"workspace": {"id": "w"}, "liveness": {"verdict": "live"},
                              "attention": {"requiresAction": False, "categories": []}}}
        self.assertEqual(normalise_worker(old), old)
        self.assertFalse(settled(old))

    def test_settled_rows_from_a_live_run(self):
        done = {"workerState": "succeeded", "dispatchStatus": "completed", "terminalState": "released"}
        failed = {"workerState": "failed", "dispatchStatus": "failed"}
        running = {"workerState": "running", "dispatchStatus": "dispatched"}
        retained = {"workerState": "succeeded", "dispatchStatus": "completed", "terminalState": "retained",
                    "projection": {"liveness": {"verdict": "unverifiable"}}}
        self.assertEqual([settled(r) for r in (done, failed, running, retained)],
                         [True, True, False, True])
        self.assertTrue(settled(LIVE_WORKER_ROW))

    def test_worker_show_maps_waiting_on_human(self):
        absent = {"dispatchId": "ctx_a31f0c072478", "taskId": "task_631befbabece",
                  "runId": "run_d8709d4fdaa6", "state": "ready", "stage": "input_accepted",
                  "liveness": "live", "activity": "working", "lastActivity": "just now",
                  "terminal": "term_201469e9-9d3d-447e-ae2d-56597ac571d3",
                  "terminalState": "active", "workspace": LIVE_WORKER_ROW["workspace"]}
        unknown = {"dispatchId": "ctx_7bc191e00d99", "taskId": "task_5b7661f0fbb3",
                   "runId": "run_d8709d4fdaa6", "state": "succeeded", "stage": "settled",
                   "liveness": "exited", "terminal": LIVE_WORKER_ROW["terminal"],
                   "terminalState": "released", "workspace": LIVE_WORKER_ROW["workspace"],
                   "waitingOnHuman": "unknown"}
        parked = {"dispatchId": "ctx_parked", "state": "ready",
                  "waitingOnHuman": "permission prompt (via hook)"}
        o, _ = orca(ok(absent), ok(unknown), ok(parked))
        self.assertIsNone(o.worker_show("ctx_a31f0c072478").get("observation", {}).get("agentWait"))
        self.assertIsNone(o.worker_show("ctx_7bc191e00d99").get("observation", {}).get("agentWait"))
        self.assertEqual(o.worker_show("ctx_parked")["observation"]["agentWait"],
                         "permission prompt (via hook)")

    def test_worker_show_keeps_the_old_observation(self):
        old = {"observation": {"agentWait": "permission prompt"}}
        self.assertEqual(normalise_show(old)["observation"]["agentWait"], "permission prompt")


class Mailbox(unittest.TestCase):
    def test_check_waits_acks_and_filters(self):
        delivery = {"runId": "run_1", "deliveryId": "delivery_1", "count": 1, "timedOut": False,
                    "messages": [{"id": "msg_1", "type": "worker_done",
                                  "payload": json.dumps({"dispatchId": "ctx_1", "outcome": "succeeded"})}]}
        o, sh = orca(ok(delivery))
        res = o.check("run_1", timeout_ms=1000, ack="delivery_0")
        self.assertEqual(res["deliveryId"], "delivery_1")
        argv = sh.calls[0]
        self.assertEqual(argv[argv.index("--ack") + 1], "delivery_0")
        self.assertIn("--wait", argv)
        self.assertEqual(payload(res["messages"][0])["dispatchId"], "ctx_1")

    def test_payload_survives_garbage(self):
        self.assertEqual(payload({"payload": "not json"}), {})
        self.assertEqual(payload({}), {})


class Worktrees(unittest.TestCase):
    def test_set_flags(self):
        o, sh = orca(ok({"worktree": {"id": "w"}}))
        o.worktree_set("repo::/p", comment="c", status="in-review", issue=21, pr=34, unread=True)
        self.assertEqual(sh.calls[0][1:], ["worktree", "set", "--worktree", "id:repo::/p", "--comment", "c",
                                           "--workspace-status", "in-review", "--issue", "21", "--pr", "34",
                                           "--unread", "--json"])

    def test_unread_false_clears_and_none_leaves_it(self):
        o, sh = orca(ok({"worktree": {}}), ok({"worktree": {}}))
        o.worktree_set("w", unread=False)
        o.worktree_set("w", comment="x")
        self.assertIn("--read", sh.calls[0])
        self.assertNotIn("--read", sh.calls[1])
        self.assertNotIn("--unread", sh.calls[1])


if __name__ == "__main__":
    unittest.main()
