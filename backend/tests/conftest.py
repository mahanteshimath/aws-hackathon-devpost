import os
import sys
import tempfile
from pathlib import Path

# Configure an isolated mock environment before the app modules load.
_TMP = tempfile.mkdtemp(prefix="crayon-test-")
os.environ.update(
    {
        "CRAYON_MODE": "mock",
        "CRAYON_STORAGE": "local",
        "CRAYON_DATA_DIR": _TMP,
        "GUARDRAIL_ID": "",
        "AGENTCORE_RUNTIME_ARN": "",
        "AGENTCORE_MEMORY_ID": "",
        "CRAYON_PUBLIC_URL": "http://tv.test",
    }
)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
