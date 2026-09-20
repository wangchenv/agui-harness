"""Business oracles use a separate SQLite connection, not runtime success text."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from agui_runtime import Action, Actor, Denied, Rejected, Runtime


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'app.sqlite'
        self.now = 1000.0
        self.denied = set()
        self.actor = Actor('tenant-a', 'alice')
        self.actions = {'increment': Action('1', lambda p: p, self.increment)}
        self.runtime = self.open()
        with sqlite3.connect(self.path) as db:
            db.execute('CREATE TABLE counters(tenant TEXT PRIMARY KEY, value INTEGER NOT NULL)')
            db.execute('INSERT INTO counters VALUES (?, ?)', ('tenant-a', 0))

    def open(self):
        return Runtime(self.path, self.actions, authorize=lambda actor, action, phase:
                       actor == self.actor and phase not in self.denied,
                       clock=lambda: self.now)

    @staticmethod
    def increment(db, actor, payload):
        changed = db.execute('UPDATE counters SET value=value+1 WHERE tenant=? AND value=?',
                             (actor.tenant_id, payload['expected']))
        if changed.rowcount != 1:
            raise Rejected('version_conflict')
        return {'value': payload['expected'] + 1}

    def prepare(self, approve=True):
        p = self.runtime.propose(self.actor, 'increment', {'expected': 0}, ttl_s=60)
        if approve:
            self.runtime.approve(self.actor, p['operation_id'], p['proposal_hash'])
        return p

    def execute(self, proposal, **kwargs):
        return self.runtime.execute(self.actor, proposal['operation_id'], proposal['proposal_hash'], **kwargs)

    def actual(self):
        with sqlite3.connect(self.path) as db:
            value = db.execute('SELECT value FROM counters WHERE tenant=?', ('tenant-a',)).fetchone()[0]
            receipts = db.execute("SELECT count(*) FROM agui_operations WHERE status='committed'").fetchone()[0]
        return value, receipts

    def test_exact_approval_and_replay(self):
        p = self.prepare(approve=False)
        with self.assertRaises(Rejected): self.execute(p)
        with self.assertRaises(Rejected): self.runtime.approve(self.actor, p['operation_id'], 'wrong')
        self.assertEqual(self.actual(), (0, 0))
        self.runtime.approve(self.actor, p['operation_id'], p['proposal_hash'])
        first = self.execute(p)
        self.now += 100
        self.assertEqual(self.execute(p), first)
        self.assertEqual(self.actual(), (1, 1))
        with self.assertRaises(Rejected):
            self.runtime.execute(self.actor, p['operation_id'], 'different')

    def test_permission_revoked_before_execution_and_replay(self):
        p = self.prepare()
        self.denied.add('execute')
        with self.assertRaises(Denied): self.execute(p)
        self.assertEqual(self.actual(), (0, 0))
        self.denied.clear(); self.execute(p); self.denied.add('execute')
        with self.assertRaises(Denied): self.execute(p)
        self.assertEqual(self.actual(), (1, 1))

    def test_tenant_and_owner_are_not_caller_payload(self):
        p = self.prepare()
        for actor in [Actor('tenant-b', 'alice'), Actor('tenant-a', 'bob')]:
            other = Runtime(self.path, self.actions, authorize=lambda *args: True, clock=lambda: self.now)
            with self.assertRaises(Denied): other.read(actor, p['operation_id'])
            with self.assertRaises(Denied): other.execute(actor, p['operation_id'], p['proposal_hash'])
        self.assertEqual(self.actual(), (0, 0))

    def test_expired_is_durable_and_cannot_resurrect(self):
        p = self.prepare()
        self.now += 60
        self.assertEqual(self.runtime.read(self.actor, p['operation_id'])['status'], 'expired')
        self.now -= 60
        with self.assertRaises(Rejected): self.execute(p)
        self.assertEqual(self.actual(), (0, 0))

    def test_expiry_checked_at_approve_and_commit(self):
        p = self.prepare(approve=False); self.now += 61
        with self.assertRaises(Rejected): self.runtime.approve(self.actor, p['operation_id'], p['proposal_hash'])
        self.assertEqual(self.runtime.read(self.actor, p['operation_id'])['status'], 'expired')
        self.now = 1000; q = self.prepare(); self.now += 61
        with self.assertRaises(Rejected): self.execute(q)
        self.assertEqual(self.runtime.read(self.actor, q['operation_id'])['status'], 'expired')

    def test_revoke_is_terminal(self):
        p = self.prepare()
        self.runtime.revoke(self.actor, p['operation_id'], p['proposal_hash'])
        with self.assertRaises(Rejected): self.execute(p)
        self.assertEqual(self.runtime.read(self.actor, p['operation_id'])['status'], 'revoked')
        self.assertEqual(self.actual(), (0, 0))

    def test_handler_version_change_requires_new_proposal(self):
        p = self.prepare(); self.actions['increment'] = Action('2', lambda p: p, self.increment)
        with self.assertRaises(Rejected): self.open().execute(self.actor, p['operation_id'], p['proposal_hash'])
        self.assertEqual(self.actual(), (0, 0))

    def test_rollback_business_write_and_receipt_together(self):
        p = self.prepare()
        def fail(stage):
            if stage == 'before_receipt': raise OSError('crash before receipt')
        with self.assertRaises(OSError): self.execute(p, fault=fail)
        self.assertEqual(self.actual(), (0, 0))
        self.assertEqual(self.runtime.read(self.actor, p['operation_id'])['status'], 'approved')
        self.execute(p); self.assertEqual(self.actual(), (1, 1))

    def test_lost_response_and_reopen(self):
        p = self.prepare()
        def lose(stage):
            if stage == 'after_commit': raise ConnectionError('lost response')
        with self.assertRaises(ConnectionError): self.execute(p, fault=lose)
        self.assertEqual(self.actual(), (1, 1))
        reopened = self.open()
        saved = reopened.read(self.actor, p['operation_id'])['receipt']
        self.assertEqual(reopened.execute(self.actor, p['operation_id'], p['proposal_hash']), saved)
        self.assertEqual(self.actual(), (1, 1))

    def test_concurrent_same_operation_commits_once(self):
        p = self.prepare(); barrier = threading.Barrier(4)
        def worker(_):
            runtime = self.open(); barrier.wait(timeout=10)
            return runtime.execute(self.actor, p['operation_id'], p['proposal_hash'])
        with ThreadPoolExecutor(max_workers=4) as pool: results = list(pool.map(worker, range(4)))
        self.assertTrue(all(r == results[0] for r in results))
        self.assertEqual(self.actual(), (1, 1))

    def test_domain_conflict_rolls_back_and_becomes_failed(self):
        p = self.prepare(); q = self.prepare(); self.execute(p)
        with self.assertRaises(Rejected): self.execute(q)
        self.assertEqual(self.runtime.read(self.actor, q['operation_id'])['status'], 'failed')
        self.assertEqual(self.actual(), (1, 1))

    def test_invalid_input_never_enters_ledger(self):
        for payload in [{'expected': float('nan')}, {'expected': 'x' * 70000}]:
            with self.assertRaises(ValueError): self.runtime.propose(self.actor, 'increment', payload)
        with self.assertRaises(Rejected): self.runtime.propose(self.actor, 'unknown', {})
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM agui_operations').fetchone()[0], 0)

    def test_mutating_returned_proposal_does_not_change_approved_payload(self):
        p = self.prepare(); p['payload']['expected'] = 999
        receipt = self.execute(p)
        self.assertEqual(receipt['result'], {'value': 1})
        self.assertEqual(self.actual(), (1, 1))

    def test_handler_rejection_after_mutation_rolls_back_and_records_failure(self):
        def reject_after_write(db, actor, payload):
            self.increment(db,actor,payload)
            raise Rejected('late_business_rejection')
        self.actions['increment']=Action('1',lambda p:p,reject_after_write)
        self.runtime=self.open(); p=self.prepare()
        with self.assertRaises(Rejected): self.execute(p)
        self.assertEqual(self.actual(),(0,0))
        self.assertEqual(self.runtime.read(self.actor,p['operation_id'])['status'],'failed')

    def test_invalid_handler_result_rolls_back_effect(self):
        def invalid_after_write(db,actor,payload):
            self.increment(db,actor,payload)
            return {'value':float('nan')}
        self.actions['increment']=Action('1',lambda p:p,invalid_after_write)
        self.runtime=self.open(); p=self.prepare()
        with self.assertRaises(ValueError): self.execute(p)
        self.assertEqual(self.actual(),(0,0))
        self.assertEqual(self.runtime.read(self.actor,p['operation_id'])['status'],'approved')


if __name__ == '__main__': unittest.main()
