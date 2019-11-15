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

.. code-block:: console

    $ pip install accession

In addition to installing the module, make sure to provide your API keys from the ENCODE portal:

.. code-block:: console

    $ export DCC_API_KEY=XXXXXXXX
    $ export DCC_SECRET_KEY=yyyyyyyyyyy

You will also need `Google Application Credentials <https://cloud.google.com/video-intelligence/docs/common/auth#set_up_a_service_account/>`_ in your environment. Obtain and set your service account credentials:

.. code-block:: console

    $ export GOOGLE_APPLICATION_CREDENTIALS=<path_to_service_account_file>

Usage
======

.. code-block:: console

    $ accession --accession-metadata metadata.json \
                --accession-steps steps.json \
                --server dev \
                --lab /labs/my-lab/ \
                --award U00HG123456

Please see the `docs <https://https://accession.readthedocs.io/en/latest/#detailed-argument-description>`_ for greater detail on these input parameters.

.. short-intro-end

Project Information
====================

``accession`` is released under the `MIT <https://choosealicense.com/licenses/mit/>`_ license, documentation lives in `readthedocs <https://accession.readthedocs.io/en/latest/>`_, code is hosted on `github <https://github.com/ENCODE-DCC/accession>`_ and the releases on `PyPI <https://pypi.org/project/accession/>`_.
