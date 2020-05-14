import pytest

from accession.backends import GcsBlob
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


def test_gcs_blob_b64_to_hex():
    assert (
        GcsBlob.b64_to_hex("rQproAprtP/Prr1eFZpaHA==")
        == "ad0a6ba00a6bb4ffcfaebd5e159a5a1c"
    )


def test_gcs_blob_read(mocker):
    """
    Mocking super() is hard, so we just mock out the whole __init__ and set the values
    that we need, see https://github.com/pytest-dev/pytest-mock/issues/110
    """
    mocker.patch.object(GcsBlob, "__init__", return_value=None)
    blob = GcsBlob("key", "bucket")
    data = b"abc123"
    mocker.patch.object(
        blob, "download_as_string", lambda start, end: data[start : end + 1]
    )
    blob.pos = 0
    blob._properties = {"size": len(data)}
    assert blob.read(3) == b"abc"
    assert blob.read(3) == b"123"
    assert blob.read(3) == b""
