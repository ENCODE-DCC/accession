===============
Release Process
===============

Prerequisites:

You will need a GitHub personal access token with ``repo`` scope,

Steps:

0. Set the environment variables ``GITHUB_USERNAME`` and ``GITHUB_TOKEN`` to your GitHub username and to your personal token, respectively.
1. Run the script ``release.sh`` from the root of the repo passing the target version.
2. When prompted, enter your PyPI username and password to upload the new version to PyPI.
3. Go to the draft release on GitHub, edit the changelog, and publish.
