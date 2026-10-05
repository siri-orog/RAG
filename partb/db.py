"""MongoDB singleton."""
from __future__ import annotations

from pymongo import MongoClient

from partb.config import MONGO_DB, MONGO_URI

_client: MongoClient | None = None


def get_mongo() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI)
    return _client


def db():
    return get_mongo()[MONGO_DB]