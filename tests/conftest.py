import pytest
from pathlib import Path
from uuid import uuid4

from iip.models import Evidence, Institution
from iip.repository import Repository
from iip.config import today


@pytest.fixture
def tmp_path():
    # Keep generated test data in the project, including in restricted environments.
    path = Path(__file__).resolve().parent.parent / "artifacts" / "tests" / uuid4().hex
    path.mkdir(parents=True)
    return path


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "test.db")


@pytest.fixture
def real_profile():
    evidence = Evidence(id="E1", title="University registration report", source_type="University", observed_on=today(), period="2025-26", excerpt="Example supplied report, unverified.")
    return Institution(id="real-test", name="Test Institution", city="Hyderabad", state="Telangana", identity_evidence_id="E1", evidence=[evidence])
