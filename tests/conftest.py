import typing as t

import pytest
import responses


@pytest.fixture(autouse=True)
def mocked_responses() -> t.Iterator[None]:
    """
    All tests enable `responses` patching of the `requests` package, replacing
    all HTTP calls.
    """
    responses.start()

    yield

    responses.stop()
    responses.reset()
