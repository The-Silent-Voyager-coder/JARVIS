"""Workspace models tests."""

from pathlib import Path

import pytest

from greatsage.exceptions import WorkspaceValidationError
from greatsage.workspace.models import ProjectType, WorkspaceInfo


def test_workspace_info_validate() -> None:
    info = WorkspaceInfo(root=Path("tmp/ws"))
    with pytest.raises(WorkspaceValidationError, match="absolute"):
        info.validate()

    info2 = WorkspaceInfo(root=Path("C:/tmp/ws").resolve())
    info2.validate()

    # to_dict roundtrip
    d = info2.to_dict()
    assert d["project_type"] == ProjectType.UNKNOWN.value
    assert "scanned_at" in d
