from unittest.mock import Mock

import chromadb
import pytest

import seasons
from vectordb import VectorDBManager, SchemaMismatchError, build_where


@pytest.fixture
def manager(tmp_path, hash_ef):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    return VectorDBManager(client=client, embedding_function=hash_ef)


# --- where-clause builder ---

def test_build_where_empty():
    assert build_where() is None


def test_build_where_single_clause_not_wrapped():
    assert build_where(team=14469) == {"team": 14469}


def test_build_where_multiple_clauses_uses_and():
    where = build_where(team=14469, season=2022)
    assert where == {"$and": [{"team": 14469}, {"season": 2022}]}


def test_build_where_skips_none_values():
    assert build_where(team=14469, season=None) == {"team": 14469}


# --- upsert / cache behavior ---

def test_upsert_returns_false_on_empty_payload(manager):
    assert manager.upsert_team_data({}, season=2022, region="All") is False


def test_upsert_chunk_count_matches_processor(manager, payload_14469_2022):
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    assert manager.collection.count() == 40


def test_is_team_in_db_false_before_upsert(manager):
    assert manager.is_team_in_db(14469, 2022) is False


def test_is_team_in_db_true_after_upsert(manager, payload_14469_2022):
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    assert manager.is_team_in_db(14469, 2022) is True


def test_is_team_in_db_discriminates_season(manager, payload_14469_2022):
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    assert manager.is_team_in_db(14469, 2025) is False


def test_ids_do_not_collide_across_seasons(manager, payload_14469_2022, payload_14469_2025):
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    n_2022 = manager.collection.count()

    manager.upsert_team_data(payload_14469_2025, season=2025, region="All")
    n_2025_total = manager.collection.count()

    still_2022 = manager.collection.get(where=build_where(team=14469, season=2022))
    assert len(still_2022["ids"]) == n_2022
    assert n_2025_total > n_2022  # both seasons coexist, nothing overwritten


def test_reupsert_same_season_is_idempotent(manager, payload_14469_2022):
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    n1 = manager.collection.count()
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    n2 = manager.collection.count()
    assert n1 == n2


def test_reupsert_smaller_payload_removes_stale_chunks(manager, payload_14469_2022):
    import copy
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    full_count = manager.collection.count()

    shrunk = copy.deepcopy(payload_14469_2022)
    shrunk["matches"] = shrunk["matches"][:5]
    manager.upsert_team_data(shrunk, season=2022, region="All")

    assert manager.collection.count() < full_count


def test_get_or_load_team_fetches_once_then_caches(manager, payload_14469_2022):
    fetch_fn = Mock(return_value=payload_14469_2022)
    manager.get_or_load_team(14469, fetch_fn, season=2022, region="All")
    manager.get_or_load_team(14469, fetch_fn, season=2022, region="All")
    assert fetch_fn.call_count == 1


def test_get_or_load_team_returns_false_when_fetch_returns_none(manager):
    fetch_fn = Mock(return_value=None)
    assert manager.get_or_load_team(14469, fetch_fn, season=2022, region="All") is False


def test_current_season_cache_expires_after_ttl(manager, payload_14469_2025, monkeypatch):
    import config
    import time

    monkeypatch.setattr(config, "CACHE_TTL_HOURS", 1)
    manager.upsert_team_data(payload_14469_2025, season=seasons.CURRENT_SEASON, region="All")
    assert manager.is_team_in_db(14469, seasons.CURRENT_SEASON) is True

    real_time = time.time
    monkeypatch.setattr(time, "time", lambda: real_time() + 3 * 3600)
    assert manager.is_team_in_db(14469, seasons.CURRENT_SEASON) is False


def test_all_metadata_values_are_chroma_scalars(manager, payload_14469_2022):
    manager.upsert_team_data(payload_14469_2022, season=2022, region="All")
    results = manager.collection.get(include=["metadatas"])
    for meta in results["metadatas"]:
        for key, value in meta.items():
            assert value is not None
            assert isinstance(value, (str, int, float, bool))


def test_schema_mismatch_raises(tmp_path, hash_ef):
    client = chromadb.PersistentClient(path=str(tmp_path / "chroma"))
    client.create_collection(name="ftc_team_data", embedding_function=hash_ef, metadata={"schema_version": 1})
    with pytest.raises(SchemaMismatchError):
        VectorDBManager(client=client, embedding_function=hash_ef)
