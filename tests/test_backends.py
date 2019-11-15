import json

import pytest

from accession.file import GSFile

from .fixtures import MockBlob, MockBucket


@pytest.mark.parametrize(
    "filename",
    ["gs://accession-test-bucket/test.txt", "gs://different-test-bucket/test.txt"],
)
def test_blob_from_filename(mock_gc_backend, filename):
    blob = mock_gc_backend.blob_from_filename(filename)
    assert blob.path == "test.txt"


def test_md5sum(mock_gc_backend):
    md5sum = mock_gc_backend.md5sum("gs://different-test-bucket/test.txt")
    assert md5sum == "c8dd0119389ce1e83eca7ecadc15651b"


def test_size(mock_gc_backend):
    size = mock_gc_backend.size("gs://different-test-bucket/test.txt")
    assert size == 3


def test_md5_from_blob(mock_gc_backend):
    bucket = MockBucket("baz")
    blob = MockBlob("qux", bucket)
    md5sum = mock_gc_backend.md5_from_blob(blob)
    assert md5sum == "c8dd0119389ce1e83eca7ecadc15651b"


def test_file_path(mock_gc_backend):
    file = "gs://different-test-bucket/test.txt"
    bucket = MockBucket("different-test-bucket")
    file_path = mock_gc_backend.file_path(file, bucket)
    assert file_path == "test.txt"


def test_read_file(mock_gc_backend):
    file_as_str = mock_gc_backend.read_file("gs://foo/bar")
    assert file_as_str == b'{"foobar": "bazqux"}'


def test_read_json(mock_gc_backend):
    gs_file = GSFile(key="foo", name="gs://foo/bar", md5sum="12345", size="123")
    file = mock_gc_backend.read_json(gs_file)
    assert file == {"foobar": "bazqux"}


def test_download(mock_gc_backend):
    local_filename, md5sum = mock_gc_backend.download("gs://foo/bar")
    with open(local_filename) as f:
        assert json.load(f) == {"foobar": "bazqux"}
    assert md5sum == "c8dd0119389ce1e83eca7ecadc15651b"
