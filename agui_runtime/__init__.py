"""Opt-in local SQLite execution primitives; not a distributed workflow engine."""
from .sqlite import Action, Actor, Denied, Rejected, Runtime

__all__ = ['Action', 'Actor', 'Denied', 'Rejected', 'Runtime']
