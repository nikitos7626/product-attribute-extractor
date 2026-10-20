import asyncio
import os
import sys
from pathlib import Path

# Ensure repo root and infra directory are in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent.parent
for p in (str(REPO_ROOT), str(SCRIPT_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from scripts.infra.vm_exec import exec_remote
except (ImportError, ValueError):
    from vm_exec import exec_remote

code = """
import subprocess
import sys

print("=== 1. Checking environment ===")
subprocess.run("echo Python: $(~/project/.venv/bin/python --version)", shell=True, executable="/bin/bash")

print("\\n=== 2. Pre-loading GLiNER model ===")
cmd = '''~/project/.venv/bin/python -c "
from gliner import GLiNER
print('Loading urchade/gliner_multi-v2.1...')
model = GLiNER.from_pretrained('urchade/gliner_multi-v2.1')
print('GLiNER loaded successfully!')
"'''
res = subprocess.run(cmd, shell=True, executable="/bin/bash")
print(f"GLiNER exit code: {res.returncode}")
"""

if __name__ == "__main__":
    asyncio.run(exec_remote(code))
