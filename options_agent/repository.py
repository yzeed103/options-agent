"""SQLite-backed persistence for contracts.

Replaces the previous read-modify-write JSON file, which corrupted data under
concurrent gunicorn workers. WAL mode plus per-operation connections make this
safe across threads and processes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from .errors import NotFoundError
from .models import Contract, OptionType, Side

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT    NOT NULL,
    type            TEXT    NOT NULL CHECK (type IN ('call', 'put')),
    side            TEXT    NOT NULL CHECK (side IN ('long', 'short')),
    strike          REAL    NOT NULL CHECK (strike > 0),
    entry_premium   REAL    NOT NULL CHECK (entry_premium > 0),
    current_premium REAL    NOT NULL CHECK (current_premium > 0),
    qty             INTEGER NOT NULL CHECK (qty > 0),
    expiry          TEXT    NOT NULL,
    added_at        TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_contracts_symbol ON contracts (symbol);
"""


def _parse_datetime(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return datetime.now(timezone.utc)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _row_to_contract(row: sqlite3.Row) -> Contract:
    return Contract(
        id=row["id"],
        symbol=row["symbol"],
        type=OptionType(row["type"]),
        side=Side(row["side"]),
        strike=row["strike"],
        entry_premium=row["entry_premium"],
        current_premium=row["current_premium"],
        qty=row["qty"],
        expiry=date.fromisoformat(row["expiry"]),
        added_at=_parse_datetime(row["added_at"]),
    )


class ContractRepository:
    """Thread-safe repository. A connection is opened per operation."""

    def __init__(self, database_path: Path | str, *, timeout: float = 10.0) -> None:
        self._path = Path(database_path)
        self._timeout = timeout

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._path.parent and str(self._path.parent) not in ("", "."):
            self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._path, timeout=self._timeout)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("PRAGMA foreign_keys=ON")
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def list_all(self) -> list[Contract]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM contracts ORDER BY id").fetchall()
        return [_row_to_contract(row) for row in rows]

    def get(self, contract_id: int) -> Contract:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"لا يوجد عقد بالرقم {contract_id}")
        return _row_to_contract(row)

    def add(self, contract: Contract) -> Contract:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO contracts
                    (symbol, type, side, strike, entry_premium, current_premium, qty, expiry, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    contract.symbol,
                    contract.type.value,
                    contract.side.value,
                    contract.strike,
                    contract.entry_premium,
                    contract.current_premium,
                    contract.qty,
                    contract.expiry.isoformat(),
                    contract.added_at.isoformat(),
                ),
            )
        return contract.with_id(int(cursor.lastrowid))

    def add_many(self, contracts: Sequence[Contract]) -> int:
        if not contracts:
            return 0
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO contracts
                    (symbol, type, side, strike, entry_premium, current_premium, qty, expiry, added_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        c.symbol,
                        c.type.value,
                        c.side.value,
                        c.strike,
                        c.entry_premium,
                        c.current_premium,
                        c.qty,
                        c.expiry.isoformat(),
                        c.added_at.isoformat(),
                    )
                    for c in contracts
                ],
            )
        return len(contracts)

    def delete(self, contract_id: int) -> Contract:
        """Delete and return the removed contract. Raises NotFoundError."""
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM contracts WHERE id = ?", (contract_id,)).fetchone()
            if row is None:
                raise NotFoundError(f"لا يوجد عقد بالرقم {contract_id}")
            conn.execute("DELETE FROM contracts WHERE id = ?", (contract_id,))
        return _row_to_contract(row)

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM contracts").fetchone()[0])

    def migrate_legacy_json(self, json_path: Path | str) -> int:
        """One-shot import of the old contracts.json file. Idempotent: the
        import is skipped when the database already holds rows."""
        path = Path(json_path)
        if not path.exists() or self.count() > 0:
            return 0
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("legacy file %s is unreadable; skipping migration", path)
            return 0
        if not isinstance(raw, list):
            return 0

        migrated: list[Contract] = []
        for entry in raw:
            try:
                migrated.append(Contract.from_payload(entry))
            except Exception:  # noqa: BLE001 - a bad legacy row must not block startup
                logger.warning("skipping invalid legacy contract: %r", entry)
        imported = self.add_many(migrated)
        if imported:
            backup = path.with_suffix(path.suffix + ".migrated")
            try:
                path.replace(backup)
            except OSError:
                logger.warning("could not rename %s after migration", path)
            logger.info("migrated %d contracts from %s", imported, path)
        return imported
