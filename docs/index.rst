
======================================
Welcome to accessions's documentation!
======================================

.. include:: ../README.rst
   :start-after: short-intro-begin
   :end-before: short-intro-end


Detailed Argument Description
=============================

Metadata Json
--------------

This file is an output of a pipeline analysis run. For details, see `Cromwell documentation <https://cromwell.readthedocs.io/en/stable/api/RESTAPI/#workflowmetadataresponse>`_

Accession Steps
---------------

The accession steps JSON file specifies the task and file names in the output metadata JSON and the order in which the files and metadata will be submitted. Accessioning code will selectively submit the specified files to the ENCODE Portal. You can find the appropriate accession steps for your pipeline run `here <https://github.com/ENCODE-DCC/accession/tree/master/accession_steps>`_

A single step is configured in the following way:

.. code-block:: javascript

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

``dcc_step_version`` and ``dcc_step_run`` must exist on the portal.

``wdl_task_name`` is the name of the task that has the files to be accessioned.

``wdl_files`` specifies the set of files to be accessioned.

``filekey`` is a variable that stores the file path in the metadata file.

``output_type``, ``file_format``, and ``file_format_type`` are ENCODE specific metadata that are required by the Portal

``quality_metrics`` is a list of methods that will be called in during the accessioning to attach quality metrics to the file

``possible_duplicate`` indicates that there could be files that have an identical content. If the ``possible_duplicate`` flag is set and the current file being accessioned has md5sum that's identical to the md5sum of another file in the same task, the current file will not be accessioned. Optimal IDR peaks and conservative IDR peaks are an example set of files that can have an identical md5sum.

``derived_from_files`` specifies the list of files the current file being accessioned derives from. The parent files must have been accessioned before the current file can be submitted.

``derived_from_inputs`` is used when indicating that the parent files were not produced during the pipeline analysis. Instead, these files are initial inputs to the pipeline. Raw fastqs and genome references are examples of such files.

``derived_from_output_type`` is required in the case the parent file has a possible duplicate.

Server
------

``prod`` and ``dev`` indicate the server where the files are being accessioned to. ``dev`` points to `<https://test.encodedcc.org>`_. The server parameter can be explicitly passed as ``test.encodedcc.org`` or ``encodeproject.org``.

Lab and Award
-------------
These are unique identifiers that are expected to be already present on the ENCODE Portal.

Table of Contents
==================

.. toctree::
   :maxdepth: 2

   development
   release
   license
   changelog

Indices and tables
==================

* :ref:`genindex`
* :ref:`search`
