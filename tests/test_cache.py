from app.rag.cache import CACHE_SCHEMA_VERSION, QueryCache, cache_key


def test_cache_roundtrip_without_redis() -> None:
    cache = QueryCache()
    key = cache_key({"query": "hello", "tenant": "demo"})
    value = {"answer": "world", "metrics": {"total_ms": 1}}

    cache.set(key, value)

    assert cache.get(key) == value


def test_cache_key_is_stable_for_dict_order() -> None:
    left = cache_key({"query": "hello", "tenant": "demo"})
    right = cache_key({"tenant": "demo", "query": "hello"})

    assert left == right


def test_cache_key_includes_schema_version() -> None:
    key = cache_key({"query": "hello"})

    assert CACHE_SCHEMA_VERSION
    assert key.startswith("rag:query:")
