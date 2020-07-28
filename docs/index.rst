
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

| This is an output of a pipeline analysis run. This can either be an actual JSON file
  or a Caper workflow ID/label. To use Caper IDs you must have set up access to a Caper
  server on the machine you are running ``accession`` from. For details on configuring
  this, see :ref:`installation`. For details about metadata,
  `Cromwell documentation <https://cromwell.readthedocs.io/en/stable/api/RESTAPI/#workflowmetadataresponse>`_

Server
------

``prod`` and ``dev`` indicate the server where the files are being accessioned to. ``dev`` points to `<https://test.encodedcc.org>`_. The server parameter can be explicitly passed as ``test.encodedcc.org`` or ``encodeproject.org``.

Lab and Award
-------------
| These are unique identifiers that are expected to be already present on the ENCODE
  Portal. It is recommended to specify them as the environment variables ``DCC_LAB`` and
  ``DCC_AWARD``, respectively. However, you may also specify them on the command line
  using the ``--lab`` and ``--award`` flags. Specifying these parameters with flags will
  take override any values in your environment. The values correspond to the lab and
  award identifiers given by the ENCODE portal, e.g. ``/labs/foo/`` and ``U00HG123456``.

| To set these variables in your environment, run the following two commands in your
  shell. You may wish to add these to your ``~/.bashrc``, ``~/.bash_profile``,
  ``~/.zshrc``, or similar to configure them for your shell so you don't need to set
  them every time.

.. code-block:: console

    $ export DCC_LAB=XXXXXXXX
    $ export DCC_AWARD=yyyyyyyyyyy

Pipeline Type
-------------

| Use the ``--pipeline-type`` argument to identify the pipeline type to be
  accessioned, for instance ``mirna``. This name is used to identify the appropriate
  steps JSON to use as the accessioning template, so if you use ``mirna`` as above the
  code will look for the corresponding template at ``accession_steps/mirna_steps.json``.

Dry Run
-------

| The ``--dry-run`` flag can be used to determine if any files that would be accessioned
  have md5sums matching those of files already on the portal. When this flag is
  specified, nothing will be accessioned, and log messages will be printed indicating
  files from the WDL metadata with md5 matches on the portal. Specifying this flag
  overrides the ``--force`` option, as such nothing will be accessioned if both flags
  are specified.

Force Accessioning of MD5-Identical Files
-------

| The ``-f/--force`` flag can be used to force accessioning even if there are
  md5-identical files already on the portal. The default behavior is to not accession
  anything if md5 duplicates are detected.

Logging Options
----------------

| The `--no-log-file` flag and `--log-file-path` argument allow for some control over
  the accessioning code logging. `--no-log-file` will always skip logging to a file,
  even if a log file path is specified. The code will log to stdout in either case.
  `--log-file-path` defaults to `accession.log`. Log files are always appended to, never
  overwritten.

Accession Steps Template Format
===============================

Accession Steps
---------------

| The accession steps JSON file specifies the task and file names in the output metadata
  JSON and the order in which the files and metadata will be submitted. Accessioning
  code will selectively submit the specified files to the ENCODE Portal. You can find
  the appropriate accession steps for your pipeline run `here <https://github.com/ENCODE-DCC/accession/tree/master/accession_steps>`_

A single step is configured in the following way:

.. code-block:: javascript

    {
        "dcc_step_version": "/analysis-step-versions/kundaje-lab-atac-seq-trim-align-filter-step-v-1-0/",
        "dcc_step_run": "atac-seq-trim-align-filter-step-run-v1",
        "requires_replication": "true",
        "wdl_task_name": "filter",
        "wdl_files": [
            {
              "callbacks": ["maybe_preferred_default"]
              "filekey": "nodup_bam",
              "output_type": "alignments",
              "file_format": "bam",
              "quality_metrics": ["cross_correlation", "samtools_flagstat"],
              "derived_from_files": [
                {
                  "derived_from_task": "trim_adapter",
                  "derived_from_filekey": "fastqs",
                  "derived_from_inputs": true,
                  "disallow_tasks": ["crop"]
                }
              ]
            }
        ]
    }

``dcc_step_version`` and ``dcc_step_run`` must exist on the portal.

``requires_replication`` indicates that a given step and files should only be accessioned if the experiment is replicated.

``wdl_task_name`` is the name of the task that has the files to be accessioned.

``wdl_files`` specifies the set of files to be accessioned.

``filekey`` is a variable that stores the file path in the metadata file.

``output_type``, ``file_format``, and ``file_format_type`` are ENCODE specific metadata that are required by the Portal

``quality_metrics`` is a list of methods that will be called in during the accessioning to attach quality metrics to the file

``callbacks`` is an array of strings referencing methods of the appropriate ``Accession`` subclass. This can be used to change or add arbitrary properties on the file.

``derived_from_files`` specifies the list of files the current file being accessioned derives from. The parent files must have been accessioned before the current file can be submitted.

``derived_from_inputs`` is used when indicating that the parent files were not produced during the pipeline analysis. Instead, these files are initial inputs to the pipeline. Raw fastqs and genome references are examples of such files.

``derived_from_output_type`` is required in the case the parent file has a possible duplicate.

``disallow_tasks`` can be used to tell the accessioning code not to search particular branches of the workflow digraph when searching up for parent files. This is useful for situations where the workflow exhibits a diamond dependency leading to unwanted files in the ``derived_from``.

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
