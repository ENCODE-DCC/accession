

def test_dcc_server(dcc_server):
    assert dcc_server.dcc_host == 'test.encodedcc.org'


def test_gcbackend(gcbackend):
    assert gcbackend.bucket


def test_analyis(analysis):
    assert len(analysis.files) > 0


def test_empty_analysis(empty_analysis):
    assert len(empty_analysis.files) == 0
