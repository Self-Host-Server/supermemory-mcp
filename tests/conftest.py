"""Dummy env vars so `server.main`'s module-level `app = create_app()` can
construct `Settings()` at import time. pytest imports conftest.py before any
test module, so these are set before `from server.main import create_app`
runs.

Assigned unconditionally, not via setdefault: the suite must never pick up a
developer's real instance URL or API key, so the test environment is
hermetic regardless of what the shell exports.
"""

import os

os.environ["SUPERMEMORY_API_URL"] = "http://backend:6767"
os.environ["SUPERMEMORY_API_KEY"] = "sm_key"
os.environ["SUPERMEMORY_CONTAINER_TAG"] = "test_tag"
