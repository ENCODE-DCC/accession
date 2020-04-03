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

Installation
=============

Note: intallation requires Python >= 3.6

.. code-block:: console

    $ pip install accession

Next, provide your API keys from the ENCODE portal:

.. code-block:: console

    $ export DCC_API_KEY=XXXXXXXX
    $ export DCC_SECRET_KEY=yyyyyyyyyyy

You will also need to authenticate with Google Cloud if using WDL metadata from pipeline runs on Google Cloud. Run the following two commands and follow the prompts:

.. code-block:: console

    $ gcloud auth login --no-launch-browser
    $ gcloud auth application-default login --no-launch-browser

| Finally, it is highly recommended to set the DCC_LAB and DCC_AWARD environment
  variables for ease of use. These correspond to the lab and award identifiers given by
  the ENCODE portal, e.g. ``/labs/foo/`` and ``U00HG123456``, respectively.

.. code-block:: console

    $ export DCC_LAB=XXXXXXXX
    $ export DCC_AWARD=yyyyyyyyyyy

Usage
======

.. code-block:: console

    $ accession --accession-metadata metadata.json \
                --pipeline-type mirna \
                --server dev

Please see the `docs <https://accession.readthedocs.io/en/latest/#detailed-argument-description>`_ for greater detail on these input parameters.

.. short-intro-end

Project Information
====================

``accession`` is released under the `MIT <https://choosealicense.com/licenses/mit/>`_ license, documentation lives in `readthedocs <https://accession.readthedocs.io/en/latest/>`_, code is hosted on `github <https://github.com/ENCODE-DCC/accession>`_ and the releases on `PyPI <https://pypi.org/project/accession/>`_.
