import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--docker",
        action="store",
        default="",
        help=(
            "Docker image to use for local encoded server in tests, e.g. quay.io/encode"
            "-dcc/accession:v80.0"
        ),
    )


@pytest.fixture(scope="session")
def encoded_docker_image(request):
    return request.config.getoption("--docker")
