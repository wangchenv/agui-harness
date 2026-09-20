# Local execution module

`agui_runtime` is an opt-in Python standard-library module for **one SQLite database**. It provides immutable proposals, exact-content approval, stable operation identity, expiry/revocation, atomic domain writes plus receipts, and receipt replay after reconnection or process restart.

It does not implement authentication, a distributed transaction, an external API outbox, a model client, or a production service. Keep an existing application's equivalent mechanisms when they are already sound.

## Integrate

Vendor the `agui_runtime/` directory into the target project, keep its version in your dependency inventory, and include it in `contract.source_paths`. Alternatively, import it from a pinned complete plugin checkout; include that dependency in your reviewed build and evidence process. Merely mentioning a version does not snapshot external code.

The host supplies:

- `Actor(tenant_id, subject_id)` obtained from its authenticated session, never from model output or an untrusted request body.
- `authorize(actor, action_name, phase) -> bool`, called on propose, approve, execute (including replay), read and revoke. It must check current permissions and session revocation. Returning anything other than `True` denies access.
- An allowlisted `Action(version, validate, apply)`. `validate(payload)` returns the normalized object to display and approve. `apply(connection, actor, payload)` checks **current business preconditions**, modifies domain tables using that connection, and returns a JSON object.

```python
from agui_runtime import Action, Actor, Runtime

# validate_quantity, take_stock, and authorize are application-owned functions.
runtime = Runtime(
    "application.sqlite",
    {"inventory.take": Action("1", validate_quantity, take_stock)},
    authorize=authorize,
)
actor = Actor(authenticated_tenant, authenticated_subject)
proposal = runtime.propose(actor, "inventory.take", {
    "sku": "laptop", "quantity": 2, "expected_version": 0,
})
# Display the returned payload and expiry. Only after the user's actual approval:
runtime.approve(actor, proposal["operation_id"], proposal["proposal_hash"])
receipt = runtime.execute(actor, proposal["operation_id"], proposal["proposal_hash"])
```

Do not make `approve` available as an unconstrained model tool. The host is responsible for verifying the real confirmation event, CSRF/Origin, and the allowed intent. This version binds a proposal to its creating subject; a different-person approval workflow requires a separate policy/implementation, not a forged Actor.

The operation ID is created by `propose` and remains fixed through approval, submission, lookup and replay. A second proposal is a new intent; domain preconditions must prevent conflicting effects across distinct proposals.

## State and failure semantics

`proposed → approved → committed` is the success path. Uncommitted operations can become `expired` or `revoked`. A handler's explicit `Rejected` rolls back its domain changes and records `failed`. Unexpected exceptions roll back the whole transaction, leaving the original operation safely retryable. A response error after commit does not undo a committed operation: query `read(actor, operation_id)` or replay the same operation.

- Receipt replay still requires current authorization and the original proposal hash; it survives proposal expiry after commit.
- `read` finalizes expired uncommitted operations. Clock rollback cannot revive a stored terminal state.
- Handlers with a changed `Action.version` reject old approved proposals. Maintain this version when semantics change; it is not an automatic code hash.
- A write lock serializes local transactions. Inventory uses a version/quantity predicate; room booking uses a half-open interval overlap predicate inside that lock.
- Approval is recorded with the exact proposal hash. Domain update, receipt and commit audit event use the same transaction.

Handlers are trusted code: **never call commit/rollback, start another write connection, perform external writes, or retain the supplied connection**. This is an API contract, not an adversarial Python sandbox. Long-running work and model requests belong outside the transaction.

## Verify and reuse

[Two domain adapters](../examples/runtime-domains/domain.py) share this module. [Runtime tests](../tests/test_runtime.py) and [cross-domain tests](../tests/test_runtime_domains.py) independently inspect SQLite state, including concurrency and lost acknowledgements.

```sh
python -m unittest discover -s tests -p 'test_runtime*.py' -v
```

The example's `allow_overlap` switch is a negative-control fixture and must not be exposed to users. The reusable runtime itself has no defect switch. Its `fault` callback is for trusted failure-injection tests only.

Schema migration, backup/disaster recovery, database encryption, a durable event bus, and multi-instance production sizing remain application responsibilities. Local tests do not establish power-loss recovery or a production SLO.
