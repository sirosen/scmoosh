import responses

from scmoosh import Scmoosher

SCHEMA_URI = "https://bogus.net/schema.json"


def test_empty_schema() -> None:
    responses.add(
        "GET",
        SCHEMA_URI,
        json={"$schema": "https://json-schema.org/draft/2020-12/schema"},
    )

    s = Scmoosher(SCHEMA_URI)

    result = s.render()

    assert result == {"$schema": "https://json-schema.org/draft/2020-12/schema"}
