import json
import os
import shutil
from base64 import b64decode
from pathlib import Path
from time import sleep
from typing import Callable, Dict, Iterator, Tuple
from unittest.mock import PropertyMock, create_autospec
from urllib.parse import urljoin

import attr
import encode_utils as eu
import pytest
import requests
from encode_utils.connection import Connection
from pytest_mock.plugin import MockFixture

import docker
from accession import backends
from accession.accession import (
    Accession,
    AccessionChip,
    AccessionMicroRna,
    accession_factory,
)
from accession.analysis import Analysis
from accession.encode_models import (
    EncodeAttachment,
    EncodeCommonMetadata,
    EncodeDocument,
    EncodeDocumentType,
    EncodeExperiment,
    EncodeFile,
)
from accession.file import GSFile
from accession.metadata import FileMetadata
from accession.task import Task


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
    yield server_address
    container.kill()


@pytest.fixture
def server_name() -> str:
    return "mock_server.biz"


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
def common_metadata(lab, award):
    return EncodeCommonMetadata(lab, award)


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
    normal_analysis = Analysis(
        FileMetadata(metadata_json_path), backend=mock_gc_backend
    )
    return normal_analysis


@pytest.fixture
def metadata_json(metadata_json_path: Path) -> Iterator[dict]:
    with open(metadata_json_path) as json_file:
        yield json.load(json_file)


@pytest.fixture
def mirna_replicated_metadata_path() -> str:
    current_dir = Path(__file__).resolve()
    metadata_json_path = current_dir.parent / "data" / "mirna_replicated_metadata.json"
    return str(metadata_json_path)


@pytest.fixture
def encode_file_no_qc():
    return EncodeFile({"@id": "/files/foo/", "quality_metrics": []})


@pytest.fixture(scope="module")
def encode_attachment():
    return EncodeAttachment(
        filename="/my/dir/haz/my_text_file", contents=b"foo bar baz"
    )


@pytest.fixture(scope="module")
def encode_common_metadata():
    return EncodeCommonMetadata("/labs/lab/", "award")


@pytest.fixture
def encode_document(encode_attachment, encode_common_metadata):
    return EncodeDocument(
        encode_attachment,
        encode_common_metadata,
        EncodeDocumentType.WorkflowMetadata,
        aliases=["encode:foo"],
    )


@pytest.fixture
def gsfile():
    task = {
        "inputs": {
            "prefix": "pooled-pr1_vs_pooled-pr2",
            "fastqs_R1": ["gs://abc/spam.fastq.gz"],
        },
        "outputs": {},
    }
    my_task = Task("my_task", task)
    return GSFile(
        "foo", "gs://abc/spam.fastq.gz", md5sum="123", size="456", task=my_task
    )


@attr.s(auto_attribs=True)
class MockFile:
    filename: str
    size: int
    md5sum: str


@pytest.fixture
def mock_file() -> MockFile:
    return MockFile("gs://foo/bar", 123, "abc")


class MockGCBackend(backends.GCBackend):
    def __init__(self, bucket: str):
        self.client = MockGCClient()
        self.bucket = self.client.get_bucket(bucket)


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
    def md5sum(self) -> str:
        # yN0BGTic4eg+yn7K3BVlGw== in base 64
        return "c8dd0119389ce1e83eca7ecadc15651b"

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
    def md5sum(self) -> str:
        b64_md5 = self.md5_lookup[f"gs://{self.bucket.name}/{self.path}"]
        return b64decode(b64_md5).hex()

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
    mocker.patch.object(backends, "GcsBlob", MockBlob)
    mock_gc_backend = MockGCBackend("accession-test-bucket")
    return mock_gc_backend


@pytest.fixture
def mock_accession_gc_backend(mocker) -> MockGCBackend:
    """
    Similar to mock_gc_backend, except it provides real md5sums and can access real test
    data files.
    """
    mocker.patch.object(backends, "GcsBlob", LocalMockBlob)
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

        def mock_set_dcc_mode(self, dcc_mode: str) -> str:
            eu.DCC_MODES[dcc_mode] = {"host": dcc_mode, "url": f"http://{dcc_mode}/"}
            return dcc_mode

        mocker.patch.object(Connection, "_set_dcc_mode", mock_set_dcc_mode)

        accessioner = accession_factory(
            assay_name,
            metadata_file,
            local_encoded_server,
            lab,
            award,
            backend=mock_accession_gc_backend,
            no_log_file=True,
        )

        mocker.patch.object(
            accessioner, "upload_file", return_value=None, autospec=True
        )
        with open(
            current_dir.parent / "data" / "validation" / f"{assay_name}" / "files.json"
        ) as f:
            expected_files = json.load(f)
        yield (accessioner, expected_files)
        shutil.rmtree(current_dir.parents[1] / "EU_Logs")

    return _accessioner_factory


