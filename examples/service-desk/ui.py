"""One interaction's host-side UI reducer; create a new reducer for a new flow.

Partial model output is never a commit receipt. Terminal state survives late frames.
"""

from domain import canonical


class ReceiptRequired(Exception):
    pass


class UIReducer:
    def __init__(self, store, actor, *, defect=None):
        self.store = store
        self.actor = actor
        self.defect = defect
        self.state = {"phase": "idle", "can_approve": False, "receipt": None}

    def partial(self, text):
        if self.state["phase"] in ("committed", "interrupted"):
            return
        self.state = {"phase": "partial", "text": str(text)[:1000],
                      "can_approve": False, "receipt": None}

    def validated(self, proposal_id, proposal_hash):
        if self.state["phase"] in ("committed", "interrupted"):
            return
        preview = self.store.preview(self.actor, proposal_id, proposal_hash)
        self.state = {"phase": "validated", "proposal": preview,
                      "proposal_hash": proposal_hash,
                      "can_approve": "ticket:approve" in self.actor.permissions, "receipt": None}

    def committed(self, receipt):
        # Deliberately vulnerable mode solely for the adapter's negative control.
        if self.defect == "allow_unreceipted_commit" and receipt is None:
            self.state.update(phase="committed", can_approve=False)
            return
        if not isinstance(receipt, dict) or self.state["phase"] != "validated":
            raise ReceiptRequired("validated preview and persistent receipt required")
        saved = self.store.receipt(self.actor, receipt.get("operation_id", ""))
        if saved is None or canonical(saved) != canonical(receipt):
            raise ReceiptRequired("receipt does not match the trusted operation store")
        if (receipt["proposal_id"] != self.state["proposal"]["proposal_id"]
                or receipt["proposal_hash"] != self.state["proposal_hash"]):
            raise ReceiptRequired("receipt belongs to a different preview")
        self.state.update(phase="committed", can_approve=False, receipt=saved)

    def interrupted(self):
        if self.state["phase"] != "committed":
            self.state.update(phase="interrupted", can_approve=False, receipt=None)
