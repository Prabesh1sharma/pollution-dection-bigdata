"""Thin Cassandra access layer (lazy connection so the API can start before Cassandra)."""
import os
import threading
from datetime import datetime, timezone

_session = None
_lock = threading.Lock()


def get_session():
    global _session
    with _lock:
        if _session is None:
            from cassandra.cluster import Cluster  # imported lazily
            from cassandra.query import dict_factory

            cluster = Cluster(
                os.getenv("CASSANDRA_HOSTS", "localhost").split(","),
                port=int(os.getenv("CASSANDRA_PORT", "9042")),
                connect_timeout=10,
            )
            session = cluster.connect(os.getenv("CASSANDRA_KEYSPACE", "airquality"))
            session.row_factory = dict_factory
            _session = session
        return _session


def reset_session():
    global _session
    with _lock:
        _session = None


def query(cql: str, params: tuple = ()) -> list[dict]:
    return list(get_session().execute(cql, params))


def iso(dt):
    """Cassandra returns naive UTC datetimes; emit RFC 3339 with a Z suffix."""
    if dt is None:
        return None
    if isinstance(dt, datetime):
        return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(dt)
