"""Atomic Rollback Guard for Adapter Switching Transactions."""
from __future__ import annotations

from typing import Optional, Callable, Any
import time


class RollbackError(Exception):
    """Raised when an atomic rollback operation fails."""
    pass


class AdapterTransactionGuard:
    """Context manager executing atomic adapter switching with automated rollback on failure."""

    def __init__(
        self,
        switch_func: Callable[[str], float],
        target_adapter_id: str,
        previous_adapter_id: Optional[str],
        on_error_quarantine: Optional[Callable[[str, str], None]] = None,
    ) -> None:
        self.switch_func = switch_func
        self.target_adapter_id = target_adapter_id
        self.previous_adapter_id = previous_adapter_id
        self.on_error_quarantine = on_error_quarantine
        self.switch_latency_ms: float = 0.0
        self.committed: bool = False

    def __enter__(self) -> AdapterTransactionGuard:
        try:
            self.switch_latency_ms = self.switch_func(self.target_adapter_id)
            return self
        except Exception as e:
            # Switch failed on entry; rollback immediately if there was a previous adapter
            self._execute_rollback(f"Switch to '{self.target_adapter_id}' failed: {e}")
            raise

    def commit(self) -> None:
        """Explicitly marks the transaction as successfully completed."""
        self.committed = True

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None or not self.committed:
            # Transaction aborted or exception raised during inference
            err_msg = str(exc_val) if exc_val else "Transaction aborted before commit"
            self._execute_rollback(err_msg)
        return False  # Re-raise exception

    def _execute_rollback(self, reason: str) -> None:
        if self.on_error_quarantine:
            self.on_error_quarantine(self.target_adapter_id, reason)

        if self.previous_adapter_id and self.previous_adapter_id != self.target_adapter_id:
            try:
                self.switch_func(self.previous_adapter_id)
            except Exception as rb_exc:
                raise RollbackError(f"Fatal: Failed to rollback to previous adapter '{self.previous_adapter_id}': {rb_exc}") from rb_exc
