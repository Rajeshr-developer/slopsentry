import pytest

from slopsentry.hook import extract_packages, read_event


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        # each install tool
        ("pip install requests", ["requests"]),
        ("pip3 install requests", ["requests"]),
        ("pip3.12 install requests", ["requests"]),
        (".venv/bin/pip install requests", ["requests"]),
        ("python -m pip install requests", ["requests"]),
        ("python3 -m pip install requests", ["requests"]),
        ("/usr/bin/python3.12 -m pip install requests", ["requests"]),
        ("uv add requests", ["requests"]),
        ("uv pip install requests", ["requests"]),
        ("poetry add requests", ["requests"]),
        # specs resolve to names; duplicates collapse
        ("pip install 'requests[socks]>=2' requests==2.31.0 Requests", ["requests"]),
        ("poetry add requests@^2.31 pytest@latest", ["requests", "pytest"]),
        # chained commands
        ("cd x && pip install a; uv add b | tee log", ["a", "b"]),
        ("pip install a || poetry add b & uv pip install c", ["a", "b", "c"]),
        ("pip install a\npip install b", ["a", "b"]),
        ("echo hi; pip install a", ["a"]),
        # prefixes
        ("sudo pip install a", ["a"]),
        ("sudo -u me pip install a", ["a"]),
        ("FOO=1 BAR=2 pip install a", ["a"]),
        ("env -u X PYTHONPATH=. pip install a", ["a"]),
        # global options before the subcommand
        ("pip --quiet install a", ["a"]),
        ("pip --cache-dir /tmp/c install a", ["a"]),
        ("uv --quiet add a", ["a"]),
        # flags, values, paths and URLs are skipped
        ("pip install -U --no-deps a", ["a"]),
        ("pip install -r reqs.txt -c constraints.txt a", ["a"]),
        ("pip install -e . a", ["a"]),
        ("pip install -e git+https://github.com/x/y.git#egg=y a", ["a"]),
        ("pip install --target dir --prefix /opt a", ["a"]),
        ("pip install ./dir ../pkg ~/pkg /abs/pkg sub/dir a", ["a"]),
        ("pip install dist/pkg-1.0-py3-none-any.whl pkg-1.0.tar.gz a", ["a"]),
        ("pip install https://example.com/pkg.zip git+https://x/y.git a", ["a"]),
        ("pip install 'pkg @ https://example.com/pkg.whl' a", ["a"]),
        ("pip install pkg @ https://example.com/pkg.whl a", ["a"]),
        ("uv add --group dev --optional extra a", ["a"]),
        ("poetry add -G dev --extras socks a", ["a"]),
        ("pip install a > log 2>&1", ["a"]),
        # nothing to check
        ("pip install -e '.[dev]'", []),
        ("pip install -r requirements.txt", []),
        ("pip install $(cat reqs)", []),
    ],
)
def test_extract_packages(command, expected):
    assert extract_packages(command) == expected


@pytest.mark.parametrize(
    "command",
    [
        "pip install --index-url https://my.index/simple a",
        "pip install --index-url=https://my.index/simple a",
        "pip install --extra-index-url https://my.index/simple a",
        "pip install -i https://my.index/simple a",
        "pip install -ihttps://my.index/simple a",
        "pip install -f ./wheels a",
        "pip install --find-links=./wheels a",
        "uv add --index https://my.index/simple a",
        "uv pip install --default-index https://my.index/simple a",
        "poetry add --source private a",
    ],
)
def test_custom_index_skips_command(command):
    assert extract_packages(command) == []


def test_custom_index_only_skips_its_own_command():
    assert extract_packages("pip install -i https://x/simple a && pip install b") == ["b"]


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "pip list",
        "pip uninstall a",
        "pip download a",
        "uv sync",
        "uv run pytest",
        "poetry install",
        "python -m pytest",
        "python script.py install a",
        "npm install left-pad",
        "npx create-something",
        "echo pip install a",
        'pip install "unterminated',
        "",
    ],
)
def test_non_install_commands(command):
    assert extract_packages(command) == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"tool_name": "Bash", "tool_input": {"command": "ls"}}', "ls"),
        ('{"tool_name": "Write", "tool_input": {"command": "ls"}}', None),
        ('{"tool_name": "Bash", "tool_input": {}}', None),
        ('{"tool_name": "Bash", "tool_input": {"command": 3}}', None),
        ('{"tool_name": "Bash", "tool_input": "ls"}', None),
        ("[1, 2]", None),
        ("{not json", None),
        ("", None),
    ],
)
def test_read_event(raw, expected):
    assert read_event(raw) == expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("pip install a # pip install b", ["a"]),
        ("# pip install a\npip install b", ["b"]),
        ("pip install 'git+https://x/y.git#egg=y' a", ["a"]),
    ],
)
def test_comments(command, expected):
    assert extract_packages(command) == expected
