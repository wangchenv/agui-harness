"""Offline service-desk example: one SQLite transaction boundary, not a framework.

Written for this repository, building on its reliability-audit experiment. A trusted
host authenticates callers and constructs Actor; never decode Actor from model/UI
JSON. External systems, tenant administration, permission revocation and approval
UX are outside this local example. No model or network client is used.
"""

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import sqlite3
import time
import uuid


class Denied(Exception):
    pass


class StaleEvidence(Exception):
    pass


class VersionConflict(Exception):
    pass


class ApprovalRequired(Exception):
    pass


class IdempotencyConflict(Exception):
    pass


class UnknownOutcome(Exception):
    """The caller did not receive acknowledgement; query/replay the same operation."""


@dataclass(frozen=True)
class Actor:
    tenant_id: str
    operator: str
    permissions: frozenset[str]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


class TicketStore:
    """All public business methods derive tenant scope from a host-issued Actor.

    Priority is integer 1..4 (1 is most urgent). Evidence is issued by this store,
    bound to the reading operator, expires after evidence_ttl seconds, and refers
    to an entity version. One operator approves and executes in this small example.
    """

    def __init__(self, path, *, clock=time.time, evidence_ttl=60, defect=None):
        self.clock = clock
        self.evidence_ttl = evidence_ttl
        self.defect = defect  # Test-only negative control, never set in deployment.
        self.db = sqlite3.connect(path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tickets (
              tenant TEXT NOT NULL, id TEXT NOT NULL,
              priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 4),
              version INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(tenant,id));
            CREATE TABLE IF NOT EXISTS evidence (
              tenant TEXT NOT NULL, id TEXT NOT NULL, operator TEXT NOT NULL,
              ticket_id TEXT NOT NULL, version INTEGER NOT NULL,
              priority INTEGER NOT NULL, expires_at REAL NOT NULL,
              PRIMARY KEY(tenant,id),
              FOREIGN KEY(tenant,ticket_id) REFERENCES tickets(tenant,id));
            CREATE TABLE IF NOT EXISTS proposals (
              tenant TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL,
              hash TEXT NOT NULL, PRIMARY KEY(tenant,id));
            CREATE TABLE IF NOT EXISTS approvals (
              tenant TEXT NOT NULL, proposal_id TEXT NOT NULL, hash TEXT NOT NULL,
              operator TEXT NOT NULL, PRIMARY KEY(tenant,proposal_id,hash,operator),
              FOREIGN KEY(tenant,proposal_id) REFERENCES proposals(tenant,id));
            CREATE TABLE IF NOT EXISTS operations (
              tenant TEXT NOT NULL, id TEXT NOT NULL, payload_hash TEXT NOT NULL,
              receipt TEXT NOT NULL, PRIMARY KEY(tenant,id));
        """)

    def close(self):
        self.db.close()

    @staticmethod
    def _permit(actor, action):
        if not isinstance(actor, Actor) or not actor.tenant_id or not actor.operator:
            raise Denied("host-issued actor required")
        if "ticket:" + action not in actor.permissions:
            raise Denied("host did not authorize this action")

    @contextmanager
    def _transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def seed_ticket(self, tenant_id, ticket_id, priority):
        """Administrative test/bootstrap function, never exposed as an agent tool."""
        self.db.execute("INSERT INTO tickets VALUES (?, ?, ?, 0)",
                        (tenant_id, ticket_id, priority))

    def _ticket(self, tenant, ticket_id):
        row = self.db.execute("SELECT * FROM tickets WHERE tenant=? AND id=?",
                              (tenant, ticket_id)).fetchone()
        if row is None:
            raise Denied("ticket unavailable in this tenant")
        return dict(row)

    def read_ticket(self, actor, ticket_id):
        self._permit(actor, "read")
        with self._transaction():
            ticket = self._ticket(actor.tenant_id, ticket_id)
            evidence_id = "ev-" + uuid.uuid4().hex
            expires_at = self.clock() + self.evidence_ttl
            self.db.execute("INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (actor.tenant_id, evidence_id, actor.operator, ticket_id,
                             ticket["version"], ticket["priority"], expires_at))
        return {"ticket": ticket, "evidence_id": evidence_id, "expires_at": expires_at}

    def _evidence(self, actor, evidence_id):
        row = self.db.execute(
            "SELECT * FROM evidence WHERE tenant=? AND id=? AND operator=?",
            (actor.tenant_id, evidence_id, actor.operator)).fetchone()
        if row is None:
            raise Denied("evidence unavailable for this actor")
        if self.clock() >= row["expires_at"]:
            raise StaleEvidence("evidence expired; read the ticket again")
        return row

    def propose(self, actor, proposal_id, evidence_id, priority):
        self._permit(actor, "propose")
        if type(priority) is not int or priority not in (1, 2, 3, 4):
            raise ValueError("priority must be an integer from 1 to 4")
        with self._transaction():
            evidence = self._evidence(actor, evidence_id)
            ticket = self._ticket(actor.tenant_id, evidence["ticket_id"])
            if ticket["version"] != evidence["version"]:
                raise StaleEvidence("evidence version changed; read again")
            body = {"tenant_id": actor.tenant_id, "proposal_id": proposal_id,
                    "ticket_id": ticket["id"], "expected_version": ticket["version"],
                    "priority_before": ticket["priority"], "priority_after": priority,
                    "evidence_id": evidence_id, "operator": actor.operator}
            proposal_hash = digest(body)
            self.db.execute("INSERT INTO proposals VALUES (?, ?, ?, ?)",
                            (actor.tenant_id, proposal_id, canonical(body), proposal_hash))
        return {"proposal": body, "proposal_hash": proposal_hash}

    def _proposal(self, actor, proposal_id, expected_hash):
        row = self.db.execute("SELECT * FROM proposals WHERE tenant=? AND id=?",
                              (actor.tenant_id, proposal_id)).fetchone()
        if row is None:
            raise Denied("proposal unavailable in this tenant")
        body = json.loads(row["payload"])
        if digest(body) != row["hash"] or expected_hash != row["hash"]:
            raise ApprovalRequired("proposal differs from reviewed content")
        if body["operator"] != actor.operator:
            raise Denied("proposal belongs to another operator")
        return body

    def preview(self, actor, proposal_id, expected_hash):
        self._permit(actor, "read")
        return self._proposal(actor, proposal_id, expected_hash)

    def approve(self, actor, proposal_id, expected_hash):
        self._permit(actor, "approve")
        with self._transaction():
            self._proposal(actor, proposal_id, expected_hash)
            self.db.execute("INSERT OR IGNORE INTO approvals VALUES (?, ?, ?, ?)",
                            (actor.tenant_id, proposal_id, expected_hash, actor.operator))

    def receipt(self, actor, operation_id):
        self._permit(actor, "read")
        row = self.db.execute("SELECT receipt FROM operations WHERE tenant=? AND id=?",
                              (actor.tenant_id, operation_id)).fetchone()
        return None if row is None else json.loads(row["receipt"])

    def apply(self, actor, operation_id, proposal_id, expected_hash, *, fault=None):
        """Persist entity update and receipt together; retry with the SAME operation ID.

        fault(stage) is only for acceptance probes. A post-commit exception becomes
        UnknownOutcome, never a claim that the write rolled back. Real external API
        integrations need their own idempotency and reconciliation; this transaction
        cannot cover them.
        """
        self._permit(actor, "apply")  # Authorization also precedes receipt replay.
        if not isinstance(operation_id, str) or not operation_id:
            raise ValueError("persistent operation_id required")
        command_hash = digest({"proposal_id": proposal_id, "hash": expected_hash,
                               "operator": actor.operator, "tenant": actor.tenant_id})
        with self._transaction():
            prior = self.db.execute("SELECT * FROM operations WHERE tenant=? AND id=?",
                                    (actor.tenant_id, operation_id)).fetchone()
            if prior and self.defect != "skip_idempotency_replay":
                if prior["payload_hash"] != command_hash:
                    raise IdempotencyConflict("operation ID reused with different content")
                return json.loads(prior["receipt"])
            body = self._proposal(actor, proposal_id, expected_hash)
            approved = self.db.execute(
                "SELECT 1 FROM approvals WHERE tenant=? AND proposal_id=? AND hash=? AND operator=?",
                (actor.tenant_id, proposal_id, expected_hash, actor.operator)).fetchone()
            if not approved:
                raise ApprovalRequired("this exact proposal has no host approval")
            ticket = self._ticket(actor.tenant_id, body["ticket_id"])
            if ticket["version"] != body["expected_version"]:
                raise VersionConflict("stale proposal; generate and approve a new preview")
            self._evidence(actor, body["evidence_id"])
            changed = self.db.execute(
                "UPDATE tickets SET priority=?, version=version+1 WHERE tenant=? AND id=? AND version=?",
                (body["priority_after"], actor.tenant_id, ticket["id"], ticket["version"]))
            if changed.rowcount != 1:
                raise VersionConflict("conditional write failed")
            if fault:
                fault("after_ticket_write")
            receipt = {"schema_version": 1, "tenant_id": actor.tenant_id,
                       "operation_id": operation_id, "proposal_id": proposal_id,
                       "proposal_hash": expected_hash, "operator": actor.operator,
                       "ticket_id": ticket["id"], "priority_before": ticket["priority"],
                       "priority_after": body["priority_after"],
                       "version": ticket["version"] + 1, "committed_at": self.clock()}
            self.db.execute("INSERT INTO operations VALUES (?, ?, ?, ?)",
                            (actor.tenant_id, operation_id, command_hash, canonical(receipt)))
        if fault:
            try:
                fault("after_commit")
            except Exception as error:
                raise UnknownOutcome("acknowledgement lost; query/replay " + operation_id) from error
        return receipt
