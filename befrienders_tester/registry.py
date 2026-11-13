"""Persistent local registry of beneficiary codes used by earlier batches.

Only normalised codes are stored (never names), in a SQLite file next to the app.
A new roster row whose code is already registered is rejected as a duplicate.
"""
from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from .reference_core import normalize_code

_SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    code_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS codes (
    code TEXT PRIMARY KEY,
    batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE
);
"""


class DuplicateCodes(ValueError):
    def __init__(self, codes):
        self.codes = list(codes)
        super().__init__('أكواد مسجلة مسبقًا: ' + '، '.join(self.codes[:5]))


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as conn, conn:
            conn.executescript(_SCHEMA)

    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.execute('PRAGMA foreign_keys=ON')
        return conn

    @staticmethod
    def _clean(codes):
        return list(dict.fromkeys(normalize_code(c) for c in codes if str(c).strip()))

    def known(self, codes) -> dict:
        """{code: (batch_id, created_at)} for codes that are already registered."""
        codes = self._clean(codes)
        found = {}
        with closing(self._connect()) as conn:
            for i in range(0, len(codes), 500):
                chunk = codes[i:i + 500]
                marks = ','.join('?' * len(chunk))
                for code, batch_id, created in conn.execute(
                        f'SELECT c.code, b.id, b.created_at FROM codes c JOIN batches b ON b.id=c.batch_id '
                        f'WHERE c.code IN ({marks})', chunk):
                    found[code] = (batch_id, created)
        return found

    def register(self, codes, note: str = '') -> int:
        """Register a batch atomically; refuses if any code is already registered."""
        codes = self._clean(codes)
        if not codes:
            raise ValueError('لا توجد أكواد للتسجيل')
        clash = self.known(codes)
        if clash:
            raise DuplicateCodes(clash)
        with closing(self._connect()) as conn, conn:
            cursor = conn.execute('INSERT INTO batches(created_at, note, code_count) VALUES (?,?,?)',
                                  (datetime.now().isoformat(timespec='seconds'), note, len(codes)))
            batch_id = cursor.lastrowid
            conn.executemany('INSERT INTO codes(code, batch_id) VALUES (?,?)', [(c, batch_id) for c in codes])
        return batch_id

    def batches(self) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute('SELECT id, created_at, code_count, note FROM batches ORDER BY id DESC').fetchall()
        return [{'id': r[0], 'created_at': r[1], 'code_count': r[2], 'note': r[3]} for r in rows]

    def total_codes(self) -> int:
        with closing(self._connect()) as conn:
            return conn.execute('SELECT COUNT(*) FROM codes').fetchone()[0]

    def delete_batch(self, batch_id: int):
        with closing(self._connect()) as conn, conn:
            conn.execute('DELETE FROM batches WHERE id=?', (batch_id,))

    def clear(self):
        with closing(self._connect()) as conn, conn:
            conn.execute('DELETE FROM codes')
            conn.execute('DELETE FROM batches')


def filter_registered(people, registry: Registry):
    """Split a roster into (new people, errors) — rows already registered are rejected."""
    known = registry.known([p.code for p in people])
    accepted, errors = [], []
    for person in people:
        hit = known.get(normalize_code(person.code))
        if hit:
            errors.append(f'صف {person.row}: الكود «{person.code}» مكرر — مسجل مسبقًا في الدفعة #{hit[0]} ({hit[1][:10]})')
        else:
            accepted.append(person)
    return accepted, errors
