"""Serialized Worker Queue for Request-Level Isolation.

Enforces strict transaction serialization per model engine to guarantee
that concurrent requests never observe each other's adapter state or cached activations.
"""
from __future__ import annotations

import threading
from typing import Any, Callable, TypeVar
import time

T = TypeVar("T")


class SerializedWorkerQueue:
    """Provides mutually exclusive execution per model worker to prevent cross-request leakage."""

    def __init__(self, worker_id: str = "default_worker") -> None:
        self.worker_id = worker_id
        self._lock = threading.RLock()
        self._active_transaction_id: str | None = None
        self._total_executed = 0

    def execute_transaction(self, request_id: str, action: Callable[[], T]) -> T:
        """Executes the given action under exclusive lock, associating it with request_id."""
        with self._lock:
            self._active_transaction_id = request_id
            try:
                res = action()
                self._total_executed += 1
                return res
            finally:
                self._active_transaction_id = None

    @property
    def is_busy(self) -> bool:
        return self._active_transaction_id is not None

    @property
    def active_request_id(self) -> str | None:
        return self._active_transaction_id

    @property
    def total_transactions_executed(self) -> int:
        return self._total_executed
