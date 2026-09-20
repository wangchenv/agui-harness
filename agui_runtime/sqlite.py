"""Trusted handlers must use the supplied transaction and never perform remote writes.

Authentication, current authorization (including revoked sessions), business
preconditions, and handler version discipline are the integrating host's duty.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import time
from types import MappingProxyType
from typing import Callable, Mapping
import uuid


class Denied(Exception):
    pass


class Rejected(Exception):
    """An explicit domain rejection; its transaction is rolled back and made terminal."""


def canonical(value):
    encoded = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)
    if len(encoded.encode()) > 65536:
        raise ValueError('JSON exceeds 64 KiB')
    return encoded


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    subject_id: str

    def __post_init__(self):
        if not all(isinstance(v, str) and 0 < len(v) <= 256 for v in (self.tenant_id, self.subject_id)):
            raise ValueError('host tenant and subject required')


@dataclass(frozen=True)
class Action:
    version: str
    validate: Callable[[dict], dict]
    apply: Callable[[sqlite3.Connection, Actor, dict], dict]


class Runtime:
    def __init__(self, database, actions: Mapping[str, Action], *, authorize, clock=time.time):
        self.database = str(Path(database).resolve())
        self.actions = MappingProxyType(dict(actions))
        if not callable(authorize): raise ValueError('host authorization callback required')
        for name, action in self.actions.items():
            if not isinstance(name, str) or not name or not isinstance(action.version, str) or not action.version:
                raise ValueError('registered actions need stable names and versions')
        self.authorize, self.clock = authorize, clock
        with self._transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS agui_operations(
                id TEXT PRIMARY KEY, tenant TEXT NOT NULL, subject TEXT NOT NULL,
                action TEXT NOT NULL, action_version TEXT NOT NULL,
                payload TEXT NOT NULL, proposal_hash TEXT NOT NULL,
                created_at REAL NOT NULL, expires_at REAL NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('proposed','approved','committed','expired','revoked','failed')),
                receipt TEXT, error TEXT,
                CHECK((status='committed') = (receipt IS NOT NULL)))''')
            db.execute('''CREATE TABLE IF NOT EXISTS agui_audit(
                seq INTEGER PRIMARY KEY, operation_id TEXT NOT NULL REFERENCES agui_operations(id),
                event TEXT NOT NULL, at REAL NOT NULL, subject TEXT NOT NULL)''')

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.database, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _now(self):
        now = float(self.clock())
        if not math.isfinite(now): raise ValueError('finite clock required')
        return now

    def _permit(self, actor, action, phase):
        if not isinstance(actor, Actor) or self.authorize(actor, action, phase) is not True:
            raise Denied('current host authorization required')

    def _row(self, db, actor, operation_id, phase):
        if not isinstance(actor, Actor): raise Denied('host actor required')
        row = db.execute('SELECT * FROM agui_operations WHERE id=? AND tenant=? AND subject=?',
                         (operation_id, actor.tenant_id, actor.subject_id)).fetchone()
        if row is None: raise Denied('operation unavailable')
        self._permit(actor, row['action'], phase)
        return row

    def _audit(self, db, row, event):
        db.execute('INSERT INTO agui_audit(operation_id,event,at,subject) VALUES (?,?,?,?)',
                   (row['id'], event, self._now(), row['subject']))

    def _state(self, db, row):
        status = row['status']
        if status in {'proposed', 'approved'} and self._now() >= row['expires_at']:
            db.execute("UPDATE agui_operations SET status='expired' WHERE id=?", (row['id'],))
            self._audit(db, row, 'expired')
            status = 'expired'
        return status

    @staticmethod
    def _hash_matches(row, expected_hash):
        if row['proposal_hash'] != expected_hash:
            raise Rejected('proposal_hash_mismatch')

    @staticmethod
    def _view(row, status):
        return {'operation_id': row['id'], 'action': row['action'], 'action_version': row['action_version'],
                'payload': json.loads(row['payload']), 'proposal_hash': row['proposal_hash'],
                'expires_at': row['expires_at'], 'status': status,
                'receipt': json.loads(row['receipt']) if row['receipt'] else None, 'error': row['error']}

    def propose(self, actor, action_name, payload, *, ttl_s=300):
        self._permit(actor, action_name, 'propose')
        if action_name not in self.actions: raise Rejected('unknown_action')
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, (int, float)) or not 0 < ttl_s <= 3600:
            raise ValueError('proposal TTL must be in (0, 3600] seconds')
        if not isinstance(payload, dict): raise ValueError('object payload required')
        action = self.actions[action_name]
        normalized = action.validate(json.loads(canonical(payload)))
        if not isinstance(normalized, dict): raise ValueError('validator must return object payload')
        encoded = canonical(normalized)
        operation_id, now = 'op_' + uuid.uuid4().hex, self._now()
        body = {'operation_id': operation_id, 'tenant': actor.tenant_id, 'subject': actor.subject_id,
                'action': action_name, 'action_version': action.version, 'payload': json.loads(encoded),
                'expires_at': now + ttl_s}
        proposal_hash = hashlib.sha256(canonical(body).encode()).hexdigest()
        with self._transaction() as db:
            db.execute('INSERT INTO agui_operations VALUES (?,?,?,?,?,?,?,?,?,?,NULL,NULL)',
                       (operation_id, actor.tenant_id, actor.subject_id, action_name, action.version,
                        encoded, proposal_hash, now, now + ttl_s, 'proposed'))
            row = self._row(db, actor, operation_id, 'propose')
            self._audit(db, row, 'proposed')
            return self._view(row, 'proposed')

    def approve(self, actor, operation_id, expected_hash):
        error = None
        with self._transaction() as db:
            row = self._row(db, actor, operation_id, 'approve')
            self._hash_matches(row, expected_hash)
            status = self._state(db, row)
            if status not in {'proposed', 'approved'}:
                error = Rejected('operation_' + status)
            elif status == 'proposed':
                db.execute("UPDATE agui_operations SET status='approved' WHERE id=?", (operation_id,))
                self._audit(db, row, 'approved')
                status = 'approved'
        if error: raise error
        return self._view(row, status)

    def execute(self, actor, operation_id, expected_hash, *, fault=None):
        """fault is a trusted test hook. Exceptions after commit do not mean rollback.

        Query/replay this SAME operation after transport loss. No external I/O
        belongs inside Action.apply: only writes using the supplied connection.
        """
        error, receipt, newly_committed = None, None, False
        with self._transaction() as db:
            row = self._row(db, actor, operation_id, 'execute')
            self._hash_matches(row, expected_hash)
            status = self._state(db, row)
            if status == 'committed':
                receipt = json.loads(row['receipt'])
            elif status != 'approved':
                error = Rejected('operation_' + status)
            else:
                db.execute('SAVEPOINT business_mutation')
                try:
                    action = self.actions.get(row['action'])
                    if action is None or action.version != row['action_version']:
                        raise Rejected('handler_version_changed')
                    result = action.apply(db, actor, json.loads(row['payload']))
                    if not isinstance(result, dict): raise ValueError('handler result must be an object')
                    canonical(result)
                    if fault: fault('before_receipt')
                    receipt = {'schema_version': 1, 'operation_id': operation_id,
                               'proposal_hash': row['proposal_hash'], 'tenant_id': actor.tenant_id,
                               'subject_id': actor.subject_id, 'action': row['action'],
                               'committed_at': self._now(), 'result': result}
                    db.execute("UPDATE agui_operations SET status='committed',receipt=? WHERE id=?",
                               (canonical(receipt), operation_id))
                    self._audit(db, row, 'committed')
                    newly_committed = True
                except Rejected as exc:
                    db.execute('ROLLBACK TO business_mutation')
                    db.execute("UPDATE agui_operations SET status='failed',error=? WHERE id=?",
                               (str(exc)[:256], operation_id))
                    self._audit(db, row, 'failed')
                    error = exc
                finally:
                    db.execute('RELEASE business_mutation')
        if error: raise error
        if newly_committed and fault: fault('after_commit')
        return receipt

    def read(self, actor, operation_id):
        with self._transaction() as db:
            row = self._row(db, actor, operation_id, 'read')
            return self._view(row, self._state(db, row))

    def revoke(self, actor, operation_id, expected_hash):
        error = None
        with self._transaction() as db:
            row = self._row(db, actor, operation_id, 'revoke')
            self._hash_matches(row, expected_hash)
            status = self._state(db, row)
            if status in {'proposed', 'approved'}:
                db.execute("UPDATE agui_operations SET status='revoked' WHERE id=?", (operation_id,))
                self._audit(db, row, 'revoked'); status = 'revoked'
            elif status != 'revoked': error = Rejected('operation_' + status)
        if error: raise error
        return self._view(row, status)
