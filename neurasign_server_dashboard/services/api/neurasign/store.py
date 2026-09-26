"""Transactional JSON documents: SQLite locally, Firestore on Google Cloud.

No client can query either store directly. Authorization belongs to the API.
"""
from datetime import datetime, timezone
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3


def _json_value(value):
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


class Documents:
    def __init__(self, store, connection=None):
        self.store, self.connection = store, connection
        self.pending = {}

    def get(self, path):
        if path in self.pending:
            return self.pending[path]
        return self.store._get(path, self.connection)

    def put(self, path, value):
        self.pending[path] = value

    def delete(self, path):
        self.pending[path] = None


class SQLiteStore:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS documents (path TEXT PRIMARY KEY, collection TEXT NOT NULL, body TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS document_collection ON documents(collection)')

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=15)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _get(self, path, connection):
        row = connection.execute('SELECT body FROM documents WHERE path=?', (path,)).fetchone()
        return json.loads(row[0]) if row else None

    def get(self, path):
        with self.connect() as db:
            return self._get(path, db)

    def get_many(self, paths):
        with self.connect() as db:
            return {path: self._get(path, db) for path in paths}

    def list(self, collection, limit=100, order=None, filters=None):
        with self.connect() as db:
            rows = [json.loads(row[0]) for row in db.execute('SELECT body FROM documents WHERE collection=?', (collection,))]
        if filters:
            rows = [row for row in rows if all(row.get(key) == value for key, value in filters.items())]
        if order:
            rows.sort(key=lambda item: item.get(order, 0), reverse=True)
        return rows[:limit]

    def atomic(self, function):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            documents = Documents(self, db)
            result = function(documents)
            for path, value in documents.pending.items():
                if value is None:
                    db.execute('DELETE FROM documents WHERE path=?', (path,))
                else:
                    db.execute('INSERT OR REPLACE INTO documents VALUES (?, ?, ?)', (path, path.rsplit('/', 1)[0], json.dumps(value, allow_nan=False)))
            return result


class FirestoreStore:
    def __init__(self, project, database='(default)'):
        from google.cloud import firestore
        self.firestore = firestore
        self.client = firestore.Client(project=project, database=database)

    def _get(self, path, connection):
        result = self.client.document(path).get(transaction=connection)
        return _json_value(result.to_dict()) if result.exists else None

    def get(self, path):
        return self._get(path, None)

    def get_many(self, paths):
        if not paths:
            return {}
        return {document.reference.path: _json_value(document.to_dict()) if document.exists else None
                for document in self.client.get_all([self.client.document(path) for path in paths])}

    def list(self, collection, limit=100, order=None, filters=None):
        query = self.client.collection(collection)
        if filters:
            from google.cloud.firestore_v1.base_query import FieldFilter
            for key, value in filters.items():
                query = query.where(filter=FieldFilter(key, '==', value))
        if order:
            query = query.order_by(order, direction=self.firestore.Query.DESCENDING)
        return [_json_value(document.to_dict()) for document in query.limit(limit).stream()]

    def atomic(self, function):
        @self.firestore.transactional
        def commit(transaction):
            documents = Documents(self, transaction)
            result = function(documents)
            # Buffer writes so all Firestore reads precede writes.
            for path, value in documents.pending.items():
                reference = self.client.document(path)
                if value is None:
                    transaction.delete(reference)
                else:
                    value = dict(value)
                    if value.get('expires_at') is not None:
                        value['expires_at'] = datetime.fromtimestamp(value['expires_at'], timezone.utc)
                    transaction.set(reference, value)
            return result
        return commit(self.client.transaction(max_attempts=5))
