======================================
Developer Guidelines
======================================

Pull Request (PR) Guidelines
======================================

Every PR should have a corresponding JIRA ticket, and the name of the PR should have the ticket number as the first thing in its title, e.g. ``PIP-123 accession things``. PRs can have as many commits as you like, they will be squashed when merging into ``dev`` anyway. Your PR must pass on CircleCI, otherwise it will not be reviewed.

Local Development Environment
======================================

The following instructions are copied from `attrs <https://github.com/python-attrs/attrs/blob/master/.github/CONTRIBUTING.rst#local-development-environment>`_

**You can (and should) run our test suite** using ``tox``:

.. code-block:: bash

    $ tox

However, you’ll probably want a more traditional environment as well.
We highly recommend to develop using the latest Python 3 release because ``accession`` tries to take advantage of modern features whenever possible.

First create a `virtual environment <https://virtualenv.pypa.io/>`_.
It’s out of scope for this document to list all the ways to manage virtual environments in Python, but if you don’t already have a pet way, take some time to look at tools like `pew <https://github.com/berdario/pew>`_, `virtualfish <https://virtualfish.readthedocs.io/>`_, and `virtualenvwrapper <https://virtualenvwrapper.readthedocs.io/>`_.

Next, get an up to date checkout of the ``accession`` repository:

.. code-block:: bash

    $ git clone git@github.com:ENCODE-DCC/accession.git

or if you want to use git via ``https``:

.. code-block:: bash

    $ git clone https://github.com/ENCODE-DCC/accession.git

Change into the newly created directory and **after activating your virtual environment** install an editable version of ``accession`` along with its tests and docs requirements:

.. code-block:: bash

    $ cd accession
    $ pip install -e '.[dev]'

At this point,

.. code-block:: bash

   $ python -m pytest

should work and pass, as should:

.. code-block:: bash

   $ cd docs
   $ make html

The built documentation can then be found in ``docs/_build/html/``.

To avoid committing code that violates our style guide, we strongly advise you to install `pre-commit <https://pre-commit.com/>`_ [#f1]_ hooks:

.. code-block:: bash

   $ pre-commit install

You can also run them anytime (as our tox does) using:

.. code-block:: bash

   $ pre-commit run --all-files


.. [#f1] pre-commit should have been installed into your virtualenv automatically when you ran ``pip install -e '.[dev]'`` above. If pre-commit is missing, it may be that you need to re-run ``pip install -e '.[dev]'``.

Building and Running Docker Images
======================================

The docker images for `encoded <https://github.com/ENCODE-DCC/encoded>`_ are parametrized by the branch name or release tag, e.g. ``ENCD-1234-foo-bar`` or ``v90.0``. To build it manually, run the following commands (relative to the repo root):

.. code-block:: bash

   $ docker build . -f docker/Dockerfile -t [IMAGE TAG] --build-arg ENCODED_RELEASE_TAG=[TAG OR BRANCH]

To run the local app, map your desired host port (must not be in use, here using 8000) to port 8000 of the container:

.. code-block:: bash

   $ docker run -d -p 8000:8000 encoded-docker:test

Writing tests
======================================

You should always write tests whenever adding new code, or potentially update tests if
you modify code. Throughout the repo's test suite in the ``/tests`` folder you can find
examples of different uses of mocking that you can use to help write your own tests.

Integration tests are more complicated to assemble, but there is infrastructure in place
to make them easier to write, although they still require adding a lot of data to
the repo. The required pieces of data are listed below, assuming you already have a
Cromwell pipeline run:

1. Get the Cromwell metadata json file, and put it in the ``tests/data`` folder

2. Add the base64-encoded md5sums for each ``gs://`` file in the metadata json to the
``tests/data/gcloud_md5s.json`` file. You can obtain these with ``gsutil hash``. The
following command will parse the metadata and give you the ``gsutil`` output for each
unique object.

.. code-block:: bash

   $ cat tests/data/mirna_replicated_metadata.json | tr -s ' ' | tr ' ' '\n' | tr -d ',' | egrep "^\"gs://" | sort | uniq | grep "\." | xargs gsutil hash > hashes.txt

You will then need to encode this as JSON in the aforementioned file. Here is some Python
that will print out file: md5sum entries you can just copy-paste into the JSON.
**IMPORTANT** try not to duplicate keys in this JSON file. While it is techincally valid
and wouldn't be caught by either Python or the ``pre-commit`` hooks, it could be very
confusing for someone looking in the file. Using a proper JSON linter will tell you if
duplicate keys exist.

.. code-block:: python

   with open("hashes.txt") as f:
       data = f.readlines()

   buffer = []
   for i, line in enumerate(data):
       if (i - 1) % 3 == 0:
           continue
       elif i % 3 == 0:
           x = line.split(' for ')[-1].strip().rstrip(':')
           buffer.append(f'"gs://encode-processing/{x}"')
       elif (i + 1) % 3 == 0:
           y = line.split('(md5):')[-1].strip()
           buffer.append(f'"{y}",')
       if len(buffer) == 2:
           print(": ".join(buffer))
           buffer = []

3. Download and add any QC JSON files from the metadata to the ``tests/data/files`` folder.

4. Add the appropriate test inserts to the ``tests/data/inserts folder``. For any given
experiment, you will likely need to add experiment, replicate, library, file, biosample,
donor, biosample_type, lab, and award inserts. You need only to add raw files (fastqs)
and reference files. If you are testing a new assay, you will also need to add
analysis_step_version, analysis_step, software_version, and software inserts. The
easiest way to add them is to get the JSON from `the portal <https://www.encodeproject.org>`
with ``frame=edit``, copy that JSON into the the insert, and then copy the UUID from the
portal into the insert as well. You will want to replcace any "user" properties with the
dummy user in the inserts, see them for examples. I also delete any instances of the
``documents`` property to avoid needing to add them to the inserts, they don't affect
the accessioning.

You will need to rebuild the docker image in order to add the inserts to the local test
server. You may see errors loading the test data when starting the container, you can
see the exact errors by looking at the container logs. You can then fix the inserts and
rebuild.

5. Add the expected results to the ``tests/data/validation/{ASSAY}/files.json`` file.
If you already have an accessioned example on a demo, you can simply GET the files
with ``frame=embedded`` and copy-paste them into the validation JSON. The frame
parameter is important, and saves us from needing separate validation files for the
analysis_step_runs and quality_metrics. You will need to put the reference files in
there as well, if they aren't there already (those are OK to use ``frame=object``).
6. That's a lot of data to manage. Fortunately, writing the tests should be very simple.
The ``accessioner_factory`` fixture will take care of setup and teardown of the test,
including the test's Docker container. Here is an example of a microRNA test:

.. code-block:: python

   def test_accession_mirna_unreplicated(accessioner_factory):
       factory = accessioner_factory(
           metadata_file="mirna_unreplicated_metadata.json", assay_name="mirna"
       )
       accessioner, expected_files = next(factory)
       accessioner.accession_steps()
       validate_accessioning(
           accessioner, expected_files, expected_num_files=6, dataset="ENCSR543MWW"
       )

Here, validate_accessioning is just a function that takes care of all the assertions,
and can be reused by your tests as well. expected_num_files is the number of new files
that you expect the accessioning to post.
