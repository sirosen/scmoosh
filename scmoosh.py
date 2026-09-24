import hashlib
import json
import sys
import typing as t
import urllib.parse
from collections import deque

import referencing
import referencing.retrieval
import requests


@referencing.retrieval.to_cached_resource()
def _cached_retrieve_uri(uri: str) -> str:
    return requests.get(uri).text


class ScmooshMap:
    PREFIX = "SCMOOSHED"

    def __init__(self) -> None:
        self._map: dict[str, referencing.Resource] = {}
        self._keymap: dict[str, str] = {}

    def add(self, uri: str, resource: referencing.Resource) -> None:
        self._map[uri] = resource

        uri_hash = hashlib.md5(uri.encode()).hexdigest()
        self._keymap[uri] = f"{self.PREFIX}:{uri_hash}"

    def __contains__(self, key: str) -> bool:
        return key in self._map

    def render(self, root_uri: str) -> dict[str, t.Any]:
        root_key = self._keymap[root_uri]
        root_doc = self._map[root_uri].contents
        root_doc.pop("$id", None)

        # map all definitions (including the root doc)
        result: dict[str, t.Any] = {"definitions": {}}
        for uri, resource in self._map.items():
            key = self._keymap[uri]
            result["definitions"][key] = resource.contents

        # having mapped everything, traverse the object again, this time with the goal
        # of replacing any $ref entries
        # in the process, also strip out any `$id` values
        to_update = deque(result["definitions"].items())
        while to_update:
            defn_base, doc = to_update.popleft()
            if not isinstance(doc, (dict, list)):
                continue

            if isinstance(doc, list):
                to_update.extend((defn_base, sub) for sub in doc)
                continue

            # dict case
            doc.pop("$id", None)
            if (ref := doc.get("$ref")) is not None:
                if ref.startswith("#"):
                    new_ref = f"#/definitions/{defn_base}/{ref[1:].lstrip('/')}"
                else:
                    uri, fragment = urllib.parse.urldefrag(ref)
                    if fragment:
                        new_ref = (
                            f"{self._keymap[uri].rstrip('/')}/{fragment.lstrip('/')}"
                        )
                    else:
                        new_ref = self._keymap[uri]
                    new_ref = f"#/definitions/{new_ref}"
                doc["$ref"] = new_ref

            to_update.extend((defn_base, sub) for sub in doc.values())

        # finally, introduce a "$ref" which points to the root doc
        # copy "$schema" from the root if present, as it impacts how the rest of the
        # schema evaluates
        result["$ref"] = f"#/definitions/{root_key}"
        if "$schema" in root_doc:
            result["$schema"] = root_doc["$schema"]
        return result


class Scmoosher:
    DEFINITIONS_KEY = "SCMOOSHED"

    def __init__(self, base_uri: str) -> None:
        self.docs = ScmooshMap()
        self.base_uri = base_uri

    def _retrieve_uri(self, uri: str) -> referencing.Resource:
        resource = _cached_retrieve_uri(uri)
        self.docs.add(uri, resource)
        return resource

    def walk(self) -> None:
        # type ignore: attrs class features not recognized under 'referencing' usage
        registry = referencing.Registry(
            retrieve=self._retrieve_uri  # type: ignore[call-arg]
        )
        resolver = registry.resolver()
        resolved_root = resolver.lookup(self.base_uri)
        resolver = resolved_root.resolver
        root_contents = resolved_root.contents
        if root_contents is None:
            raise ValueError("Cannot scmoosh a schema whose root is `null`!")

        root = referencing.Resource.from_contents(root_contents)

        # detect the specification at the root, use it throughout
        spec = referencing.Specification[dict[str, t.Any]].detect(root_contents)

        # track refs we've already resolved
        seen: set[tuple[str, str]] = set()

        unresolved = deque([(self.base_uri, resolver, root)])
        while unresolved:
            base_uri, resolver, current = unresolved.popleft()

            if isinstance(current.contents, dict) and isinstance(
                ref := current.contents.get("$ref"), str
            ):
                # copied out of Resolver.lookup() to let us get the exact URI which will
                # be used
                if ref.startswith("#"):
                    uri, fragment = base_uri, ref[1:]
                else:
                    uri, fragment = urllib.parse.urldefrag(
                        urllib.parse.urljoin(base_uri, ref)
                    )
                if (uri, fragment) in seen:
                    continue
                seen.add((uri, fragment))

                resolved = resolver.lookup(ref)
                new_resource = referencing.Resource.from_contents(
                    resolved.contents, default_specification=spec
                )
                unresolved.append((uri, resolved.resolver, new_resource))
            else:
                unresolved.extend(
                    (base_uri, resolver.in_subresource(sub), sub)
                    for sub in current.subresources()
                )

    def render(self) -> dict[str, t.Any]:
        return self.docs.render(self.base_uri)


def scmoosh(uri: str) -> t.Any:
    s = Scmoosher(uri)
    s.walk()
    return s.render()


def main(argv: list[str] | None = None, /) -> None:
    if argv is None:
        argv = sys.argv[1:]
    base_uri = argv[0]

    print(json.dumps(scmoosh(base_uri), indent=2, separators=(",", ": ")))


if __name__ == "__main__":
    import os

    os.makedirs("samples", exist_ok=True)
    with open("samples/.gitignore", "w") as fp:
        fp.write("*")

    with open("sample_targets.txt") as fp:
        data = [
            (split[0].strip(), split[2].strip())
            for x in fp
            if (split := x.partition(":"))
        ]

    for name, uri in data:
        print(f"smooshing {name} -- {uri}")
        data = scmoosh(uri)
        with open(f"samples/{name}.json", "w") as fp:
            json.dump(data, fp, separators=(",", ":"))
