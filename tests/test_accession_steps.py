from pathlib import Path

import pytest

from accession.accession import AccessionSteps


@pytest.mark.filesystem
def test_accession_steps_init(steps):
    """
    Once we access steps.content, the _steps is initialized.
    """
    assert not steps._steps
    assert steps.content
    assert (
        steps.content[0]["dcc_step_run"]
        == "/analysis-steps/long-read-rna-seq-alignments-step-v-1/"
    )
    assert steps._steps


@pytest.mark.filesystem
def test_accession_steps_path_to_json(steps):
    """
    The absolute path will vary across systems, so we only observe the last two pieces
    """
    assert steps.path_to_json.parts[-2:] == ("data", "long_rna_steps.json")


@pytest.mark.filesystem
def test_accession_steps_content(steps):
    assert isinstance(steps.content, list)
    assert all(isinstance(x, dict) for x in steps.content)


@pytest.fixture(scope="module")
def steps():
    current_dir = Path(__file__).resolve()
    steps_json_path = current_dir.parent / "data" / "long_rna_steps.json"
    return AccessionSteps(steps_json_path)
