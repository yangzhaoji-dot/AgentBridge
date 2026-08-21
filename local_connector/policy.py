from __future__ import annotations

import os
from pathlib import Path
from typing import Any


V2_APPROVAL_METHODS = {
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
}
LEGACY_APPROVAL_METHODS = {"execCommandApproval", "applyPatchApproval"}


def resolve_allowed_cwd(candidate: str, allowed_roots: list[Path]) -> Path:
    target = Path(candidate).expanduser().resolve()
    if not target.is_dir():
        raise ValueError(f"working directory does not exist: {target}")

    for root in allowed_roots:
        resolved_root = root.expanduser().resolve()
        try:
            if os.path.commonpath([str(target), str(resolved_root)]) == str(resolved_root):
                return target
        except ValueError:
            # Different Windows drives do not have a common path.
            continue

    allowed = ", ".join(str(root) for root in allowed_roots)
    raise PermissionError(f"working directory is outside allowed roots: {allowed}")


def approval_result(method: str, approved: bool) -> dict[str, Any]:
    if method in V2_APPROVAL_METHODS:
        return {"decision": "accept" if approved else "decline"}
    if method in LEGACY_APPROVAL_METHODS:
        return {"decision": "approved" if approved else "denied"}
    raise ValueError(f"unsupported approval method: {method}")
