import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("poetry_token", [None, "", "poetry-secret"])
@pytest.mark.parametrize("uv_token", [None, "uv-secret"])
def test_make_push_token_priority_and_fallback(
    tmp_path: Path, poetry_token: str | None, uv_token: str | None
) -> None:
    project_root = Path(__file__).resolve().parents[1]
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "if sys.argv[1] == 'build':\n"
        "    pathlib.Path(sys.argv[3], 'fake.whl').touch()\n"
        "elif sys.argv[1] == 'publish':\n"
        "    pathlib.Path(os.environ['UV_RECORD']).write_text(json.dumps({\n"
        "        'args': sys.argv[1:],\n"
        "        'token': os.environ.get('UV_PUBLISH_TOKEN'),\n"
        "    }))\n"
        "else:\n"
        "    sys.exit(1)\n"
    )
    fake_uv.chmod(0o755)
    record = tmp_path / "publish.json"
    env = os.environ.copy()
    env.update(PATH=f"{tmp_path}{os.pathsep}{env['PATH']}", UV_RECORD=str(record))
    for name, value in (
        ("POETRY_PYPI_TOKEN_PYPI", poetry_token),
        ("UV_PUBLISH_TOKEN", uv_token),
    ):
        env.pop(name, None)
        if value is not None:
            env[name] = value

    result = subprocess.run(
        ["make", "-o", "check", "push"],
        cwd=project_root,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    published = json.loads(record.read_text())
    assert published["token"] == (poetry_token or uv_token)
    assert published["args"][0] == "publish"
    assert len(published["args"]) == 2
    assert published["args"][1].endswith("/fake.whl")
    for secret in ("poetry-secret", "uv-secret"):
        assert secret not in result.stdout + result.stderr
        assert all(secret not in arg for arg in published["args"])
