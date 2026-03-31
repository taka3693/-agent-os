"""互換シム - ops.approval_queue へ移行"""
from ops.approval_queue import (
    load_approval_queue,
    list_pending_approvals,
    find_pending_approval_by_fingerprint,
)
