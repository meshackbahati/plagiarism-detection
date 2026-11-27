import os
import sys

# Tests run without ML models; integration tests use TEST_DATABASE_URL.
os.environ.setdefault("LIGHTWEIGHT_MODE", "true")
os.environ.setdefault("STORAGE_TYPE", "local")
os.environ.setdefault("ENVIRONMENT", "test")
if os.getenv("TEST_DATABASE_URL"):
    os.environ["DATABASE_URL"] = os.environ["TEST_DATABASE_URL"]

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
