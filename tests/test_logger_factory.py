from logging import FileHandler, StreamHandler
from unittest.mock import mock_open

from accession.logger_factory import logger_factory


def test_logger_factory(mocker):
    mocker.patch("builtins.open", mock_open())
    result = logger_factory(logger_name="foo", log_file_path="bar", no_log_file=False)
    handler_types = [type(hdlr) for hdlr in result.handlers]
    assert len(handler_types) == 2
    assert StreamHandler in handler_types
    assert FileHandler in handler_types


def test_logger_factory_no_log_file():
    """
    Must use a different logger name to avoid conflict with other test.
    """
    result = logger_factory(logger_name="baz", log_file_path="bar", no_log_file=True)
    handler_types = [type(hdlr) for hdlr in result.handlers]
    assert len(handler_types) == 1
    assert StreamHandler in handler_types
    assert FileHandler not in handler_types
