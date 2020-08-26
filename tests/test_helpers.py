from accession.helpers import LruCache, flatten, impersonate_file, string_to_number


def test_lru_cache_get_has_key_should_reorder():
    cache = LruCache()
    cache.insert("foo", "bar")
    cache.insert("baz", "qux")
    result = cache.get("foo")
    assert result == "bar"
    assert list(cache.data.keys()) == ["baz", "foo"]


def test_lru_cache_get_does_not_have_key_returns_none():
    cache = LruCache()
    cache.insert("foo", "bar")
    result = cache.get("baz")
    assert result is None


def test_lru_cache_insert():
    cache = LruCache(max_size=2)
    cache.insert("foo", "bar")
    cache.insert("baz", "qux")
    cache.insert("spam", "eggs")
    assert cache.get("foo") is None


def test_lru_cache_insert_extant_key_updates_value():
    cache = LruCache(max_size=2)
    cache.insert("foo", "bar")
    cache.insert("baz", "qux")
    cache.insert("foo", "eggs")
    assert cache.get("foo") == "eggs"
    assert list(cache.data.keys()) == ["baz", "foo"]


def test_lru_cache_invalidate_key_in_cache():
    cache = LruCache()
    cache.insert("foo", "bar")
    cache.invalidate("foo")
    assert "foo" not in cache.data.keys()


def test_lru_cache_invalidate_key_not_in_cache_does_not_raise():
    cache = LruCache()
    cache.insert("foo", "bar")
    cache.invalidate("baz")
    assert "foo" in cache.data.keys()


def test_string_to_number_not_string_return_input():
    not_string = 3
    result = string_to_number(not_string)
    assert result == not_string


def test_string_to_number_stringy_int_returns_int():
    int_string = "3"
    result = string_to_number(int_string)
    assert isinstance(result, int)
    assert result == 3


def test_string_to_number_stringy_float_returns_float():
    float_string = "3.0"
    result = string_to_number(float_string)
    assert isinstance(result, float)
    assert result == 3.0


def test_string_to_number_non_number_string_returns_input():
    non_number_string = "3.0a"
    result = string_to_number(non_number_string)
    assert result == non_number_string


def test_flatten() -> None:
    result = flatten([["a", "b"], ["c", "d"]])
    assert result == ["a", "b", "c", "d"]


def test_impersonate_file() -> None:
    bytes_data = b"firstline\nsecondline\n"
    with impersonate_file(bytes_data) as totally_a_file:
        with open(totally_a_file) as fp:
            data = fp.readlines()
    assert len(data) == 2
    assert isinstance(data[0], str)
    assert data[1] == "secondline\n"
