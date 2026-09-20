"""Smoke test for Step 17: the golden demo path end to end.

One integration check through the real student API (scripted execution
abstraction, test-only fake):

    health -> session -> canonical problem -> wrong submission
      -> diagnosis + intervention -> retry pass -> transfer
      -> VERIFIED_IMPROVED -> next recommendation

Plus API hardening probes: duplicate submits stay deterministic, malformed
/ mistyped / oversized bodies are rejected with safe error shapes, and
CORS remains allowlisted.

Run from repo root:
    python -m unittest discover -s services/core-backend/tests -t . -v

NOTE: ``services/core-backend`` is not importable (hyphen), so this file
bootstraps sys.path with the repo root AND the service dir.
"""
from __future__ import annotations

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


class GoldenPathSmokeTests(unittest.TestCase):
    """The 3-5 minute demo, asserted end to end."""

    def test_golden_path(self):
        client = make_client()

        # 1. Backend health needs no LLM, database, frontend, or session.
        health = client.get("/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(
            health.json(), {"status": "ok", "service": "core-backend"}
        )

        # 2-3. Session creation hands over the canonical problem.
        session = client.post("/student/sessions", json={}).json()
        sid = session["session_id"]
        self.assertTrue(sid.strip())
        self.assertEqual(session["problem"]["problem_id"], CANONICAL_ID)
        problem = client.get(
            f"/student/problems/{CANONICAL_ID}", params={"session_id": sid}
        ).json()
        self.assertEqual(problem["title"], session["problem"]["title"])
        self.assertIn("starter_code", problem)

        # 4-5. Wrong submission -> failure + diagnosis + intervention.
        wrong = client.post(
            "/student/submissions",
            json={"session_id": sid, "problem_id": CANONICAL_ID, "code": WRONG_CODE},
        )
        self.assertEqual(wrong.status_code, 200, wrong.text)
        failed = wrong.json()
        self.assertEqual(failed["outcome"], "FAILED")
        self.assertEqual(failed["diagnosis"]["misconception_id"], "C3-M01")
        self.assertTrue(failed["diagnosis"]["explanation"].strip())
        self.assertEqual(
            failed["intervention"]["intervention_type"], "BOUNDARY_CHECK"
        )
        self.assertTrue(failed["intervention"]["student_message"].strip())
        self.assertTrue(
            failed["intervention"]["recommended_action"].strip()
        )

        # 6. Retry with corrected code passes and unlocks transfer.
        retry = client.post(
            "/student/submissions",
            json={"session_id": sid, "problem_id": CANONICAL_ID, "code": FIXED_CODE},
        ).json()
        self.assertEqual(retry["outcome"], "PASSED")
        self.assertTrue(retry["transfer_available"])
        self.assertEqual(retry["transfer_problem"]["problem_id"], TRANSFER_ID)

        # 7-9. Transfer submission -> VERIFIED_IMPROVED + recommendation.
        transfer = client.post(
            "/student/submissions",
            json={
                "session_id": sid,
                "problem_id": TRANSFER_ID,
                "code": TRANSFER_CODE,
            },
        )
        self.assertEqual(transfer.status_code, 200, transfer.text)
        done = transfer.json()
        self.assertEqual(done["outcome"], "PASSED")
        self.assertEqual(done["verification"]["outcome"], "VERIFIED_IMPROVED")
        self.assertTrue(done["verification"]["message"].strip())
        self.assertGreater(len(done["recommendations"]), 0)
        first = done["recommendations"][0]
        self.assertTrue(first["action"].strip())
        self.assertTrue(first["reason"].strip())

        # 10. Journey endpoint agrees with the final state.
        journey = client.get(
            "/student/journey", params={"session_id": sid}
        ).json()
        self.assertEqual(journey["journey_state"]["stage"], "transfer_done")
        self.assertEqual(
            journey["verification"]["outcome"], "VERIFIED_IMPROVED"
        )


