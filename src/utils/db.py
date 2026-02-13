"""
OenoBench — Database connection utilities.

Usage:
    from src.utils.db import get_pg, get_es, get_neo4j, get_redis
"""

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache()
def get_pg():
    """Return a psycopg2 connection to PostgreSQL."""
    import psycopg2
    from psycopg2.extras import RealDictCursor

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", 5432)),
        dbname=os.getenv("POSTGRES_DB", "winebench"),
        user=os.getenv("POSTGRES_USER", "winebench"),
        password=os.getenv("POSTGRES_PASSWORD"),
        cursor_factory=RealDictCursor,
    )


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
