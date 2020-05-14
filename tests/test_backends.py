import json

import pytest

from accession.file import GSFile

from .fixtures import MockBucket


@pytest.mark.parametrize(
    "filename",
    ["gs://accession-test-bucket/test.txt", "gs://different-test-bucket/test.txt"],
)
def test_blob_from_filename(mock_gc_backend, filename):
    blob = mock_gc_backend.blob_from_filename(filename)
    assert blob.path == "test.txt"


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
