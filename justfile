version := `uvx mddj read version`

build:
    uv build

check-sdist:
    uvx --from='check-sdist==1.3.1' check-sdist --inject-junk

publish: build
    uvx flit publish

tag-release:
    git tag -s "{{version}}" -m "v{{version}}"

clean:
	rm -rf dist build *.egg-info .tox .venv
	find . -type d -name '__pycache__' -exec rm -r {} +
