import pytest

from accession.backends import GCBackend, LocalBackend, backend_factory


@pytest.mark.parametrize("uri,expected", [("gs://foo/bar", True), ("not/valid", False)])
def test_gc_backend_is_valid_uri(uri, expected):
    backend = GCBackend()
    result = backend.is_valid_uri(uri)
    assert result is expected


def test_local_backend_is_valid_uri():
    backend = LocalBackend()
    result = backend.is_valid_uri("foo")
    assert result is True


def test_backend_factory():
    result = backend_factory("Local")
    assert isinstance(result, LocalBackend)


def test_backend_factory_invalid_backend_name_raises():
    with pytest.raises(ValueError):
        backend_factory("invalid")
