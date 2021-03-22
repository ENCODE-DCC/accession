import os
import shutil
from pathlib import Path

import pytest
from encode_utils.connection import Connection

from accession.accession import Accession
from accession.accession_steps import AccessionSteps
from accession.analysis import Analysis
from accession.backends import backend_factory
from accession.metadata import FileMetadata


class AccessionDummy(Accession):
    QC_MAP = {}

    @property
    def assembly(self):
        return "GRCh38"

    @property
    def genome_annotation(self):
        return "V19"

    def get_preferred_default_qc_value(self, file):
        return super().get_preferred_default_qc_value(file)

    def preferred_default_should_be_updated(self, qc_value, current_best_qc_value):
        return super().preferred_default_should_be_updated(
            qc_value, current_best_qc_value
        )

    def upload_file(self, *args, **kwargs):
        pass


@pytest.fixture
def dummy_data_path(tmp_path):
    """
    Copies the dummy data to a temporary directory and returns the path.
    """
    current_dir = Path(__file__).resolve()
    data_dir = current_dir.parent / "data" / "accession_local"
    tmp_data_dir = tmp_path / "accession_local"
    shutil.copytree(data_dir, tmp_data_dir)
    yield str(tmp_data_dir)
    shutil.rmtree(tmp_data_dir)


@pytest.fixture
def local_workflow_metadata(tmp_path, dummy_data_path):
    """
    Need to template out the json, no guarantees that relative paths will work.
    """
    current_dir = Path(__file__).resolve()
    metadata_json_path = current_dir.parent / "data" / "dummy_local_metadata.json"
    raw = metadata_json_path.read_text()
    raw = raw.replace("DATA_DIR", dummy_data_path)
    tmp_metadata_path = tmp_path / "dummy_local_metadata.json"
    tmp_metadata_path.write_text(raw)
    yield FileMetadata(tmp_metadata_path)
    os.remove(tmp_metadata_path)


@pytest.fixture
def dummy_steps_path():
    current_dir = Path(__file__).resolve()
    dummy_steps_path = current_dir.parent / "data" / "accession_local" / "steps.json"
    return dummy_steps_path


@pytest.fixture
def local_accessioner(
    local_workflow_metadata, local_encoded_server, common_metadata, dummy_steps_path
):
    accession_steps = AccessionSteps(dummy_steps_path)
    backend = backend_factory(local_workflow_metadata.backend_name)
    analysis = Analysis(
        local_workflow_metadata,
        raw_fastqs_keys=accession_steps.raw_fastqs_keys,
        raw_fastqs_can_have_task=accession_steps.raw_fastqs_can_have_task,
        backend=backend,
    )
    connection = Connection(local_encoded_server, no_log_file=True)
    return AccessionDummy(accession_steps, analysis, connection, common_metadata)


@pytest.mark.docker
@pytest.mark.filesystem
def test_accession_local_workflow(local_accessioner):
    local_accessioner.accession_steps(force=True)
