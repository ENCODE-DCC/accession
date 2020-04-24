from unittest.mock import mock_open

import pytest

from accession.accession import AccessionStep, AccessionSteps


@pytest.fixture
def steps(mocker):
    data = """
    {
      "accession.steps": [
        {
          "dcc_step_run": "/analysis-steps/1/",
          "dcc_step_version": "/analysis-step-versions/1-0/",
          "wdl_files": [
            {
              "derived_from_files": [
                {
                  "derived_from_filekey": "fastq",
                  "derived_from_inputs": true,
                  "derived_from_task": "minimap2"
                }
              ],
              "file_format": "bam",
              "filekey": "bam",
              "output_type": "alignments",
              "quality_metrics": [
                  "long_read_rna_mapping"
              ]
            }
          ],
          "wdl_task_name": "minimap2"
        }
      ]
    }
    """
    mocker.patch("builtins.open", mock_open(read_data=data))
    return AccessionSteps("steps.json")


def test_accession_steps_init(steps):
    """
    Once we access steps.content, the _steps is initialized.
    """
    assert not steps._steps
    assert steps.content
    assert steps.content[0].step_run == "/analysis-steps/1/"
    assert steps._steps


def test_accession_steps_content(steps):
    assert isinstance(steps.content, list)
    assert all(isinstance(x, AccessionStep) for x in steps.content)


def test_accession_steps_raw_fastqs_keys_defaults_none(steps):
    assert steps.raw_fastqs_keys is None


def test_accession_step_get_portal_step_run(steps):
    result = steps.content[0].get_portal_step_run(aliases=["foo"])
    assert result == {
        "aliases": ["foo"],
        "status": "in progress",
        "analysis_step_version": "/analysis-step-versions/1-0/",
        "_profile": "analysis_step_runs",
    }


def test_file_params(steps):
    file_params = steps.content[0].wdl_files[0]
    assert file_params.filekey == "bam"
    assert file_params.file_format == "bam"
    assert file_params.output_type == "alignments"
    assert file_params.file_format_type is None
    assert isinstance(file_params.derived_from_files, list)
    assert file_params.callbacks == []
    assert file_params.quality_metrics == ["long_read_rna_mapping"]


def test_derived_from_file(steps):
    file_params = steps.content[0].wdl_files[0].derived_from_files[0]
    assert file_params.allow_empty is False
    assert file_params.derived_from_filekey == "fastq"
    assert file_params.derived_from_inputs is True
    assert file_params.derived_from_task == "minimap2"
    assert file_params.derived_from_output_type is None
    assert file_params.disallow_tasks == []
