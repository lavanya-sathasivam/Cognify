"""Unit tests for Step 20B: read-only student data APIs (core-backend).

Covers the three new endpoints through the EXISTING engines only
(orchestrated, never reimplemented):

    GET /student/concepts -> 8 taxonomy concepts + learner-engine views
                             + adaptive-engine next action
    GET /student/history  -> student-safe attempt history from existing
                             append-only events
    GET /student/problems -> safe catalog discovered via the bank loader

Read-only contract: repeated GETs never change learner state (no mastery
/ attempt / misconception / event / adaptive mutation).

NOTE: ``services/core-backend`` is not importable (hyphen), so this file
bootstraps sys.path with the repo root AND the service dir.
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
_ROOT = _HERE.parents[3]  # .../Cognify
_SERVICE_DIR = _ROOT / "services" / "core-backend"
for _p in (str(_ROOT), str(_SERVICE_DIR), str(_HERE.parent)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fake_runner import (  # noqa: E402
    CANONICAL_ID,
    FIXED_CODE,
    TRANSFER_CODE,
    TRANSFER_ID,
    WRONG_CODE,
    make_client,
)
from fastapi.testclient import TestClient  # noqa: E402

from packages.adaptive.models import ActionType  # noqa: E402
from packages.problem_bank import loader as bank_loader  # noqa: E402
from packages.taxonomy import list_concept_ids  # noqa: E402

_MID_RE = re.compile(r"\bC[1-8]-M\d{2}\b")

_VALID_ACTIONS = {a.value for a in ActionType}


def _client() -> TestClient:
    return make_client()


def _new_session(client: TestClient) -> str:
    resp = client.post("/student/sessions", json={})
    assert resp.status_code == 200, resp.text
    return resp.json()["session_id"]


def _submit(client: TestClient, session_id: str, problem_id: str, code: str):
    resp = client.post(
        "/student/submissions",
        json={"session_id": session_id, "problem_id": problem_id, "code": code},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


class ConceptsTests(unittest.TestCase):
    def test_all_eight_concepts_in_taxonomy_order(self):
        client = _client()
        body = client.get(
            "/student/concepts", params={"session_id": _new_session(client)}
        ).json()
        self.assertEqual(
            [c["concept_id"] for c in body["concepts"]], list_concept_ids()
        )
        self.assertEqual(len(body["concepts"]), 8)

    def test_taxonomy_metadata_and_groups(self):
        client = _client()
        body = client.get(
            "/student/concepts", params={"session_id": _new_session(client)}
        ).json()
        by_id = {c["concept_id"]: c for c in body["concepts"]}
        c3 = by_id["C3"]
        self.assertEqual(c3["title"], "Loops & Iteration Control")
        self.assertEqual(c3["prerequisites"], ["C1", "C2"])
        self.assertTrue(c3["description"].strip())
        self.assertEqual(by_id["C1"]["group"], "Foundations")
        self.assertEqual(by_id["C2"]["group"], "Control Flow")
        self.assertEqual(by_id["C3"]["group"], "Control Flow")
        self.assertEqual(by_id["C4"]["group"], "Functions")
        self.assertEqual(by_id["C5"]["group"], "Collections")
        self.assertEqual(by_id["C6"]["group"], "Collections")
        self.assertEqual(by_id["C7"]["group"], "Objects")
        self.assertEqual(by_id["C8"]["group"], "Recursion & Beyond")

    def test_fresh_session_is_honestly_not_started(self):
        client = _client()
        body = client.get(
            "/student/concepts", params={"session_id": _new_session(client)}
        ).json()
        for card in body["concepts"]:
            self.assertEqual(card["status"], "not_started")
            self.assertEqual(card["attempt_count"], 0)
            self.assertEqual(card["pass_count"], 0)
            self.assertEqual(card["fail_count"], 0)
            self.assertEqual(card["recent_history"], [])
            self.assertFalse(card["mastery_claim"])

    def test_real_c3_state_after_failed_submission(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        body = client.get(
            "/student/concepts", params={"session_id": session_id}
        ).json()
        by_id = {c["concept_id"]: c for c in body["concepts"]}
        c3 = by_id["C3"]
        self.assertEqual(c3["status"], "started")
        self.assertEqual(c3["attempt_count"], 1)
        self.assertEqual(c3["pass_count"], 0)
        self.assertEqual(c3["fail_count"], 1)
        self.assertEqual(len(c3["recent_history"]), 1)
        self.assertEqual(c3["recent_history"][0]["problem_id"], CANONICAL_ID)
        self.assertFalse(c3["recent_history"][0]["passed"])
        # Untouched concepts stay honestly empty.
        for cid in ("C1", "C2", "C4", "C5", "C6", "C7", "C8"):
            self.assertEqual(by_id[cid]["status"], "not_started")
            self.assertEqual(by_id[cid]["attempt_count"], 0)

    def test_concepts_get_never_mutates(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        first = client.get(
            "/student/concepts", params={"session_id": session_id}
        ).json()
        second = client.get(
            "/student/concepts", params={"session_id": session_id}
        ).json()
        self.assertEqual(first, second)
        history = client.get(
            "/student/history", params={"session_id": session_id}
        ).json()
        self.assertEqual(history["total"], 1)

    def test_next_action_comes_from_adaptive_engine(self):
        client = _client()
        session_id = _new_session(client)
        body = client.get(
            "/student/concepts", params={"session_id": session_id}
        ).json()
        action = body["next_action"]
        self.assertIsNotNone(action)
        assert action is not None
        self.assertIn(action["action"], _VALID_ACTIONS)
        self.assertTrue((action["reason"] or "").strip())
        self.assertIn(action["concept_id"], list_concept_ids())
        if action["problem_id"] is not None:
            # Any suggested problem must really exist with that title.
            problem = bank_loader.load_problem(action["problem_id"])
            self.assertEqual(action["problem_title"], problem.title)

    def test_concepts_response_is_student_safe(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        resp = client.get("/student/concepts", params={"session_id": session_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertIsNone(_MID_RE.search(resp.text))
        for key in ("expected_output", "isomorphic", "misconception_ids",
                    "evidence_refs", "starter_code"):
            self.assertNotIn(key, resp.text)

    def test_unknown_session_rejected(self):
        self.assertEqual(
            _client().get("/student/concepts", params={"session_id": "nope"}).status_code,
            404,
        )


class HistoryTests(unittest.TestCase):
    def test_empty_history_is_honest(self):
        client = _client()
        body = client.get(
            "/student/history", params={"session_id": _new_session(client)}
        ).json()
        self.assertEqual(body["total"], 0)
        self.assertEqual(body["items"], [])

    def test_failed_attempt_history_entry(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        body = client.get(
            "/student/history", params={"session_id": session_id}
        ).json()
        self.assertEqual(body["total"], 1)
        item = body["items"][0]
        self.assertEqual(item["order"], 1)
        self.assertEqual(item["problem_id"], CANONICAL_ID)
        self.assertEqual(item["problem_title"], "Count Divisible Numbers")
        self.assertEqual(item["concept_id"], "C3")
        self.assertEqual(item["outcome"], "failed")
        self.assertEqual(item["execution_status"], "FAILED")
        self.assertFalse(item["is_transfer"])
        self.assertTrue(item["feedback"].strip())
        self.assertFalse(item["verified"])
        self.assertIsNotNone(item["created_at"])

    def test_full_journey_history_marks_verified_transfer(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        _submit(client, session_id, CANONICAL_ID, FIXED_CODE)
        _submit(client, session_id, TRANSFER_ID, TRANSFER_CODE)
        body = client.get(
            "/student/history", params={"session_id": session_id}
        ).json()
        # Only recorded attempts appear (the canonical PASS goes through
        # the closed loop on transfer): 1 fail + 2 closed-loop records.
        self.assertGreaterEqual(body["total"], 2)
        outcomes = [i["outcome"] for i in body["items"]]
        self.assertIn("failed", outcomes)
        self.assertIn("passed", outcomes)
        transfers = [i for i in body["items"] if i["is_transfer"]]
        self.assertTrue(transfers)
        self.assertTrue(any(i["verified"] for i in transfers))

    def test_limit_handling(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        one = client.get(
            "/student/history", params={"session_id": session_id, "limit": 1}
        ).json()
        self.assertEqual(len(one["items"]), 1)
        self.assertEqual(one["items"][0]["order"], 2)
        capped = client.get(
            "/student/history", params={"session_id": session_id, "limit": 500}
        ).json()
        self.assertEqual(capped["limit"], 50)
        bad = client.get(
            "/student/history", params={"session_id": session_id, "limit": 0}
        )
        self.assertEqual(bad.status_code, 422)

    def test_history_get_never_mutates(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        first = client.get(
            "/student/history", params={"session_id": session_id}
        ).json()
        second = client.get(
            "/student/history", params={"session_id": session_id}
        ).json()
        self.assertEqual(first, second)
        concepts = client.get(
            "/student/concepts", params={"session_id": session_id}
        ).json()
        c3 = [c for c in concepts["concepts"] if c["concept_id"] == "C3"][0]
        self.assertEqual(c3["attempt_count"], 1)

    def test_session_isolation(self):
        client = _client()
        first = _new_session(client)
        second = _new_session(client)
        _submit(client, first, CANONICAL_ID, WRONG_CODE)
        untouched = client.get(
            "/student/history", params={"session_id": second}
        ).json()
        self.assertEqual(untouched["total"], 0)
        self.assertEqual(untouched["items"], [])

    def test_no_hidden_output_leakage(self):
        client = _client()
        session_id = _new_session(client)
        _submit(client, session_id, CANONICAL_ID, WRONG_CODE)
        resp = client.get("/student/history", params={"session_id": session_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        canonical = bank_loader.load_problem(CANONICAL_ID)
        transfer = bank_loader.load_problem(TRANSFER_ID)
        hidden = [t.expected_output for t in canonical.hidden_tests]
        hidden += [t.expected_output for t in transfer.hidden_tests]
        for answer in hidden:
            self.assertNotIn(f'"expected_output": "{answer}"', resp.text)
        self.assertIsNone(_MID_RE.search(resp.text))
        for key in ("isomorphic", "misconception_ids", "evidence_refs"):
            self.assertNotIn(key, resp.text)

    def test_unknown_session_rejected(self):
        self.assertEqual(
            _client().get("/student/history", params={"session_id": "nope"}).status_code,
            404,
        )


class ProblemsTests(unittest.TestCase):
    def test_discovers_whole_bank_dynamically(self):
        client = _client()
        body = client.get(
            "/student/problems", params={"session_id": _new_session(client)}
        ).json()
        expected_ids = bank_loader.list_problem_ids()
        self.assertEqual(body["total"], len(expected_ids))
        self.assertEqual(
            sorted(p["problem_id"] for p in body["problems"]), expected_ids
        )

    def test_safe_metadata_shape(self):
        client = _client()
        body = client.get(
            "/student/problems", params={"session_id": _new_session(client)}
        ).json()
        for entry in body["problems"]:
            self.assertEqual(
                set(entry),
                {"problem_id", "title", "language", "concept_id",
                 "concept_title", "difficulty", "role", "description"},
            )
            self.assertIs(type(entry["difficulty"]), int)
            self.assertIn(entry["role"], ("canonical", "transfer", "remedial"))
            self.assertTrue(entry["title"].strip())
            self.assertTrue(entry["description"].strip())
        canonical = [p for p in body["problems"] if p["problem_id"] == CANONICAL_ID][0]
        self.assertEqual(canonical["concept_id"], "C3")
        self.assertEqual(canonical["concept_title"], "Loops & Iteration Control")

    def test_no_solution_or_test_leakage(self):
        client = _client()
        session_id = _new_session(client)
        resp = client.get("/student/problems", params={"session_id": session_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        self.assertNotIn("expected_output", resp.text)
        self.assertNotIn("misconception_ids", resp.text)
        self.assertNotIn("isomorphic", resp.text.lower())
        self.assertNotIn("starter_code", resp.text)
        self.assertNotIn("hidden_tests", resp.text)
        self.assertNotIn("public_tests", resp.text)
        self.assertIsNone(_MID_RE.search(resp.text))

    def test_unknown_session_rejected(self):
        self.assertEqual(
            _client().get("/student/problems", params={"session_id": "nope"}).status_code,
            404,
        )


class ReadOnlyOrchestrationTests(unittest.TestCase):
    def test_read_endpoints_delegate_without_new_rules(self):
        """New GETs reuse engines; they invent no mastery/adaptive logic."""
        import ast as _ast

        tree = _ast.parse(
            (_SERVICE_DIR / "app" / "student.py").read_text(encoding="utf-8"),
            filename="student.py",
        )
        called: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call):
                func = node.func
                if isinstance(func, _ast.Name):
                    called.add(func.id)
                elif isinstance(func, _ast.Attribute):
                    called.add(func.attr)
        for required in (
            "get_concept_view",
            "get_misconception_view",
            "recommend_next_actions",
            "load_all_problems",
            "list_events_for_journey",
        ):
            self.assertIn(required, called, f"read path bypasses {required}")
        duplicated = {
            "compute_mastery_update",
            "mastery_band",
            "compute_trend",
            "evaluate_concept",
            "evaluate_all",
            "rank_recommendations",
            "verify_improvement",
            "fallback_diagnose",
            "build_evidence_pack",
        }
        # The read-only views must not reimplement engine internals. Note:
        # ``mastery_band``/``verify_improvement`` appear in the pre-existing
        # submission flow (Step 16), so scope the check to the Step 20B
        # functions only (module helpers + new endpoints, including the
        # nested endpoint defs inside ``create_student_router``).
        new_funcs = {
            "_group_for_concept",
            "_concept_card",
            "_next_action_view",
            "_full_problem_catalog",
            "_human_issue_summary",
            "_history_feedback",
            "_safe_description",
            "get_concepts",
            "get_history",
            "list_problems",
        }
        block_called: set[str] = set()
        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and (
                node.name in new_funcs
            ):
                for child in _ast.walk(node):
                    if isinstance(child, _ast.Call):
                        func = child.func
                        if isinstance(func, _ast.Name):
                            block_called.add(func.id)
                        elif isinstance(func, _ast.Attribute):
                            block_called.add(func.attr)
        self.assertTrue(
            new_funcs <= {n.name for n in _ast.walk(tree) if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef))},
            "Step 20B functions missing from student.py",
        )
        hits = block_called & duplicated
        self.assertEqual(hits, set(), f"Step 20B duplicates logic: {hits}")


if __name__ == "__main__":
    unittest.main()
