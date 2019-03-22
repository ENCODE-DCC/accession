

def test_dcc_server(dcc_server):
    assert dcc_server.dcc_host == 'test.encodedcc.org'


def test_gcbackend(gcbackend):
    assert gcbackend.bucket


def test_analyis(analysis):
    assert len(analysis.files) > 0


def test_empty_analysis(empty_analysis):
    assert len(empty_analysis.files) == 0


def test_accession(accession):
    assert accession.steps_and_params_json
    assert isinstance(accession.steps_and_params_json, list)
    assert len(accession.steps_and_params_json) > 0