class SubmissionHardeningTests(unittest.TestCase):
    def test_duplicate_submit_is_deterministic(self):
        client = make_client()
        sid = client.post("/student/sessions", json={}).json()["session_id"]
        payload = {
            "session_id": sid,
            "problem_id": CANONICAL_ID,
            "code": WRONG_CODE,
        }
        first = client.post("/student/submissions", json=payload).json()
        second = client.post("/student/submissions", json=payload).json()
        # Same evidence -> same outcome, execution, and diagnosis.
        for key in ("outcome", "diagnosis"):
            self.assertEqual(second[key], first[key])
        self.assertEqual(
            second["execution"]["failed_count"],
            first["execution"]["failed_count"],
        )
        # Intervention stays on the same misconception/type; only the
        # history-driven level may escalate monotonically (Step 15 rule:
        # seen-once -> L2), never randomly.
        self.assertEqual(
            second["intervention"]["misconception_id"],
            first["intervention"]["misconception_id"],
        )
        self.assertEqual(
            second["intervention"]["intervention_type"],
            first["intervention"]["intervention_type"],
        )
        order = ("L1", "L2", "L3", "L4")
        self.assertGreaterEqual(
            order.index(second["intervention"]["intervention_level"]),
            order.index(first["intervention"]["intervention_level"]),
        )
        journey = client.get(
            "/student/journey", params={"session_id": sid}
        ).json()
        self.assertEqual(journey["journey_state"]["stage"], "practicing")

    def test_malformed_bodies_rejected_safely(self):
        client = make_client()
        sid = client.post("/student/sessions", json={}).json()["session_id"]
        bad_bodies = [
            {"session_id": sid, "problem_id": CANONICAL_ID},  # missing code
            {"session_id": sid, "code": "x=1\n"},  # missing problem_id
            {
                "session_id": sid,
                "problem_id": CANONICAL_ID,
                "code": 12345,  # mistyped code
            },
            "not-an-object",
        ]
        for body in bad_bodies:
            resp = client.post("/student/submissions", json=body)
            self.assertIn(resp.status_code, (404, 422), repr(body))
            self.assertNotIn("Traceback", resp.text)
            self.assertNotIn("File \"", resp.text)

    def test_oversized_code_rejected(self):
        client = make_client()
        sid = client.post("/student/sessions", json={}).json()["session_id"]
        resp = client.post(
            "/student/submissions",
            json={
                "session_id": sid,
                "problem_id": CANONICAL_ID,
                "code": "x = 1\n" + "#" * 100_001,
            },
        )
        self.assertEqual(resp.status_code, 422)
        self.assertNotIn("Traceback", resp.text)

    def test_error_bodies_are_safe(self):
        client = make_client()
        probes = [
            ("POST", "/student/submissions", {
                "session_id": "nope", "problem_id": CANONICAL_ID, "code": "x=1\n",
            }),
            ("POST", "/student/submissions", {
                "session_id": "x", "problem_id": "NOPE", "code": "x=1\n",
            }),
            ("GET", "/student/journey?session_id=nope", None),
        ]
        for method, path, body in probes:
            if method == "POST":
                resp = client.post(path, json=body)
            else:
                resp = client.get(path)
            self.assertIn(resp.status_code, (404, 409, 422), path)
            detail = resp.json().get("detail", "")
            self.assertTrue(str(detail).strip())
            for leaked in ("Traceback", "sqlalchemy", "DATABASE_URL", "sk-"):
                self.assertNotIn(leaked, resp.text)

    def test_cors_allowlist_present(self):
        client = make_client()
        allowed = client.get(
            "/health", headers={"Origin": "http://localhost:3000"}
        )
        self.assertEqual(
            allowed.headers.get("access-control-allow-origin"),
            "http://localhost:3000",
        )
        denied = client.get("/health", headers={"Origin": "http://evil.example"})
        self.assertNotEqual(
            denied.headers.get("access-control-allow-origin"),
            "http://evil.example",
        )


if __name__ == "__main__":
    unittest.main()
