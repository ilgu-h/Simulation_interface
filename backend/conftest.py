"""Root conftest — runs before any test module is collected.

Sets SIM_RUNS_DIR to a temp directory so tests don't pollute the real
runs/ folder, and so registry.py picks it up at import time.
"""

import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="sim-test-")
os.environ["SIM_RUNS_DIR"] = _tmp
