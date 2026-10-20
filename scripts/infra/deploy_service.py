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

service_content = '''[Unit]
Description=M.Video Attribute Extraction API Service
After=network.target

[Service]
Type=simple
User=tochka-sborki-2026-team-059
WorkingDirectory=/home/tochka-sborki-2026-team-059/project/backend
Environment="PYTHONPATH=/home/tochka-sborki-2026-team-059/project/backend"
EnvironmentFile=-/opt/hackathon/ai.env
ExecStart=/home/tochka-sborki-2026-team-059/project/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
StandardOutput=append:/home/tochka-sborki-2026-team-059/project/logs/app.log
StandardError=append:/home/tochka-sborki-2026-team-059/project/logs/app.log

[Install]
WantedBy=multi-user.target
'''

print("1. Creating systemd service file...")
with open("/tmp/mvideo-nlp.service", "w") as f:
    f.write(service_content)

subprocess.run("sudo cp /tmp/mvideo-nlp.service /etc/systemd/system/mvideo-nlp.service", shell=True, check=True)
subprocess.run("sudo systemctl daemon-reload", shell=True, check=True)
subprocess.run("sudo systemctl enable mvideo-nlp", shell=True, check=True)
subprocess.run("sudo systemctl restart mvideo-nlp", shell=True, check=True)

print("2. Checking service status...")
subprocess.run("sudo systemctl status mvideo-nlp --no-pager", shell=True)
"""

if __name__ == "__main__":
    asyncio.run(exec_remote(code))
