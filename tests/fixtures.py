import datetime
import json
import os
import shutil
from base64 import b64decode
from pathlib import Path
from time import sleep
from typing import Callable, Iterator, Tuple
from unittest.mock import PropertyMock, create_autospec
from urllib.parse import urljoin

import encode_utils as eu
import pytest
import requests
from encode_utils.connection import Connection
from pytest_mock.plugin import MockerFixture
from WDL import parse_document

import docker
from accession import backends
from accession.accession import (
    Accession,
    AccessionChip,
    AccessionMicroRna,
    accession_factory,
)
from accession.analysis import Analysis
from accession.database.connection import DbSession
from accession.database.models import Run, RunStatus, WorkflowLabel
from accession.database.query import DbQuery
from accession.encode_models import (
    EncodeAttachment,
    EncodeCommonMetadata,
    EncodeDocument,
    EncodeDocumentType,
    EncodeExperiment,
    EncodeFile,
)
from accession.file import GSFile
from accession.helpers import Recorder
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
            encoded_docker_image,
            detach=True,
            ports={"8000/tcp": host_port},
            auto_remove=True,
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


@pytest.fixture(scope="session")
def db_session():
    return DbSession("sqlite:///:memory:", echo=True)


@pytest.fixture(scope="session")
def db_query(db_session):
    return DbQuery(db_session)


@pytest.fixture(scope="session")
def date():
    return datetime.date(1999, 9, 9)


@pytest.fixture(scope="session")
def run(db_session, date):
    label = WorkflowLabel(key="foo", value="bar")
    run = Run(
        experiment_at_id="ABC",
        workflow_id="123",
        date_created=date,
        status=RunStatus.Succeeded,
        workflow_labels=[label],
    )
    db_session.session.add(run)
    yield run
    db_session.session.delete(run)


@pytest.fixture(scope="session")
def additional_runs(db_session):
    run = Run(
        experiment_at_id="/experiments/ENCSR123ABC/",
        workflow_id="456",
        date_created=datetime.date(2020, 3, 10),
        status=RunStatus.Succeeded,
        workflow_labels=[WorkflowLabel(key="caper-str-label", value="bar")],
    )
    run2 = Run(
        experiment_at_id="/experiments/ENCSR456DEF/",
        workflow_id="60fb02a7-31ae-4e9e-8e77-9c2722189cb4",
        date_created=datetime.date(2020, 3, 11),
        status=RunStatus.Succeeded,
        workflow_labels=[WorkflowLabel(key="caper-str-label", value="baz")],
    )
    db_session.session.add(run)
    db_session.session.add(run2)
    yield
    db_session.session.delete(run)
    db_session.session.delete(run2)


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
    mock_gc_backend, metadata_json_path: Path
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
def wdl_workflow():
    workflow = (
        'workflow myWorkflow { meta { version: "v1.2.3" } call myTask } task myTask {'
        " command { bar }}"
    )
    return workflow


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
def gsfile(mocker):
    task = {
        "inputs": {
            "prefix": "pooled-pr1_vs_pooled-pr2",
            "fastqs_R1": ["gs://abc/spam.fastq.gz"],
        },
        "outputs": {},
    }
    my_task = Task("my_task", task)
    mocker.patch(
        "accession.file.GSFile.md5sum", mocker.PropertyMock(return_value="123")
    )
    return GSFile(key="foo", name="gs://abc/spam.fastq.gz", task=my_task, client="bar")


@pytest.fixture
def mock_file(mocker):
    file = mocker.Mock(
        filekeys=["foo"], filename="gs://foo/bar", size=123, md5sum="abc"
    )
    return file


@pytest.fixture
def mock_gs_file(mocker):
    # md5sum is yN0BGTic4eg+yn7K3BVlGw== in base 64
    file = mocker.MagicMock(
        filekeys=["foo"],
        filename="gs://foo/bar",
        size=3,
        md5sum="c8dd0119389ce1e83eca7ecadc15651b",
    )
    file.blob.download_as_string.return_value = b'{"foobar": "bazqux"}'
    return file


