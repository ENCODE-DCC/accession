import datetime

import pytest


def test_get_runs_by_experiment(db_query, run):
    results = db_query.get_runs_by_experiment_at_id("ABC").all()
    assert len(results) == 1


def test_get_runs_by_workflow_id(db_query, run):
    results = db_query.get_runs_by_workflow_id("123").all()
    assert len(results) == 1


@pytest.mark.parametrize("key,value,expected", [("foo", "bar", 1), ("foo", "baz", 0)])
def test_get_runs_by_workflow_label(db_query, run, key, value, expected):
    results = db_query.get_runs_by_workflow_label(key=key, value=value).all()
    assert len(results) == expected


def test_get_runs_by_date_range_one_result_in_range(db_query, run, date):
    start = date - datetime.timedelta(1)
    end = date + datetime.timedelta(1)
    results = db_query.get_runs_by_date_range(start=start, end=end).all()
    assert len(results) == 1


def test_get_runs_by_date_range_no_result_in_range(db_query, run, date):
    start = date - datetime.timedelta(2)
    end = date - datetime.timedelta(1)
    results = db_query.get_runs_by_date_range(start=start, end=end).all()
    assert len(results) == 0


def test_get_runs_by_date_range_one_result_start_no_end(db_query, run, date):
    start = date - datetime.timedelta(1)
    results = db_query.get_runs_by_date_range(start=start).all()
    assert len(results) == 1


def test_get_runs_by_date_range_one_result_end_no_start(db_query, run, date):
    end = date + datetime.timedelta(1)
    results = db_query.get_runs_by_date_range(end=end).all()
    assert len(results) == 1


def test_get_runs_by_date_range_one_result_no_start_no_end(db_query, run, date):
    results = db_query.get_runs_by_date_range().all()
    assert len(results) == 1


def test_get_runs_by_date_range_start_greater_than_end_raises(db_query, run, date):
    start = date - datetime.timedelta(1)
    end = date - datetime.timedelta(2)
    with pytest.raises(ValueError):
        db_query.get_runs_by_date_range(start=start, end=end)


def test_get_all(db_query):
    result = db_query.get_all_runs().all()
    assert len(result) == 1
