==============
accession
==============

.. image:: https://img.shields.io/badge/code%20style-black-000000.svg
    :target: https://github.com/ambv/black
    :alt: Code Style: Black

.. image:: https://img.shields.io/badge/License-MIT-blue.svg
   :target: https://lbesson.mit-license.org/
   :alt: License: MIT

.. image:: https://circleci.com/gh/ENCODE-DCC/accession.svg?style=svg
    :target: https://circleci.com/gh/ENCODE-DCC/accession
    :alt: CircleCI status

.. short-intro-begin

``accession`` is a Python module and command line tool for submitting genomics pipeline analysis output files and metadata to the ENCODE Portal.

.. _installation:

Installation
=============

Note: intallation requires Python >= 3.6

.. code-block:: console

    $ pip install accession

Next, provide your API keys from the ENCODE portal:

.. code-block:: console

    $ export DCC_API_KEY=XXXXXXXX
    $ export DCC_SECRET_KEY=yyyyyyyyyyy

| It is highly recommended to set the DCC_LAB and DCC_AWARD environment variables for
  ease of use. These correspond to the lab and award identifiers given by the ENCODE
  portal, e.g. ``/labs/foo/`` and ``U00HG123456``, respectively.

.. code-block:: console

    $ export DCC_LAB=XXXXXXXX
    $ export DCC_AWARD=yyyyyyyyyyy

| If you are accessioning workflows produced using the
  `Caper <https://github.com/ENCODE-DCC/caper>`_ local backend, then installation is
  complete. However, if using WDL metadata from pipeline runs on Google Cloud, you will
  also need to authenticate with Google Cloud. Run the following two commands and follow
  the prompts:

.. code-block:: console

    $ gcloud auth login --no-launch-browser
    $ gcloud auth application-default login --no-launch-browser

| If you would like to be able to pass Caper workflow IDs or labels you will
  need to configure access to the Caper server. If you are invoking ``accession`` from
  a machine where you already have a Caper set up, and you have the Caper configuration
  file available at ``~/.caper/default.conf``, then there is no extra setup required.
  If the Caper server is on another machine, you will need so configure HTTP access to
  it by setting the ``hostname`` and ``port`` values in the Caper conf file.

| (Optional) Finally, to enable using Cloud Tasks to upload files from Google Cloud
  Storage to AWS S3, set the following two environment variables. If one or more of them
  is not set, then files will be uploaded using the same machine that the accessioning
  code is run from. For more information on how to set up Cloud Tasks and the upload
  service, see the docs for the `gcs-s3-transfer-service <https://github.com/ENCODE-DCC/gcs-s3-transfer-service/>`_

.. code-block:: console

    $ export ACCESSION_CLOUD_TASKS_QUEUE_NAME=my-queue
    $ export ACCESSION_CLOUD_TASKS_QUEUE_REGION=us-west1

Usage
======

.. code-block:: console

    $ accession -m metadata.json \
                -p mirna \
                -s dev

Please see the `docs <https://accession.readthedocs.io/en/latest/#detailed-argument-description>`_ for greater detail on these input parameters.

Deploying on Google Cloud
=========================

| First authenticate with Google Cloud via `gcloud auth login` if needed. Then install
  the API client with `pip install google-api-python-client`, it is recommended to do
  this inside of a `venv`. Finally, create the firewall rule and deploy the instance by
  running `python deploy.py --project $PROJECT`. This will also install the `accession`
  package. Finally, SSH onto the new instance and run `gcloud auth login` to
  authenticate on the instance.

| For Caper integration, once the instance is up, SSH onto it and create the Caper conf
  file at `~/.caper/default.conf`, use the private IP of the Caper VM instance as the
  `hostname` and use `8000` for the `port`. For the connection to work the Caper VM
  will need to have the tag `caper-server`. Also note that the deployment assumes the
  Cromwell server port is set to `8000`.

.. short-intro-end

Project Information
====================

``accession`` is released under the `MIT <https://choosealicense.com/licenses/mit/>`_ license, documentation lives in `readthedocs <https://accession.readthedocs.io/en/latest/>`_, code is hosted on `github <https://github.com/ENCODE-DCC/accession>`_ and the releases on `PyPI <https://pypi.org/project/accession/>`_.
