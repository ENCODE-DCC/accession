import pytest

from accession.file import GSFile, LocalFile


@pytest.fixture
def local_file():
    return LocalFile(key="foo", name="bar")


@pytest.fixture
def test_file_contents():
    return b"foo bar baz"


@pytest.fixture
def test_file(tmp_path, test_file_contents):
    path = tmp_path / "test_file.txt"
    path.write_bytes(test_file_contents)
    return LocalFile(key="foo", name=str(path))


@pytest.fixture
def gs_file_with_name_and_bucket(mocker):
    blob = mocker.Mock()
    blob.name = "baz"
    blob.bucket.name = "bar"
    mocker.patch("accession.file.GSFile.blob", mocker.PropertyMock(return_value=blob))
    file = GSFile(key="foo", name="gs://bar/baz")
    return file


def stub_download_as_string(start=None, end=None, data=b"abc123"):
    if start is None:
        start = 0
    if end is None or end + 1 >= len(data):
        end = len(data) - 1
    if start > end:
        return data
    return data[start : end + 1]


@pytest.fixture
def readable_gs_file(mocker):
    blob = mocker.Mock(download_as_string=stub_download_as_string, size=6)
    mocker.patch("accession.file.GSFile.blob", mocker.PropertyMock(return_value=blob))
    gs_file = GSFile(key="foo", name="gs://bar/baz")
    return gs_file


def test_gs_file_md5sum(mocker):
    blob = mocker.Mock(md5_hash="rQproAprtP/Prr1eFZpaHA==")
    mocker.patch("accession.file.GSFile.blob", mocker.PropertyMock(return_value=blob))
    gs_file = GSFile(key="foo", name="gs://bar/baz")
    assert gs_file.md5sum == "ad0a6ba00a6bb4ffcfaebd5e159a5a1c"


def test_gs_file_size(mocker):
    blob = mocker.Mock(size=3)
    mocker.patch("accession.file.GSFile.blob", mocker.PropertyMock(return_value=blob))
    gs_file = GSFile(key="foo", name="gs://bar/baz")
    assert gs_file.size == 3


def test_gs_file_b64_to_hex():
    assert (
        GSFile.b64_to_hex("rQproAprtP/Prr1eFZpaHA==")
        == "ad0a6ba00a6bb4ffcfaebd5e159a5a1c"
    )


def test_gs_file_get_uri_without_scheme(gs_file_with_name_and_bucket):
    assert gs_file_with_name_and_bucket.get_uri_without_scheme() == "bar/baz"


def test_gs_file_get_filename_for_encode_alias(gs_file_with_name_and_bucket):
    assert gs_file_with_name_and_bucket.get_filename_for_encode_alias() == "bar-baz"


def test_gs_file_read_bytes(mocker):
    blob = mocker.Mock()
    blob.download_as_string.return_value = b"foo"
    mocker.patch("accession.file.GSFile.blob", mocker.PropertyMock(return_value=blob))
    gs_file = GSFile(key="foo", name="gs://bar/baz")
    result = gs_file.read_bytes()
    assert result == b"foo"


def test_gs_file_read_json(mocker):
    blob = mocker.Mock()
    blob.download_as_string.return_value = b'{"foo":"bar"}'
    mocker.patch("accession.file.GSFile.blob", mocker.PropertyMock(return_value=blob))
    gs_file = GSFile(key="foo", name="gs://bar/baz")
    result = gs_file.read_json()
    assert result == {"foo": "bar"}


@pytest.mark.parametrize(
    "start,end,expected",
    [(None, None, b"abc123"), (None, 3, b"abc1"), (3, None, b"123"), (1, 2, b"bc")],
)
def test_stub_download_as_string(start, end, expected):
    """
    In this case, need to test the tests to make sure the implementation of
    download_as_string functions the same as Google cloud, reads are 0-indexed and
    inclusive of endpoints.
    """
    result = stub_download_as_string(start, end)
    assert result == expected


def test_gs_file_read(readable_gs_file):
    assert readable_gs_file.read(3) == b"abc"
    assert readable_gs_file.read(3) == b"123"
    assert readable_gs_file.read(3) == b""


def test_gs_file_read_none(readable_gs_file):
    assert readable_gs_file.read() == b"abc123"
    assert readable_gs_file.read() == b""


def test_gs_file_read_amount_then_none(readable_gs_file):
    assert readable_gs_file.read(3) == b"abc"
    assert readable_gs_file.read() == b"123"
    assert readable_gs_file.read() == b""


def test_local_file_md5sum(mocker, local_file):
    mocker.patch("builtins.open", mocker.mock_open(read_data=b"foo"))
    assert local_file.md5sum == "acbd18db4cc2f85cedef654fccc4a4d8"


def test_local_file_size(mocker, local_file):
    stat_result = mocker.Mock(st_size=3)
    mocker.patch("pathlib.Path.stat", return_value=stat_result)
    assert local_file.size == 3


def test_local_file_get_uri_without_scheme(local_file):
    assert local_file.get_uri_without_scheme() == "bar"


@pytest.mark.filesystem
def test_local_file_read_whole_file(test_file, test_file_contents):
    assert test_file.read() == test_file_contents
    assert test_file.read() == b""


@pytest.mark.filesystem
def test_local_file_read_chunks(test_file):
    assert test_file.read(num_bytes=6) == b"foo ba"
    assert test_file.read(num_bytes=5) == b"r baz"
    assert test_file.read(num_bytes=5) == b""


@pytest.mark.filesystem
def test_local_file_read_chunks_then_all(test_file):
    assert test_file.read(num_bytes=6) == b"foo ba"
    assert test_file.read() == b"r baz"
    assert test_file.read() == b""


@pytest.mark.filesystem
def test_local_file_read_bytes(test_file, test_file_contents):
    assert test_file.read_bytes() == test_file_contents


@pytest.mark.filesystem
def test_local_file_read_json(tmp_path):
    path = tmp_path / "test_file.json"
    path.write_bytes(b'{"foo":"bar"}')
    file = LocalFile(key="foo", name=str(path))
    result = file.read_json()
    assert result == {"foo": "bar"}
