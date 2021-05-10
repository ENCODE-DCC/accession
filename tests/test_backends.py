import pytest

from accession.backends import AwsBackend, GCBackend, LocalBackend, backend_factory


@pytest.mark.parametrize("uri,expected", [("gs://foo/bar", True), ("not/valid", False)])
def test_gc_backend_is_valid_uri(uri, expected):
    backend = GCBackend()
    result = backend.is_valid_uri(uri)
    assert result is expected


@pytest.mark.parametrize(
    "uri,expected", [("s3://foo/bar", True), ("/not/valid", False)]
)
def test_aws_backend_is_valid_uri(uri, expected):
    backend = AwsBackend()
    result = backend.is_valid_uri(uri)
    assert result is expected


def test_local_backend_is_valid_uri():
    backend = LocalBackend()
    result = backend.is_valid_uri("foo")
    assert result is True


@pytest.mark.parametrize(
    "backend_name,expected_type",
    [
        ("Local", LocalBackend),
        ("sge", LocalBackend),
        ("aws", AwsBackend),
        ("gcp", GCBackend),
    ],
)
def test_backend_factory(backend_name, expected_type):
    result = backend_factory(backend_name)
    assert isinstance(result, expected_type)


def test_backend_factory_invalid_backend_name_raises():
    with pytest.raises(ValueError):
        backend_factory("invalid")
