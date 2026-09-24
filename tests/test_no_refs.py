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
    s.walk()
    result = s.render()

    assert "$ref" in result
    def_key = result["$ref"].split("/")[-1]
    assert result == {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$ref": f"#/definitions/{def_key}",
        "definitions": {
            def_key: {"$schema": "https://json-schema.org/draft/2020-12/schema"},
        },
    }
