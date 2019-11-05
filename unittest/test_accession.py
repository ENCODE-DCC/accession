import pytest
from io import StringIO
from requests import Response
from unittest.mock import patch

from accession.accession import AccessionSteps
from accession.accession import Accession
from encode_utils.connection import Connection

LONG_RNA_STEPS = """{
  "accession.steps": [
    {
      "dcc_step_run": "/analysis-steps/long-read-rna-seq-alignments-step-v-1/",
      "dcc_step_version": "/analysis-step-versions/long-read-rna-seq-alignments-step-v-1-0/",
      "wdl_files": [
        {
          "derived_from_files": [
            {
              "derived_from_filekey": "fastq",
              "derived_from_inputs": "true",
              "derived_from_task": "minimap2"
            },
            {
              "derived_from_filekey": "reference_genome",
              "derived_from_inputs": "true",
              "derived_from_task": "minimap2"
            }
          ],
          "file_format": "bam",
          "filekey": "bam",
          "output_type": "unfiltered alignments",
          "quality_metrics": [
            "long_read_rna_mapping"
          ]
        }
      ],
      "wdl_task_name": "minimap2"
    },
    {
      "dcc_step_run": "/analysis-steps/long-read-rna-seq-filtering-step-v-1/",
      "dcc_step_version": "/analysis-step-versions/long-read-rna-seq-filtering-step-v-1-0/",
      "wdl_files": [
        {
          "derived_from_files": [
            {
              "derived_from_filekey": "bam",
              "derived_from_task": "minimap2"
            },
            {
              "derived_from_filekey": "reference_genome",
              "derived_from_inputs": "true",
              "derived_from_task": "transcriptclean"
            },
            {
              "derived_from_filekey": "splice_junctions",
              "derived_from_inputs": "true",
              "derived_from_task": "transcriptclean"
            },
            {
              "allow_empty": true,
              "derived_from_filekey": "variants",
              "derived_from_inputs": "true",
              "derived_from_task": "transcriptclean"
            }
          ],
          "file_format": "bam",
          "filekey": "corrected_bam",
          "output_type": "alignments",
          "quality_metrics": []
        }
      ],
      "wdl_task_name": "transcriptclean"
    },
    {
      "dcc_step_run": "/analysis-steps/long-read-rna-seq-quantification-step-v-1/",
      "dcc_step_version": "/analysis-step-versions/long-read-rna-seq-quantification-step-v-1-0/",
      "wdl_files": [
        {
          "derived_from_files": [
            {
              "derived_from_filekey": "annotation_gtf",
              "derived_from_inputs": "true",
              "derived_from_task": "init_talon_db"
            },
            {
              "derived_from_filekey": "corrected_bam",
              "derived_from_task": "transcriptclean"
            }
          ],
          "file_format": "tsv",
          "filekey": "talon_abundance",
          "output_type": "transcript quantifications",
          "quality_metrics": [
            "long_read_rna_quantification",
            "long_read_rna_correlation"
          ]
        }
      ],
      "wdl_task_name": "create_abundance_from_talon_db"
    },
    {
      "dcc_step_run": "/analysis-steps/long-read-rna-seq-quantification-step-v-1/",
      "dcc_step_version": "/analysis-step-versions/long-read-rna-seq-quantification-step-v-1-0/",
      "wdl_files": [
        {
          "derived_from_files": [
            {
              "derived_from_filekey": "annotation_gtf",
              "derived_from_inputs": "true",
              "derived_from_task": "init_talon_db"
            },
            {
              "derived_from_filekey": "corrected_bam",
              "derived_from_task": "transcriptclean"
            }
          ],
          "file_format": "gtf",
          "filekey": "gtf",
          "output_type": "transcriptome annotations",
          "quality_metrics": []
        }
      ],
      "wdl_task_name": "create_gtf_from_talon_db"
    }
  ]
}
"""

@pytest.fixture
def ok_response():
    r = Response()
    r.status_code = 200
    return r

def test_path_to_json():
    x = AccessionSteps("path")
    assert x.path_to_json == "path"

@patch("builtins.open", return_value=StringIO(LONG_RNA_STEPS))
def test_steps(mock_open):
    x = AccessionSteps("path")
    assert x.content
    assert x.content[0]["dcc_step_run"] == "/analysis-steps/long-read-rna-seq-alignments-step-v-1/"

@patch("requests.get")
@patch("accession.analysis.Analysis")
def test_accession(mock_analysis, mock_get):
    r = Response()
    r.status_code = 200
    r.json = lambda: {"user": {"@id": "pertti"}}
    mock_get.return_value = r
    steps = AccessionSteps("path")
    steps._steps = {"accession.steps": "foo"}
    x = Accession(steps, mock_analysis, Connection("server"), "lab", "award")


