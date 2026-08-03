import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).parent / "leaderboard.db"


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    """Преобразовать sqlite3.Row в обычный словарь."""
    return {key: row[key] for key in row.keys()}


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Создать/открыть БД, включить WAL, создать таблицу если нет.
    Возвращает connection. Вызывается при старте приложения."""
    path = db_path or DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            model TEXT NOT NULL,
            scenario TEXT NOT NULL,
            defender TEXT NOT NULL,
            composite_score REAL NOT NULL DEFAULT 0.0,
            gate_passed INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'completed',
            timestamp TEXT NOT NULL,
            result_json TEXT
        )
        """
    )
    conn.commit()
    return conn


def save_run(
    conn: sqlite3.Connection,
    run_id: str,
    model: str,
    scenario: str,
    defender: str,
    composite_score: float,
    gate_passed: bool,
    status: str,
    timestamp: str,
    result_json: str | None = None,
) -> None:
    """Вставить или обновить запись о запуске."""
    conn.execute(
        """
        INSERT OR REPLACE INTO runs (
            run_id, model, scenario, defender, composite_score,
            gate_passed, status, timestamp, result_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            model,
            scenario,
            defender,
            composite_score,
            int(gate_passed),
            status,
            timestamp,
            result_json,
        ),
    )
    conn.commit()


def get_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    """Получить последние запуски для таблицы лидеров, отсортированные по timestamp DESC."""
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY timestamp DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_run(conn: sqlite3.Connection, run_id: str) -> dict[str, Any] | None:
    """Получить один запуск по run_id."""
    row = conn.execute(
        "SELECT * FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    return _row_to_dict(row) if row is not None else None
