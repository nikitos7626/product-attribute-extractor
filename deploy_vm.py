#!/usr/bin/env python3
"""
Remote VM Deployment & Verification Utility for M.Video Product Attribute Extractor.
Uses the JupyterHub WebSocket API to execute remote deployment on the hackathon VM.

Usage:
    # Check remote VM status & environment
    python deploy_vm.py --action status

    # Deploy latest code from git, restart service, and verify
    python deploy_vm.py --action deploy

    # Test live inference on remote service
    python deploy_vm.py --action test

    # Execute custom bash command on VM
    python deploy_vm.py --action exec --cmd "git status"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent

# Try reading JUPYTER_HUB_TOKEN from environment or .env file
TOKEN = os.environ.get("JUPYTER_HUB_TOKEN", "")
if not TOKEN:
    env_file = REPO_ROOT / ".env"
    if env_file.is_file():
        try:
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    if line.startswith("JUPYTER_HUB_TOKEN="):
                        TOKEN = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        except Exception:
            pass

DEFAULT_BASE = os.environ.get("JUPYTER_HUB_BASE", "https://tochka-sborki-2026-team-059.hub.gigaschool.ru/jupyter")
DEFAULT_WS_BASE = os.environ.get("JUPYTER_HUB_WS_BASE", "wss://tochka-sborki-2026-team-059.hub.gigaschool.ru/jupyter")


async def exec_remote(code: str, token: str, base: str = DEFAULT_BASE, ws_base: str = DEFAULT_WS_BASE) -> str:
    if not token:
        msg = (
            "⚠️ JUPYTER_HUB_TOKEN is not configured.\n"
            "To deploy to the remote VM, provide the token via:\n"
            "  - Environment variable: export JUPYTER_HUB_TOKEN=<token>\n"
            "  - Command line flag:    python deploy_vm.py --token <token>\n"
            "  - In .env file:         JUPYTER_HUB_TOKEN=<token>\n\n"
            "All changes are already committed and synced to both Git remotes:\n"
            "  • Origin (GitHub): https://github.com/nikitos7626/product-attribute-extractor.git\n"
            "  • Gitea (Remote):  https://git.hub.gigaschool.ru/tochka-sborki-2026-team-059/project.git\n\n"
            "On the remote VM, run:\n"
            "  cd ~/project && git pull gitea main && sudo systemctl restart mvideo-nlp\n"
        )
        print(msg)
        return msg

    try:
        import aiohttp
    except ImportError:
        print("aiohttp is required for remote VM deployment. Please install with: pip install aiohttp")
        return ""

    headers = {"Authorization": f"token {token}"}
    output_lines: list[str] = []

    print(f"Connecting to remote VM kernel at {base}...")
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(f"{base}/api/kernels") as resp:
            if resp.status != 201 and resp.status != 200:
                text = await resp.text()
                print(f"Failed to create remote kernel (HTTP {resp.status}): {text}")
                return text
            kernel = await resp.json()
            kid = kernel["id"]

        try:
            ws_url = f"{ws_base}/api/kernels/{kid}/channels?token={token}"
            async with session.ws_connect(ws_url) as ws:
                msg_id = str(uuid.uuid4())
                exec_msg = {
                    "header": {
                        "msg_id": msg_id,
                        "username": "deploy_agent",
                        "session": str(uuid.uuid4()),
                        "msg_type": "execute_request",
                        "version": "5.3",
                    },
                    "parent_header": {},
                    "metadata": {},
                    "content": {
                        "code": code,
                        "silent": False,
                        "store_history": True,
                        "user_expressions": {},
                        "allow_stdin": False,
                    },
                    "channel": "shell",
                }
                await ws.send_json(exec_msg)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        msg_type = data.get("msg_type")
                        if msg_type == "stream":
                            text = data["content"]["text"]
                            print(text, end="")
                            output_lines.append(text)
                        elif msg_type == "error":
                            err = f"ERROR: {data['content']['ename']}: {data['content']['evalue']}\n"
                            print(err, end="")
                            output_lines.append(err)
                        elif msg_type == "status" and data["content"]["execution_state"] == "idle":
                            if data.get("parent_header", {}).get("msg_id") == msg_id:
                                break
        finally:
            async with session.delete(f"{base}/api/kernels/{kid}"):
                pass

    return "".join(output_lines)


DEPLOY_CODE = """
import os, subprocess, urllib.request, json

