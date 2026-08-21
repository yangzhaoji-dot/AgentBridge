from pathlib import Path

import pytest

from local_connector.policy import approval_result, resolve_allowed_cwd


def test_cwd_must_stay_inside_allowed_root(tmp_path: Path) -> None:
    allowed = tmp_path / "allowed"
    inside = allowed / "project"
    outside = tmp_path / "outside"
    inside.mkdir(parents=True)
    outside.mkdir()

    assert resolve_allowed_cwd(str(inside), [allowed]) == inside.resolve()
    with pytest.raises(PermissionError):
        resolve_allowed_cwd(str(outside), [allowed])


def test_approval_result_uses_protocol_specific_values() -> None:
    assert approval_result("item/commandExecution/requestApproval", True) == {
        "decision": "accept"
    }
    assert approval_result("item/fileChange/requestApproval", False) == {
        "decision": "decline"
    }
    assert approval_result("execCommandApproval", True) == {
        "decision": "approved"
    }
