import json
import os
import shutil
from pathlib import Path
from time import sleep
from typing import Callable, Dict, Iterator, Tuple
from urllib.parse import urljoin

import attr
import encode_utils as eu
import pytest
import requests
from encode_utils.connection import Connection
from google.cloud import storage
from pytest_mock.plugin import MockFixture

import docker
from accession.accession import Accession, AccessionSteps
from accession.analysis import Analysis, MetaData
from accession.backends import GCBackend


@pytest.fixture(scope="session")
def local_encoded_server(
    api_credentials: Tuple[str, str], encoded_docker_image: str
) -> Iterator[str]:
    """
    Spin up the encoded local app (using default command and user) bound to host port
    8000, and kill the container when done.  Running the tests requires docker daemon to
    be running first. Note the session scope of the fixture, the app is expensive to
    spin up so we try to reuse it as many times as possible. This fixture is written as
    as generator so we can reenter the function stack frame to perform the clean up of
    killing the container.

    There are two conditions that could cause a retry here, handled in the same while
    loop. We expect that initially we'll get 504s, if nginx hasn't started yet, or 502s
    once nginx does start. Then, once we can hit the _indexer_state endpoint, we need to
    check that it's done indexing and check again later if it is not.

    Maybe we don't actually need to wait until it is done indexing, but I think it
    probably helps make the actual tests more stable.
    """
    host_port = 8000
    if not encoded_docker_image:
        raise ValueError(
            (
                "No docker image specfied, make sure you are using --docker [IMAGE] pytest "
                "argument"
            )
        )
    client = docker.from_env()
    try:
        container = client.containers.run(
            encoded_docker_image, detach=True, ports={"8000/tcp": host_port}
        )
    except Exception as e:
        raise RuntimeError(
            (
                f"Could not run docker image {encoded_docker_image}, make sure the Docker "
                "daemon is running and the image has been pulled"
            )
        ) from e
    server_address = f"localhost:{host_port}"
    retries_left = 6
    while True:
        sleep(10)
        if container.status == "exited":
            raise RuntimeError("Container unexpectedly exited early")
        try:
            response = requests.get(
                urljoin(f"http://{server_address}", "_indexer_state"),
                headers={"Accept": "application/json"},
                auth=api_credentials,
            )
        except requests.ConnectionError:
            retries_left -= 1
            continue
        if not response.ok:
            if retries_left > 0:
                retries_left -= 1
                continue
            container.kill()
            response.raise_for_status()
        res = response.json()
        if res.get("state", {}).get("status") == "done":
            break
        if retries_left > 0:
            retries_left -= 1
            continue
        container.kill()
        raise RuntimeError("Elasticsearch took too long to index")
    sleep(10)
    yield server_address
    container.kill()


@pytest.fixture(scope="session")
def lab() -> str:
    return "/labs/encode-processing-pipeline/"


@pytest.fixture(scope="session")
def award() -> str:
    """
    This is the ENC4 award for the DCC
    """
    return "U24HG009397"


@pytest.fixture(scope="session")
def api_credentials() -> Tuple[str, str]:
    return ("foobar", "bazqux")


@pytest.fixture(scope="session")
def environ_api_credentials(api_credentials: Tuple[str, str]) -> None:
    key, secret = api_credentials
    os.environ["DCC_API_KEY"] = key
    os.environ["DCC_SECRET_KEY"] = secret


@pytest.fixture
def metadata_json_path() -> Path:
    current_dir = Path(__file__).resolve()
    metadata_json_path = current_dir.parent / "data" / "ENCSR609OHJ_metadata_2reps.json"
    return metadata_json_path


@pytest.fixture
def normal_analysis(
    mock_gc_backend: MockFixture, metadata_json_path: Path
) -> Analysis:  # noqa: F811
    normal_analysis = Analysis(MetaData(metadata_json_path), backend=mock_gc_backend)
    return normal_analysis


@pytest.fixture
def metadata_json(metadata_json_path: Path) -> Iterator[dict]:
    with open(metadata_json_path) as json_file:
        yield json.load(json_file)


class MockGCBackend(GCBackend):
    def __init__(self, bucket: str):
        self.client = MockGCClient()
        self.bucket = self.client.get_bucket(bucket)
        self.local_mapping = {}


class MockBucket:
    def __init__(self, bucket: str):
        self.name = bucket

    def list_blobs(self) -> None:
        pass


