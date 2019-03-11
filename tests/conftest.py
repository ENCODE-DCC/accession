import pytest
import sys
import os
myPath = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, myPath + '/../')
import json
from accession.accession import Accession
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


@pytest.fixture
def empty_analysis(metadata_json):
    accession_metadata = write_json(metadata_json)
    analysis = Analysis(accession_metadata,
                        auto_populate=False)
    return analysis
