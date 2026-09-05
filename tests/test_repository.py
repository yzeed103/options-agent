from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from options_agent.errors import NotFoundError
from options_agent.models import OptionType

from .conftest import make_contract


def test_add_assigns_id_and_persists(repository):
    stored = repository.add(make_contract())
    assert stored.id is not None
    assert [c.id for c in repository.list_all()] == [stored.id]


def test_round_trip_preserves_types(repository):
    stored = repository.add(make_contract(type=OptionType.PUT))
    loaded = repository.get(stored.id)
    assert loaded.type is OptionType.PUT
    assert loaded.expiry == stored.expiry
    assert loaded.added_at.tzinfo is not None


def test_delete_returns_removed_contract(repository):
    stored = repository.add(make_contract(symbol="TSLA"))
    removed = repository.delete(stored.id)
    assert removed.symbol == "TSLA"
    assert repository.list_all() == []


def test_delete_missing_raises_not_found(repository):
    with pytest.raises(NotFoundError):
        repository.delete(999)


def test_get_missing_raises_not_found(repository):
    with pytest.raises(NotFoundError):
        repository.get(999)


def test_concurrent_writes_do_not_lose_rows(repository):
    """The JSON implementation lost writes here; SQLite must not."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda i: repository.add(make_contract(strike=100 + i)), range(40)))
    assert repository.count() == 40


def test_legacy_migration_imports_and_renames(repository, settings):
    legacy = settings.legacy_data_file
    legacy.write_text(
        json.dumps(
            [
                {
                    "symbol": "AAPL",
                    "type": "call",
                    "side": "long",
                    "strike": 200,
                    "entry_premium": 5,
                    "current_premium": 6,
                    "qty": 1,
                    "expiry": "2030-01-17",
                },
                {"symbol": "BROKEN"},
            ]
        ),
        encoding="utf-8",
    )
    assert repository.migrate_legacy_json(legacy) == 1
    assert repository.count() == 1
    assert not legacy.exists()
    assert legacy.with_suffix(legacy.suffix + ".migrated").exists()


def test_migration_is_skipped_when_db_has_rows(repository, settings):
    repository.add(make_contract())
    settings.legacy_data_file.write_text("[]", encoding="utf-8")
    assert repository.migrate_legacy_json(settings.legacy_data_file) == 0


def test_migration_tolerates_corrupt_file(repository, settings):
    settings.legacy_data_file.write_text("{ not json", encoding="utf-8")
    assert repository.migrate_legacy_json(settings.legacy_data_file) == 0
