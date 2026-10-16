from concurrent.futures import ThreadPoolExecutor
import time

import pytest

from iip.models import Status
from iip.repository import Repository, LimitReached


def test_profile_watchlist_and_notes_persist(repository, real_profile):
    repository.save_many([real_profile])
    assert repository.toggle_watch(real_profile.id)
    repository.save_note(real_profile.id, "Check admission registration cut-off date.")
    reopened = Repository(repository.path)
    assert reopened.get(real_profile.id).name == real_profile.name
    assert real_profile.id in reopened.watched()
    assert "cut-off" in reopened.note(real_profile.id)
    assert len(reopened.audit(real_profile.id)) == 2


def test_review_has_audit_and_requires_metadata(repository, real_profile):
    repository.save_many([real_profile])
    with pytest.raises(ValueError):
        repository.review_evidence(real_profile.id, "E1", Status.VERIFIED, "", "")
    assert repository.get(real_profile.id).evidence[0].status == Status.UNVERIFIED
    repository.review_evidence(real_profile.id, "E1", Status.VERIFIED, "Analyst", "Matched institution and year against university extract.")
    assert repository.get(real_profile.id).evidence[0].status == Status.VERIFIED
    assert repository.audit(real_profile.id)[0]["action"] == "Evidence reviewed"


def test_demo_seed_is_idempotent(repository):
    repository.seed_demo()
    repository.seed_demo()
    assert len(repository.institutions()) == 6


def test_cache_expiry_and_clear(repository):
    repository.cache_set("result", {"value": 1}, 1)
    assert repository.cache_get("result") == {"value": 1}
    with repository.connect() as db:
        db.execute("UPDATE research_cache SET expires_at=?", (time.time()-1,))
    assert repository.cache_get("result") is None
    repository.clear_research_cache()
    assert repository.cache_get("result") is None


def test_concurrent_quota_reservations_are_atomic(repository):
    def reserve(_):
        try:
            return repository.reserve_request("Test", "research", 3)
        except LimitReached:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve, range(10)))
    assert sum(r is not None for r in results) == 3
    assert repository.usage()["requests"] == 3
    repository.cache_hit("Test")
    assert repository.usage()["requests"] == 3 and repository.usage()["cache_hits"] == 1