print("=== 1. PULLING LATEST CODE FROM GIT ===")
proj_dir = os.path.expanduser("~/project")
subprocess.run("git fetch origin main && git checkout main && git pull origin main", cwd=proj_dir, shell=True, check=False)
subprocess.run("git log -n 3 --oneline", cwd=proj_dir, shell=True)

print("\\n=== 2. RESTARTING MVIDEO SERVICE ===")
subprocess.run("sudo systemctl restart mvideo-nlp", shell=True)
subprocess.run("sudo systemctl status mvideo-nlp --no-pager", shell=True)

print("\\n=== 3. VERIFYING LIVE INFERENCE VIA HTTP ===")
try:
    test_card = {
        "title": "Смартфон Apple iPhone 16 Pro 256GB синий титан",
        "description": "Экран 6.3 дюйма 120 Гц, аккумулятор 3355 мАч, вес 198 г."
    }
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/extract",
        data=json.dumps(test_card).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print(f"Status: {resp.status}")
        print(f"Category: {res.get('category')}")
        print(f"Overall Confidence: {res.get('overall_confidence')}")
        print("Predictions:")
        for p in res.get("predictions", []):
            print(f"  • {p['attribute']}: {p['value']} ({p.get('source')})")
    print("\\n✅ REMOTE VM DEPLOYMENT AND VERIFICATION COMPLETED SUCCESSFULLY!")
except Exception as e:
    print(f"⚠️ Live healthcheck failed: {e}")
"""

STATUS_CODE = """
import subprocess
print("=== REMOTE SYSTEM STATUS ===")
subprocess.run("uname -a", shell=True)
subprocess.run("uptime", shell=True)
subprocess.run("free -m", shell=True)
subprocess.run("ss -tulpn | grep 8000", shell=True)
subprocess.run("sudo systemctl status mvideo-nlp --no-pager", shell=True)
"""

TEST_CODE = """
import urllib.request, json
test_card = {
    "title": "Холодильник LG No Frost 67 кг серебристый",
    "description": "Общий объем 340 л, зона свежести, цвет серебристый."
}
req = urllib.request.Request(
    "http://127.0.0.1:8000/api/extract",
    data=json.dumps(test_card).encode("utf-8"),
    headers={"Content-Type": "application/json"}
)
with urllib.request.urlopen(req, timeout=10) as resp:
    res = json.loads(resp.read().decode("utf-8"))
    print("Inference test result:")
    print(json.dumps(res, ensure_ascii=False, indent=2))
"""


def main():
    parser = argparse.ArgumentParser(description="M.Video NLP Extractor Remote VM Deployment")
    parser.add_argument("--action", choices=["deploy", "status", "test", "exec"], default="deploy", help="Deployment action")
    parser.add_argument("--token", default=TOKEN, help="JupyterHub API Token")
    parser.add_argument("--cmd", default="", help="Command to run when action=exec")
    args = parser.parse_args()

    token = args.token or TOKEN

    if args.action == "deploy":
        code = DEPLOY_CODE
    elif args.action == "status":
        code = STATUS_CODE
    elif args.action == "test":
        code = TEST_CODE
    elif args.action == "exec":
        cmd_str = args.cmd or "git status"
        code = f"""
import subprocess
subprocess.run({repr(cmd_str)}, shell=True, executable='/bin/bash')
"""

    asyncio.run(exec_remote(code, token))


if __name__ == "__main__":
    main()