class MockGCClient:
    def get_bucket(self, bucket: str) -> MockBucket:
        return MockBucket(bucket)


@attr.s(auto_attribs=True)
class MockBlob:
    """
    Using a dataclass would work here too, but attrs works for Python 3.6 as well.
    """

    path: str
    bucket: MockBucket
    size: int = 3

    @property
    def md5_hash(self) -> str:
        # c8dd0119389ce1e83eca7ecadc15651b in hex
        return "yN0BGTic4eg+yn7K3BVlGw=="

    @property
    def id(self) -> str:
        return f"{self.bucket.name}/{self.path}"

    @property
    def public_url(self) -> str:
        url = urljoin("https://www.mystorageapi.com", f"{self.bucket.name}/{self.path}")
        return url

    def reload(self) -> None:
        pass

    def download_as_string(self) -> bytes:
        return b'{"foobar": "bazqux"}'

    def download_to_filename(self, file: str) -> None:
        with open(file, "wb") as f:
            f.write(b'{"foobar": "bazqux"}')


def load_md5_map() -> Dict[str, str]:
    md5_file = Path(__file__).resolve().parent / "data" / "gcloud_md5s.json"
    with open(md5_file) as f:
        md5_lookup = json.load(f)
    return md5_lookup


class LocalMockBlob(MockBlob):
    def __init__(self, path: str, bucket: MockBucket, size: int = 3):
        self.path = path
        self.bucket = bucket
        self.size = size

    md5_lookup = load_md5_map()

    @property
    def md5_hash(self) -> str:
        return self.md5_lookup[f"gs://{self.bucket.name}/{self.path}"]

    def download_as_string(self) -> bytes:
        """
        We use the concatenation of the last two path elements (glob and filename) to
        find the file in the test data, which should be unique
        """
        file_name = self.path.split("/")[-1]
        current_dir = Path(__file__).resolve()
        file_path = current_dir.parent / "data" / "files" / file_name
        with open(file_path, "rb") as f:
            binary_data = f.read()
        return binary_data


@pytest.fixture
def mock_gc_backend(mocker) -> MockGCBackend:
    """
    Fully mocked fixture returning an instance of MockGCBackend that does not initialize
    a Google Cloud client or make Google Cloud API calls.

    mocker fixture can only be used with function-scoped pytest fixtures for now:
    https://github.com/pytest-dev/pytest-mock/issues/136
    """
    mocker.patch.object(storage.blob, "Blob", MockBlob)
    mock_gc_backend = MockGCBackend("accession-test-bucket")
    return mock_gc_backend


@pytest.fixture
def mock_accession_gc_backend(mocker) -> MockGCBackend:
    """
    Similar to mock_gc_backend, except it provides real md5sums and can access real test
    data files.
    """
    mocker.patch.object(storage.blob, "Blob", LocalMockBlob)
    mock_gc_backend = MockGCBackend("encode-processing")
    return mock_gc_backend


@pytest.fixture
def accessioner_factory(
    mocker: MockFixture,
    mock_accession_gc_backend: MockGCBackend,
    local_encoded_server: str,
    environ_api_credentials: None,
    lab: str,
    award: str,
) -> Callable:
    def _accessioner_factory(metadata_file: str, assay_name: str) -> Iterator:
        # Setup
        current_dir = Path(__file__).resolve()
        metadata = MetaData(current_dir.parent / "data" / metadata_file)
        analysis = Analysis(metadata, backend=mock_accession_gc_backend)
        accession_steps = AccessionSteps(
            current_dir.parents[1] / "accession_steps" / f"{assay_name}_steps.json"
        )

        def mock_set_dcc_mode(self, dcc_mode: str) -> str:
            eu.DCC_MODES[dcc_mode] = {"host": dcc_mode, "url": f"http://{dcc_mode}/"}
            return dcc_mode

        mocker.patch.object(Connection, "_set_dcc_mode", mock_set_dcc_mode)
        connection = Connection(local_encoded_server)

        accessioner = Accession(accession_steps, analysis, connection, lab, award)

        mocker.patch.object(
            accessioner.conn, "upload_file", return_value=None, autospec=True
        )
        with open(
            current_dir.parent / "data" / "validation" / f"{assay_name}" / "files.json"
        ) as f:
            expected_files = json.load(f)
        yield (accessioner, expected_files)
        shutil.rmtree(current_dir.parents[1] / "EU_Logs")
        os.remove(current_dir.parents[1] / "accession.log")

    return _accessioner_factory
