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
