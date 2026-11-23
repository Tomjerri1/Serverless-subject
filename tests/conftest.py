import os
import sys

os.environ.setdefault("TABLE_NAME", "test-table")
os.environ.setdefault("AWS_DEFAULT_REGION", "eu-north-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))