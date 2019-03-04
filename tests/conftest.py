import pytest
import sys
import os
import pdb
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../')
import json
from encode_utils.connection import Connection
from accession.backends import GCBackend
from accession.accession import Accession, COMMON_METADATA
from accession.analysis import Analysis
from accession.helpers import write_json


@pytest.fixture(scope='session',
                params=['tests/data/ENCSR609OHJ_metadata_2reps.json'])
def metadata_json(request):
    with open(request.param) as json_file:
        yield json.load(json_file)


@pytest.fixture(scope='session',
                params=['tests/data/atac_input.json'])
def input_json(request):
    with open(request.param) as json_file:
        yield json.load(json_file)


@pytest.fixture(scope='session')
def accession(metadata_json, input_json):
    accession_steps = write_json(input_json.get('accession.steps'))
    accession_metadata = write_json(metadata_json)
    server = input_json.get('accession.dcc_server')
    lab = input_json.get('accession.lab')
    award = input_json.get('accession.award')
    accessioner = Accession(accession_steps,
                            accession_metadata,
                            server,
                            lab,
                            award)
    return accessioner


@pytest.fixture(scope='session')
def analysis(accession):
    analysis = accession.analysis
    return analysis


@pytest.fixture(scope='session')
def gcbackend(accession):
    gcbackend = accession.backend
    return gcbackend


@pytest.fixture(scope='session')
def dcc_server(accession):
    conn = accession.conn
    return conn


def test_dcc_server(dcc_server):
    assert dcc_server.dcc_host == 'test.encodedcc.org'


def test_gcbackend(gcbackend):
    assert gcbackend.bucket