class LocalMockGsFile:
    SCHEME = "gs://"

    def __init__(self, key, name, task=None, used_by_task=None, client=None):
        self.filekeys = [key]
        self.filename = name
        self.task = task
        self.size = 3
        self.used_by_tasks = [used_by_task] if used_by_task else []
        self._md5_lookup = None

    @property
    def md5_lookup(self):
        if self._md5_lookup is None:
            md5_file = Path(__file__).resolve().parent / "data" / "gcloud_md5s.json"
            with open(md5_file) as f:
                self._md5_lookup = json.load(f)
        return self._md5_lookup

    @property
    def md5sum(self) -> str:
        b64_md5 = self.md5_lookup[self.filename]
        return b64decode(b64_md5).hex()

    def download_as_string(self) -> bytes:
        """
        We use the concatenation of the last two path elements (glob and filename) to
        find the file in the test data, which should be unique
        """
        file_name = self.filename.split("/")[-1]
        current_dir = Path(__file__).resolve()
        file_path = current_dir.parent / "data" / "files" / file_name
        with open(file_path, "rb") as f:
            binary_data = f.read()
        return binary_data

    def read_json(self):
        """
        Read file and convert to JSON
        """
        return json.loads(self.download_as_string().decode())

    def get_task(self) -> Task:
        """
        Either gets the `File`'s task or raises a ValueError.
        """
        task = self.task
        if task is None:
            raise ValueError("No task found")
        return task

    def get_uri_without_scheme(self) -> str:
        return self.filename.split(self.SCHEME)[-1]

    def get_filename_for_encode_alias(self) -> str:
        return self.get_uri_without_scheme().replace("/", "-")


@pytest.fixture
def mock_gc_backend(mocker):
    """
    A mocked instance of GCBackend that cannot initialize a Google Cloud client or make
    Google Cloud API calls.

    mocker fixture can only be used with function-scoped pytest fixtures for now:
    https://github.com/pytest-dev/pytest-mock/issues/136
    """
    mocker.patch("accession.file.GSFile", mock_gs_file)
    mocker.patch("accession.backends.GCBackend.client", mocker.PropertyMock())
    mock_gc_backend = backends.GCBackend()
    return mock_gc_backend


@pytest.fixture
def mock_accession_gc_backend(mocker):
    """
    Similar to mock_gc_backend, except it provides real md5sums and can access real test
    data files.
    """
    mocker.patch("accession.backends.GCBackend.client", mocker.PropertyMock())
    mocker.patch("accession.file.GSFile", LocalMockGsFile)
    mocker.patch("accession.backends.GSFile", LocalMockGsFile)
    mock_gc_backend = backends.GCBackend()
    return mock_gc_backend


@pytest.fixture
def accessioner_factory(
    mocker: MockerFixture,
    mock_accession_gc_backend,
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
            use_in_memory_db=True,
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


@pytest.fixture
def mock_metadata(wdl_workflow):
    class MockMetadata:
        content = {"id": "foo", "workflowRoot": "gs://foo/bar", "calls": {}}
        workflow_id = "123"

        def get_parsed_workflow(self):
            return parse_document(wdl_workflow)

    return MockMetadata()


class MockAccessionSteps:
    path_to_json = "/dev/null"
    content = {"accession.steps": [{"a": "b"}]}
    quality_standard = "/quality-standards/bar/"


@pytest.fixture
def mock_accession_steps():
    return MockAccessionSteps()


@pytest.fixture
def mock_accession(
    mocker: MockerFixture,
    mock_accession_gc_backend,
    mock_metadata,
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
        Recorder(use_in_memory_db=True),
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
        Recorder(use_in_memory_db=True),
        no_log_file=True,
    )
    return mock_accession


@pytest.fixture
def mock_accession_chip(
    mocker: MockerFixture,
    mock_accession_gc_backend,
    mock_metadata,
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
        Recorder(use_in_memory_db=True),
        no_log_file=True,
    )
    return mocked_accession


@pytest.fixture
def mock_accession_unreplicated(
    mocker: MockerFixture,
    mock_accession_gc_backend,
    mock_metadata,
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
                    "replicates": [
                        {"biological_replicate_number": 1, "status": "released"}
                    ],
                }
            )
        ),
    )
    mocked_accession = AccessionMicroRna(
        "imaginary_steps.json",
        Analysis(mock_metadata, backend=mock_accession_gc_backend),
        "mock_server.biz",
        EncodeCommonMetadata(lab, award),
        Recorder(use_in_memory_db=True),
        no_log_file=True,
    )
    return mocked_accession
