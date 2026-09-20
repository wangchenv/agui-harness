from concurrent.futures import ThreadPoolExecutor
import importlib.util
import os
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest

from agui_runtime import Actor, Rejected, Runtime

spec = importlib.util.spec_from_file_location('runtime_domains', Path(__file__).resolve().parents[1] / 'examples/runtime-domains/domain.py')
domain = importlib.util.module_from_spec(spec)
spec.loader.exec_module(domain)


class DomainReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'app.sqlite'
        with sqlite3.connect(self.path) as db: domain.create_domain_tables(db)
        self.actor = Actor('team', 'user')
        self.runtime = Runtime(self.path, domain.actions(allow_overlap=os.environ.get('AGUI_TEST_DEFECT') == 'allow_overlap'), authorize=lambda *args: True)

    def prepare(self, action, payload):
        p = self.runtime.propose(self.actor, action, payload)
        self.runtime.approve(self.actor, p['operation_id'], p['proposal_hash'])
        return p

    def apply(self, p):
        return self.runtime.execute(self.actor, p['operation_id'], p['proposal_hash'])

    def test_shared_runtime_commits_two_different_domains(self):
        stock = self.prepare('inventory.take', {'sku': 'laptop', 'quantity': 2, 'expected_version': 0})
        room = self.prepare('room.reserve', {'room': 'room-1', 'start': 10000, 'end': 13600})
        for p in [stock, room]: self.assertEqual(self.apply(p), self.apply(p))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT quantity,version FROM inventory').fetchone(), (3, 1))
            self.assertEqual(db.execute('SELECT count(*) FROM reservations').fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT count(*) FROM agui_audit WHERE event='committed'").fetchone()[0], 2)

    def test_stock_conflict_does_not_oversell(self):
        proposals = [self.prepare('inventory.take', {'sku': 'laptop', 'quantity': 4, 'expected_version': 0}) for _ in range(2)]
        self.apply(proposals[0])
        with self.assertRaises(Rejected): self.apply(proposals[1])
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT quantity,version FROM inventory').fetchone(), (1, 1))

    def test_parallel_overlap_rejected_but_adjacent_allowed(self):
        proposals = [self.prepare('room.reserve', {'room': 'room-1', 'start': 10000, 'end': 13600}) for _ in range(2)]
        barrier = threading.Barrier(2)
        def worker(p):
            barrier.wait(timeout=10)
            try: self.apply(p); return 'committed'
            except Rejected: return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(worker, proposals)), ['committed', 'rejected'])
        self.apply(self.prepare('room.reserve', {'room': 'room-1', 'start': 13600, 'end': 17200}))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM reservations').fetchone()[0], 2)


if __name__ == '__main__': unittest.main()
