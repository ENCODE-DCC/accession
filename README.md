# accession
Python module and command line tool to submit genomics pipeline analysis output files and metadata to the ENCODE Portal

Table of Contents
=================

  * [Installation](#installation)
  * [Setting environmental variables](#setting-environmental-variables)
  * [Usage](#usage)
  * [Arguments](#arguments)
  
# Installation
Install the module with pip:

    $ pip install accession
    
# Setting environmental variables
You will need ENCODE DCC credentials from the ENCODE Portal. Set them in your command line tool like so:

    $ export DCC_API_KEY=XXXXXXXX
    $ export DCC_SECRET_KEY=yyyyyyyyyyy
    
You will also need [Google Application Credentials](https://cloud.google.com/video-intelligence/docs/common/auth#set_up_a_service_account) in your environment. Obtain and set your service account credentials:

    $ export GOOGLE_APPLICATION_CREDENTIALS=<path_to_service_account_file>
    
# Usage

    $ accession --accession-metadata metadata.json \
                --accession-steps steps.json \
                --server dev
                --lab /labs/encode-processing-pipeline/ \
                --award U41HG007000
                
# Arguments
### Metadata JSON
This file is an output of pipeline analysis run. [The example file](https://github.com/ENCODE-DCC/accession/blob/master/tests/data/ENCSR609OHJ_metadata_2reps.json) has metadata on all of the tasks and produced files.
### Accession Steps
The accessioning steps [configuration file](https://github.com/ENCODE-DCC/accession/blob/master/tests/data/atac_input.json) specifies the task and file names in the output metadata JSON. Accessioning code will selectively submit the specified file keys to the ENCODE DCC Portal. Single step is configured in the following way:

    {
            "dcc_step_version":     "/analysis-step-versions/kundaje-lab-atac-seq-trim-align-filter-step-v-1-0/",
            "dcc_step_run":         "atac-seq-trim-align-filter-step-run-v1",
            "wdl_task_name":        "filter",
            "wdl_files":            [
                {
                    "filekey":                  "nodup_bam",
                    "output_type":              "alignments",
                    "file_format":              "bam",
                    "quality_metrics":          ["cross_correlation", "samtools_flagstat"],
                    "derived_from_files":       [{
                        "derived_from_task":        "trim_adapter",
                        "derived_from_filekey":     "fastqs",
                        "derived_from_inputs":      "true"
                    }]
                }
            ]
    }

`dcc_step_version` and `dcc_step_run` must exist on the portal.

`wdl_task_name` is the name of the task that has the files to be accessioned.

`wdl_files` specifies the set of files to be accessioned.

`filekey` is the variable that stores the file path in the metadata file.

`output_type`, `file_format`, and `file_format_type` are the ENCODE specific metadata that are required by the Portal

`quality_metrics` is a list of methods that will be called in the code to attach quality metrics to a file

`possible_duplicate` specifies that there could be, in the case of optimal IDR peaks and conservative IDR peaks, files can have an identical content. If the possible duplicate flag is set, file is not accessioned.

`derived_from_files` specifies the list of files the current file being accessioned derives from. These files need to have been accessioned before the current file can be submitted. 

`derived_from_inputs` is used when indicating that parent files were not produced during the task execution. Raw fastqs and genome references are examples of such files.

`derived_from_output_type` is required in the case the parent file has a possible duplicate.

### Server
`prod` and `dev` indicates the server where the files are being accessioned to. `dev` points to test.encodedcc.org. The server parameter can be explicitly passed as test.encodedcc.org or encodeproject.org.

### Lab and Award
These are unique identifiers that are expected to be already present on the ENCODE Portal.


