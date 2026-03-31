"""互換シム - ops.approval_queue へ移行"""
from ops.approval_queue import (
    approval_queue_path,
    load_existing_approval_fingerprints,
    append_approval_queue_entry,
)
