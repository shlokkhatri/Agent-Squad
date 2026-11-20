import os
import shutil
import uuid

import pytest

# app.llm_config refuses to import without a key. Tests never call the LLM,
# so a placeholder is enough (a real key from the environment is kept).
os.environ.setdefault("GEMINI_API_KEY", "test-key-not-used")

from app.tools.repository_tools import WORKSPACE_ROOT  # noqa: E402


@pytest.fixture
def temp_repo():
    """A throw-away repository inside workspace/repositories."""

    name = f"_tmp_test_repo_{uuid.uuid4().hex[:8]}"
    path = WORKSPACE_ROOT / name
    path.mkdir(parents=True)

    yield name, path

    shutil.rmtree(path, ignore_errors=True)
