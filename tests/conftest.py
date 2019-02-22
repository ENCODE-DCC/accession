import pytest
import sys
import os
# myPath = os.path.dirname(os.path.abspath(__file__))
# sys.path.insert(0, myPath + '/../')
import json
from encode_utils.connection import Connection
from accession.backends import GCBackend


@pytest.fixture(scope='session')
def dcc_server_connection():
    yield Connection('dev')


@pytest.fixture(scope='session',
                params=['tests/data/ENCSR609OHJ_metadata_2reps.json'])
def metadata_json(request):
    with open(request.param) as json_file:
        yield json.load(json_file)


@pytest.fixture(scope='session')
def google_backend_connection():
    yield GCBackend('encode-pipeline-test-runs')


def test_metadata(metadata_json):
    assert type(metadata_json) == dict
    assert metadata_json.get('workflowRoot')
