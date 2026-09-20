import copy
import hashlib
import json
import sys
import typing as t
import urllib.parse
from collections import deque

import referencing
import referencing.retrieval
import requests
from referencing import Registry, Resource, Specification


@referencing.retrieval.to_cached_resource()
def _cached_retrieve_uri(uri: str) -> str:
    return requests.get(uri).text


class Scmoosher:
    DEFINITIONS_KEY = "SCMOOSHED"

    def __init__(self, base_uri: str) -> None:
        self.new_defs: dict[str, t.Any] = {}
        self.new_defs_keymap: dict[str, str] = {}

        self.base_uri = base_uri
        # type ignore: attrs class features not recognized under 'referencing' usage
        self.registry = Registry(retrieve=self._retrieve_uri)  # type: ignore[call-arg]

        self.root_contents: dict[str, t.Any] | None = None

    def _add_new_def(self, uri: str, resource: Resource) -> None:
        if uri == self.base_uri:
            return

        uri_hash = hashlib.md5(uri.encode()).hexdigest()
        key = f"{self.DEFINITIONS_KEY}-{uri_hash}"
        self.new_defs[key] = resource.contents
        self.new_defs_keymap[uri] = f"#/definitions/{key}"

    def _retrieve_uri(self, uri: str) -> Resource:
        resource = _cached_retrieve_uri(uri)
        self._add_new_def(uri, resource)
        return resource

    def walk(self) -> None:
        resolver = self.registry.resolver()
        resolved_root = resolver.lookup(self.base_uri)
        resolver = resolved_root.resolver
        self.root_contents = resolved_root.contents

        if self.root_contents is None:
            raise ValueError("Cannot scmoosh a schema whose root is `null`!")

        root = Resource.from_contents(self.root_contents)

        # detect the specification at the root, use it throughout
        spec = Specification[dict[str, t.Any]].detect(root.contents)

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
                new_resource = Resource.from_contents(
                    resolved.contents, default_specification=spec
                )
                unresolved.append((uri, resolved.resolver, new_resource))
            else:
                unresolved.extend(
                    (base_uri, resolver.in_subresource(sub), sub)
                    for sub in current.subresources()
                )

    def render(self) -> dict[str, t.Any]:
        if self.root_contents is None:
            self.walk()
        assert self.root_contents is not None

        result: dict[str, t.Any] = copy.deepcopy(self.root_contents)
        if not self.new_defs:
            return result

        # having done so, add definitions (if missing) and extend it with the new
        # scmooshed items
        if "definitions" not in result:
            result["definitions"] = {}
        elif not isinstance(result["definitions"], dict):
            raise ValueError(
                "Cannot scmoosh a schema whose `definitions` are not an object."
            )
        result["definitions"].update(self.new_defs)

        # finally, traverse the object again, this time with the goal of replacing any
        # $ref entries
        to_update = deque([result])
        while to_update:
            current = to_update.popleft()
            if not isinstance(current, (dict, list)):
                continue

            if isinstance(current, list):
                to_update.extend(current)
                continue

            # dict case
            if (ref := current.get("$ref")) is not None:
                if ref in self.new_defs_keymap:
                    current["$ref"] = self.new_defs_keymap[ref]
            to_update.extend(current.values())

        return result


def main(argv: list[str] | None = None, /) -> None:
    if argv is None:
        argv = sys.argv[1:]
    base_uri = argv[0]

    s = Scmoosher(base_uri)
    print(s.new_defs_keymap)
    print(s.new_defs)
    print("---")
    s.walk()
    print("---")
    for k, v in s.new_defs_keymap.items():
        print(k, ":", v)
    # print(s.new_defs)
    print("=== rendered ===")
    print(json.dumps(s.render(), indent=2, separators=(",", ": ")))


if __name__ == "__main__":
    with open("sample_targets.txt") as fp:
        data = [trimmed for x in fp if (trimmed := x.strip())]

    for uri in data:
        print(f"smooshing {uri}")
        main([uri])
