#!/usr/bin/env python3
"""Executable, stdlib-only acceptance adapter with real SQLite and reducer assertions.

Success means these defined offline cases passed, not a production certification.
Negative controls alter the imported implementation, not the assertions/results.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest

from domain import (
    Actor, ApprovalRequired, Denied, IdempotencyConflict, StaleEvidence,
    TicketStore, UnknownOutcome, VersionConflict,
)
from ui import ReceiptRequired, UIReducer


PERMISSIONS = frozenset({"ticket:read", "ticket:propose", "ticket:approve", "ticket:apply"})
ALICE = Actor("tenant-a", "alice", PERMISSIONS)
BOB = Actor("tenant-b", "bob", PERMISSIONS)

CASE_IDS = (
    "tenant_isolation", "unauthorized_write", "duplicate_commit", "changed_payload",
    "stale_proposal", "unapproved_proposal", "rollback_gap", "lost_response",
    "concurrent_duplicate", "partial_disconnect", "receipt_required", "stale_evidence",
    "approval_payload_bound", "ui_terminal_state",
)
DEFECTS = ("skip_idempotency_replay", "allow_unreceipted_commit")


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class AcceptanceCases(unittest.TestCase):
    def __init__(self, methodName, defect=None):
        super().__init__(methodName)
        self.defect = defect
        self.detail = ""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agui-service-desk-")
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "tickets.sqlite"
        self.clock = Clock()
        self.store = self.open_store()
        self.addCleanup(self.store.close)
        self.store.seed_ticket("tenant-a", "T-1", 3)
        self.store.seed_ticket("tenant-b", "T-1", 4)
        self.store.seed_ticket("tenant-a", "A-only", 3)

    def open_store(self):
        return TicketStore(self.path, clock=self.clock, evidence_ttl=60, defect=self.defect)

    def prepare(self, proposal_id="p1", priority=1, *, approve=True, actor=ALICE):
        evidence = self.store.read_ticket(actor, "T-1")
        proposal = self.store.propose(actor, proposal_id, evidence["evidence_id"], priority)
        ph = proposal["proposal_hash"]
        if approve:
            self.store.approve(actor, proposal_id, ph)
        return ph

    def actual(self, tenant="tenant-a", ticket="T-1"):
        # Independent SQLite reader: assertions do not trust a method's success text.
        with sqlite3.connect(self.path) as reader:
            row = reader.execute("SELECT priority,version FROM tickets WHERE tenant=? AND id=?",
                                 (tenant, ticket)).fetchone()
            operations = reader.execute("SELECT count(*) FROM operations WHERE tenant=?", (tenant,)).fetchone()[0]
            return row, operations

    def test_tenant_isolation(self):
        evidence = self.store.read_ticket(ALICE, "T-1")
        self.assertEqual(self.store.read_ticket(BOB, "T-1")["ticket"]["priority"], 4)
        with self.assertRaises(Denied):
            self.store.read_ticket(BOB, "A-only")
        with self.assertRaises(Denied):
            self.store.propose(BOB, "stolen", evidence["evidence_id"], 1)
        ph = self.prepare()
        with self.assertRaises(Denied):
            self.store.apply(BOB, "op1", "p1", ph)
        receipt = self.store.apply(ALICE, "op1", "p1", ph)
        self.assertEqual(receipt["tenant_id"], "tenant-a")
        self.assertIsNone(self.store.receipt(BOB, "op1"))
        self.assertEqual(self.actual(), ((1, 1), 1))
        self.assertEqual(self.actual("tenant-b"), ((4, 0), 0))
        self.detail = "Same ticket ID remains tenant-scoped; foreign evidence/proposal/receipt unavailable."

    def test_unauthorized_write(self):
        readonly = Actor("tenant-a", "alice", frozenset({"ticket:read"}))
        evidence = self.store.read_ticket(readonly, "T-1")
        with self.assertRaises(Denied):
            self.store.propose(readonly, "denied", evidence["evidence_id"], 1)
        ph = self.prepare(approve=False)
        with self.assertRaises(Denied):
            self.store.approve(readonly, "p1", ph)
        self.store.approve(ALICE, "p1", ph)
        with self.assertRaises(Denied):
            self.store.apply(readonly, "op1", "p1", ph)
        self.assertEqual(self.actual(), ((3, 0), 0))
        self.store.apply(ALICE, "op1", "p1", ph)
        with self.assertRaises(Denied):
            self.store.apply(readonly, "op1", "p1", ph)  # No unauthorized receipt replay.
        reducer = UIReducer(self.store, readonly)
        reducer.validated("p1", ph)
        self.assertFalse(reducer.state["can_approve"])
        self.detail = "Propose, approve, apply and replay require host permissions; denied writes leave DB unchanged."

    def test_duplicate_commit(self):
        ph = self.prepare()
        first = self.store.apply(ALICE, "op1", "p1", ph)
        second = self.store.apply(ALICE, "op1", "p1", ph)
        self.assertEqual(first, second)
        self.assertEqual(self.actual(), ((1, 1), 1))
        self.detail = "Same operation returns the original receipt; one version increment and one persisted operation."

    def test_changed_payload(self):
        ph = self.prepare()
        self.store.apply(ALICE, "op1", "p1", ph)
        next_hash = self.prepare("p2", 2)
        with self.assertRaises(IdempotencyConflict):
            self.store.apply(ALICE, "op1", "p2", next_hash)
        self.assertEqual(self.actual(), ((1, 1), 1))
        self.detail = "Reusing an operation ID for a different approved proposal is rejected before another write."

    def test_stale_proposal(self):
        ph = self.prepare("p1", 1)
        competing = self.prepare("p2", 2)
        self.store.apply(ALICE, "op2", "p2", competing)
        with self.assertRaises(VersionConflict):
            self.store.apply(ALICE, "op1", "p1", ph)
        fresh = self.prepare("fresh", 1, approve=False)
        with self.assertRaises(ApprovalRequired):
            self.store.apply(ALICE, "fresh-op", "fresh", fresh)
        self.assertEqual(self.actual(), ((2, 1), 1))
        self.store.approve(ALICE, "fresh", fresh)
        self.store.apply(ALICE, "fresh-op", "fresh", fresh)
        self.assertEqual(self.actual(), ((1, 2), 2))
        self.detail = "Competing write invalidates old proposal; refreshed proposal needs a new approval before commit."

    def test_unapproved_proposal(self):
        ph = self.prepare(approve=False)
        with self.assertRaises(ApprovalRequired):
            self.store.apply(ALICE, "op1", "p1", ph)
        self.assertEqual(self.actual(), ((3, 0), 0))
        self.detail = "A valid proposal and execute permission do not substitute for exact host approval."

    def test_rollback_gap(self):
        ph = self.prepare()
        def fail(stage):
            if stage == "after_ticket_write":
                raise RuntimeError("injected ticket/receipt gap")
        with self.assertRaises(RuntimeError):
            self.store.apply(ALICE, "op1", "p1", ph, fault=fail)
        self.assertEqual(self.actual(), ((3, 0), 0))
        self.store.apply(ALICE, "op1", "p1", ph)
        self.assertEqual(self.actual(), ((1, 1), 1))
        self.detail = "Failure after UPDATE rolls back ticket and receipt; same operation can then commit once."

    def test_lost_response(self):
        ph = self.prepare()
        def lose(stage):
            if stage == "after_commit":
                raise ConnectionError("injected acknowledgement loss")
        with self.assertRaises(UnknownOutcome):
            self.store.apply(ALICE, "op1", "p1", ph, fault=lose)
        self.assertEqual(self.actual(), ((1, 1), 1))
        saved = self.store.receipt(ALICE, "op1")
        self.store.close()
        self.clock.now += 61  # Completed operation replay must survive evidence expiry.
        reopened = self.open_store()
        try:
            self.assertEqual(reopened.apply(ALICE, "op1", "p1", ph), saved)
            self.assertEqual(self.actual(), ((1, 1), 1))
        finally:
            reopened.close()
        self.detail = "Post-commit response loss reports unknown to caller; reopened store replays persisted receipt once."

    def test_concurrent_duplicate(self):
        ph = self.prepare()
        barrier = threading.Barrier(2)
        def worker():
            store = self.open_store()
            try:
                barrier.wait(timeout=5)
                return store.apply(ALICE, "op1", "p1", ph)
            finally:
                store.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            first, second = list(pool.map(lambda _: worker(), range(2)))
        self.assertEqual(first, second)
        self.assertEqual(self.actual(), ((1, 1), 1))
        self.detail = "Two real SQLite connections race; both receive one receipt and DB commits only once."

    def test_partial_disconnect(self):
        reducer = UIReducer(self.store, ALICE, defect=self.defect)
        reducer.partial('untrusted streamed text: {"priority": 1')
        self.assertEqual(reducer.state["phase"], "partial")
        self.assertFalse(reducer.state["can_approve"])
        reducer.interrupted()
        reducer.partial("late frame claiming success")
        self.assertEqual(reducer.state["phase"], "interrupted")
        self.assertIsNone(reducer.state["receipt"])
        self.assertFalse(reducer.state["can_approve"])
        self.assertEqual(self.actual(), ((3, 0), 0))
        self.detail = "Disconnected partial output remains interrupted/non-actionable; no receipt and no business mutation."

    def test_receipt_required(self):
        ph = self.prepare()
        reducer = UIReducer(self.store, ALICE, defect=self.defect)
        reducer.validated("p1", ph)
        self.assertEqual(reducer.state["phase"], "validated")
        with self.assertRaises(ReceiptRequired):
            reducer.committed(None)
        with self.assertRaises(ReceiptRequired):
            reducer.committed({"operation_id": "invented", "proposal_id": "p1"})
        self.assertEqual(self.actual(), ((3, 0), 0))
        receipt = self.store.apply(ALICE, "op1", "p1", ph)
        forged = dict(receipt, priority_after=4)
        with self.assertRaises(ReceiptRequired):
            reducer.committed(forged)
        reducer.committed(receipt)
        self.assertEqual(reducer.state["phase"], "committed")
        self.assertEqual(reducer.state["receipt"], self.store.receipt(ALICE, "op1"))
        self.detail = "Missing/invented/altered receipt rejected; committed UI requires exact persisted receipt matching preview."

    def test_stale_evidence(self):
        evidence = self.store.read_ticket(ALICE, "T-1")
        self.clock.now += 61
        with self.assertRaises(StaleEvidence):
            self.store.propose(ALICE, "expired", evidence["evidence_id"], 1)
        ph = self.prepare()
        self.clock.now += 61
        with self.assertRaises(StaleEvidence):
            self.store.apply(ALICE, "op1", "p1", ph)
        self.assertEqual(self.actual(), ((3, 0), 0))
        old = self.store.read_ticket(ALICE, "T-1")
        fresh_hash = self.prepare("p2", 2)
        self.store.apply(ALICE, "op2", "p2", fresh_hash)
        with self.assertRaises(StaleEvidence):
            self.store.propose(ALICE, "old-version", old["evidence_id"], 1)
        self.assertEqual(self.actual(), ((2, 1), 1))
        self.detail = "Evidence TTL checked at propose and commit; otherwise fresh evidence with obsolete entity version is rejected."

    def test_approval_payload_bound(self):
        ph = self.prepare()
        with self.assertRaises(ApprovalRequired):
            self.store.approve(ALICE, "p1", "different-displayed-hash")
        with self.assertRaises(ApprovalRequired):
            self.store.apply(ALICE, "wrong-hash", "p1", "different-displayed-hash")
        second_hash = self.prepare("p2", 2, approve=False)
        with self.assertRaises(ApprovalRequired):
            self.store.apply(ALICE, "op2", "p2", second_hash)
        other = Actor("tenant-a", "other-operator", PERMISSIONS)
        with self.assertRaises(Denied):
            self.store.apply(other, "op1", "p1", ph)
        self.assertEqual(self.actual(), ((3, 0), 0))
        self.detail = "Approval is scoped to exact content/proposal/operator; another hash, proposal or operator cannot spend it."

    def test_ui_terminal_state(self):
        ph = self.prepare()
        reducer = UIReducer(self.store, ALICE, defect=self.defect)
        reducer.validated("p1", ph)
        receipt = self.store.apply(ALICE, "op1", "p1", ph)
        reducer.committed(receipt)
        reducer.interrupted()
        reducer.partial("late old generation")
        reducer.validated("p1", ph)
        self.assertEqual(reducer.state["phase"], "committed")
        self.assertFalse(reducer.state["can_approve"])
        self.assertEqual(reducer.state["receipt"], receipt)
        self.detail = "A confirmed commit survives late partial/validated/disconnect events in the same interaction."


class EvidenceResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.cases = []

    def record(self, test, status, detail):
        case_id = test._testMethodName.removeprefix("test_")
        existing = next((case for case in self.cases if case["id"] == case_id), None)
        if existing is not None:
            # A test and its cleanup can both fail: retain one truthful case result.
            existing["status"] = "failed" if "failed" in (status, existing["status"]) else status
            existing["detail"] += "; " + detail
            return
        self.cases.append({"id": case_id, "status": status, "detail": detail})

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, "passed", test.detail)

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, "failed", f"{err[0].__name__}: {err[1]}")

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, "failed", f"{err[0].__name__}: {err[1]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inject-defect", choices=DEFECTS)
    args = parser.parse_args()
    suite = unittest.TestSuite(AcceptanceCases("test_" + case_id, args.inject_defect)
                               for case_id in CASE_IDS)
    result = EvidenceResult()
    suite.run(result)
    evidence = {"schema_version": 1, "cases": result.cases}
    output = json.dumps(evidence, ensure_ascii=False, indent=2)
    destination = os.environ.get("AGUI_EVIDENCE_OUTPUT")
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(output + "\n", encoding="utf-8")
    print(output)
    return 0 if result.wasSuccessful() and len(result.cases) == len(CASE_IDS) else 1


if __name__ == "__main__":
    sys.exit(main())
