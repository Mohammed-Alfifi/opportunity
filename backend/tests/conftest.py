import os
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DATA_DIR"] = _tmp
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["LLM_PROVIDER"] = "none"
os.environ["SMTP_USER"] = "me@example.org"
os.environ["SMTP_PASSWORD"] = "x"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app, headers={"x-forsa-client": "web"}) as c:
        yield c
