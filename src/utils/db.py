"""
OenoBench — Database connection utilities.

Usage:
    from src.utils.db import get_pg, get_es, get_neo4j, get_redis
"""

import os
import threading
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


# Phase 2j (release_v1): per-thread psycopg2 connections. Replacing the
# previous `@lru_cache` (which returned the SAME connection across threads)
# fixes the race condition observed in the 24-in-flight worker dispatch:
# two threads concurrently flipping `conn.autocommit` would surface as
# `set_session cannot be used inside a transaction`, and concurrent
# transactions on a shared connection killed 4 of 5 strategies in the
# first 4 minutes of the original release_v1 build (commit 8d1d50a).
#
# psycopg2 connections are not thread-safe at the `Connection` level
# (cursors are independent but share the underlying socket). The standard
# fix is one connection per thread; thread-local storage gives single-
# threaded callers the same fast-path semantics they had before
# (one cached connection per thread), and the worker pool gets isolated
# connections without contention.
_pg_local = threading.local()


def get_pg():
    """Return a psycopg2 connection to PostgreSQL.

    Thread-local: each thread gets its own cached connection. The first
    call from a thread opens the connection; subsequent calls from the
    same thread return the same connection. Closed/broken connections
    are auto-reopened.
    """
    import psycopg2
    from psycopg2.extras import RealDictCursor

    conn = getattr(_pg_local, "conn", None)
    if conn is None or conn.closed:
        _pg_local.conn = psycopg2.connect(
            host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
            port=int(os.getenv("POSTGRES_PORT", 5432)),
            dbname=os.getenv("POSTGRES_DB", "winebench"),
            user=os.getenv("POSTGRES_USER", "winebench"),
            password=os.getenv("POSTGRES_PASSWORD"),
            cursor_factory=RealDictCursor,
        )
    return _pg_local.conn


@lru_cache()
def get_es():
    """Return an Elasticsearch client."""
    from elasticsearch import Elasticsearch

    return Elasticsearch(
        hosts=[f"http://{os.getenv('ES_HOST', '127.0.0.1')}:{os.getenv('ES_PORT', 9200)}"]
    )


@lru_cache()
def get_neo4j():
    """Return a Neo4j driver."""
    from neo4j import GraphDatabase

    return GraphDatabase.driver(
        f"bolt://{os.getenv('NEO4J_HOST', '127.0.0.1')}:{os.getenv('NEO4J_BOLT_PORT', 7687)}",
        auth=(os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD")),
    )


@lru_cache()
def get_redis():
    """Return a Redis client."""
    import redis as r

    return r.Redis(
        host=os.getenv("REDIS_HOST", "127.0.0.1"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True,
    )
