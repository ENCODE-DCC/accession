===============
Release Process
===============

The release process is continually evolving. This should only serve as an outline of what needs to be done.

Steps:

1. Cut a release branch from dev, the typical naming convention is ``v[major version].[minor version].[patch]``.
2. Edit the __version__ in __init__.py manually or with ``bump``.
3. Add and commit the version change, push the branch to GitHub, and make a PR against master.
4. Once the tests pass, merge the PR into master. Don't squash!
5. Checkout and pull master, tag it with the version, and run ``git push --tags``.
6. Make a release on GitHub with the changelog.
7. Rebase dev on master and push to resync it.