class MockMetadata:
    content = {"id": "foo", "workflowRoot": "gs://foo/bar", "calls": {}}
    workflow_id = "123"


@pytest.fixture
def mock_metadata():
    return MockMetadata()


class MockAccessionSteps:
    path_to_json = "/dev/null"
    content = {"accession.steps": [{"a": "b"}]}


@pytest.fixture
def mock_accession_steps():
    return MockAccessionSteps()


@pytest.fixture
def mock_accession(
    mocker: MockFixture,
    mock_accession_gc_backend: MockGCBackend,
    mock_metadata: MockMetadata,
    mock_accession_steps: MockAccessionSteps,
    server_name: str,
    common_metadata: EncodeCommonMetadata,
) -> Accession:
    """
    Mocked accession instance with dummy __init__ that doesn't do anything and pre-baked
    assembly property. @properties must be patched before instantiation
    """
    mocker.patch.object(
        AccessionMicroRna, "assembly", new_callable=PropertyMock(return_value="hg19")
    )
    mocker.patch.object(
        AccessionMicroRna,
        "genome_annotation",
        new_callable=PropertyMock(return_value="V19"),
    )
    mocker.patch.object(
        Accession,
        "experiment",
        new_callable=PropertyMock(
            return_value=EncodeExperiment(
                {
                    "@id": "/experiments/foo/",
                    "assay_term_name": "microRNA",
                    "replicates": [
                        {"biological_replicate_number": 1},
                        {"biological_replicate_number": 2},
                    ],
                }
            )
        ),
    )
    mocker.patch.object(Accession, "preflight_helper", new_callable=PropertyMock())
    mocked_accession = AccessionMicroRna(
        mock_accession_steps,
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        create_autospec(Connection, dcc_url=server_name),
        common_metadata,
        no_log_file=True,
    )
    return mocked_accession


@pytest.fixture
def mock_accession_not_patched(
    mocker,
    mock_accession_gc_backend,
    mock_metadata,
    mock_accession_steps,
    server_name,
    common_metadata,
    mock_file,
):
    mocker.patch.object(
        Analysis, "raw_fastqs", new_callable=PropertyMock(return_value=[mock_file])
    )
    mock_accession = AccessionMicroRna(
        mock_accession_steps,
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        create_autospec(Connection, dcc_url=server_name),
        common_metadata,
        no_log_file=True,
    )
    return mock_accession


@pytest.fixture
def mock_accession_chip(
    mocker: MockFixture,
    mock_accession_gc_backend: MockGCBackend,
    mock_metadata: MockMetadata,
    mock_accession_steps: MockAccessionSteps,
    server_name: str,
    common_metadata: EncodeCommonMetadata,
) -> Accession:
    """
    Mocked accession instance with dummy __init__ that doesn't do anything and pre-baked
    assembly property. @properties must be patched before instantiation
    """
    mocker.patch.object(
        AccessionChip, "assembly", new_callable=PropertyMock(return_value="hg19")
    )
    mocker.patch.object(
        AccessionChip,
        "genome_annotation",
        new_callable=PropertyMock(return_value="V19"),
    )
    mocker.patch.object(
        Accession,
        "experiment",
        new_callable=PropertyMock(
            return_value=EncodeExperiment(
                {
                    "@id": "foo",
                    "assay_term_name": "TF ChIP-seq",
                    "replicates": [
                        {"biological_replicate_number": 1},
                        {"biological_replicate_number": 2},
                    ],
                }
            )
        ),
    )
    mocked_accession = AccessionChip(
        mock_accession_steps,
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        server_name,
        common_metadata,
        no_log_file=True,
    )
    return mocked_accession


@pytest.fixture
def mock_accession_unreplicated(
    mocker: MockFixture,
    mock_accession_gc_backend: MockGCBackend,
    mock_metadata: MockMetadata,
    lab: str,
    award: str,
) -> Accession:
    """
    Mocked accession instance with dummy __init__ that doesn't do anything and pre-baked
    assembly property. @properties must be patched before instantiation
    """
    mocker.patch.object(
        Accession,
        "experiment",
        new_callable=PropertyMock(
            return_value=EncodeExperiment(
                {
                    "@id": "foo",
                    "assay_term_name": "microRNA",
                    "replicates": [{"biological_replicate_number": 1}],
                }
            )
        ),
    )
    mocked_accession = AccessionMicroRna(
        "imaginary_steps.json",
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        "mock_server.biz",
        EncodeCommonMetadata(lab, award),
        no_log_file=True,
    )
    return mocked_accession
