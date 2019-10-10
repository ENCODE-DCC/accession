import json
import os
import sys

import pytest

from accession.accession import Accession
from accession.analysis import Analysis
from accession.helpers import mutate_digits, write_json

myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + "/../")


@pytest.fixture(scope="session", params=["tests/data/ENCSR609OHJ_metadata_2reps.json"])
def metadata_json(request):
    with open(request.param) as json_file:
        yield json.load(json_file)


@pytest.fixture(scope="session", params=["tests/data/atac_input.json"])
def input_json(request):
    with open(request.param) as json_file:
        yield json.load(json_file)


@pytest.fixture(scope="session")
def accession(metadata_json, input_json):
    accession_steps = write_json(input_json)
    accession_metadata = write_json(metadata_json)
    server = input_json.get("accession.dcc_server", "dev")
    lab = input_json.get("accession.lab", "/labs/encode-processing-pipeline/")
    award = input_json.get("accession.award", "U41HG007000")
    accessioner = Accession(accession_steps, accession_metadata, server, lab, award)
    # Clean up the debugging and failing artifacts
    for original_file in accessioner.conn.get(accessioner.dataset).get(
        "original_files"
    ):
        if "TSTFF" in original_file:
            original_file = accessioner.conn.get(original_file)
            accessioner.patch_file(
                original_file,
                {
                    "md5sum": mutate_digits(original_file.get("md5sum")),
                    "aliases": [mutate_digits(original_file.get("aliases")[0])],
                    "status": "deleted",
                },
            )

    yield accessioner

    # Cleaning up so the same files can be accessioned again
    for file in accessioner.new_files:
        accessioner.patch_file(
            file,
            {
                "md5sum": mutate_digits(file.get("md5sum")),
                "aliases": [mutate_digits(original_file.get("aliases")[0])],
                "status": "deleted",
            },
        )


@pytest.fixture(scope="session")
def analysis(accession):
    analysis = accession.analysis
    return analysis


@pytest.fixture(scope="session")
def gcbackend(accession):
    gcbackend = accession.backend
    return gcbackend


@pytest.fixture(scope="session")
def dcc_server(accession):
    conn = accession.conn
    return conn


@pytest.fixture
def empty_analysis(metadata_json):
    accession_metadata = write_json(metadata_json)
    analysis = Analysis(accession_metadata, auto_populate=False)
    return analysis
