#! /bin/bash
set -euo pipefail

VERSION="${1}"
INIT_PY="accession/__init__.py"

echo "${VERSION}" | grep -qP "^\d{1,3}\.\d{1,2}\.\d{1,2}$" || echo "Version is not in correct format, should be something like 1.2.3 or 123.4.56" && exit 1

CURRENT_VERSION=$(grep __version__ ${INIT_PY} | tr -d '"' | awk '{print $3}')
if [[ ! "${CURRENT_VERSION}" < "${VERSION}" ]]; then
    echo "Specified version ${VERSION} is not higher than than the current version ${CURRENT_VERSION}"
    exit 1
fi

BRANCH="v${VERSION}"

git checkout -b "${BRANCH}"

echo "Updating version in ${INIT_PY}"
sed "/__version__/s/\".*\"/\"${VERSION}\"/" "${INIT_PY}"
git add "${INIT_PY}"

echo "Commiting changes and adding tag"
git commit -m "update to ${VERSION}"
git tag "${VERSION}"


echo "Pushing branch to remote"
git push -u origin "${BRANCH}"
# open $(git push -u origin "${BRANCH}" 2>&1 | grep "https" | awk '{ print $2 }')
git push --tags

echo "Uploading to PyPI, will prompt for username and password"
python setup.py sdist bdist_wheel && python -m twine upload --skip-existing dist/*

echo "Creating PR against dev on GitHub"
PR_URL=$(curl -s \
    -X POST \
    -H "Accept: application/vnd.github.v3+json" \
    https://api.github.com/repos/ENCODE-DCC/accession/pulls \
    -d "{\"title\":\"update to ${VERSION}\",\"head\":\"v${VERSION}\",\"base\":\"dev\"}" \
    | jq -r .url)

echo "Squash merging PR into dev on GitHub"
curl \
    -X PUT \
    -H "Accept: application/vnd.github.v3+json" \
    "${PR_URL}/merge" \
    -d "{\"commit_title\":\"update to ${VERSION}\",\"merge_method\":\"squash\"}"

echo "Creating draft release on GitHub"
BODY_TEMPLATE="##New Features\n*\n*\n\n##Bugfixes\n*\n*\n\n"
curl \
    -X POST \
    -H "Accept: application/vnd.github.v3+json" \
    https://api.github.com/repos/ENCODE-DCC/accession/releases \
    -d "{\"tag_name\":\"${VERSION}\",\"draft\":true,\"name\":\"Release version ${VERSION}\",\"body\":\"${BODY_TEMPLATE}\"}"

echo "All done. Make sure to fill out and publish the draft release on Github."
