import asyncio
import aiohttp
import json
import uuid
import sys
import os

sys.stdout.reconfigure(encoding="utf-8")

TOKEN = os.environ.get("JUPYTER_HUB_TOKEN", "")
BASE = os.environ.get("JUPYTER_HUB_BASE", "https://tochka-sborki-2026-team-059.hub.gigaschool.ru/jupyter")
WS_BASE = os.environ.get("JUPYTER_HUB_WS_BASE", "wss://tochka-sborki-2026-team-059.hub.gigaschool.ru/jupyter")

async def exec_remote(code: str):
    if not TOKEN:
        err = "ERROR: JUPYTER_HUB_TOKEN environment variable is not set.\n"
        print(err, end="", file=sys.stderr)
        return err
    headers = {"Authorization": f"token {TOKEN}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        # 1. Create kernel
        async with session.post(f"{BASE}/api/kernels") as resp:
            kernel = await resp.json()
            kid = kernel["id"]

        output_text = []
        try:
            # 2. Connect to WS
            ws_url = f"{WS_BASE}/api/kernels/{kid}/channels?token={TOKEN}"
            async with session.ws_connect(ws_url) as ws:
                msg_id = str(uuid.uuid4())
                exec_msg = {
                    "header": {
                        "msg_id": msg_id,
                        "username": "username",
                        "session": str(uuid.uuid4()),
                        "msg_type": "execute_request",
                        "version": "5.3"
                    },
                    "parent_header": {},
                    "metadata": {},
                    "content": {
                        "code": code,
                        "silent": False,
                        "store_history": True,
                        "user_expressions": {},
                        "allow_stdin": False
                    },
                    "channel": "shell"
                }
                await ws.send_json(exec_msg)

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        data = json.loads(msg.data)
                        msg_type = data.get("msg_type")
                        if msg_type == "stream":
                            text = data["content"]["text"]
                            print(text, end="")
                            output_text.append(text)
                        elif msg_type == "error":
                            err = f"ERROR: {data['content']['ename']}: {data['content']['evalue']}\n"
                            print(err, end="")
                            output_text.append(err)
                        elif msg_type == "status" and data["content"]["execution_state"] == "idle":
                            if data.get("parent_header", {}).get("msg_id") == msg_id:
                                break
        finally:
            # 3. Clean up kernel
            async with session.delete(f"{BASE}/api/kernels/{kid}"):
                pass
        return "".join(output_text)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        sh_cmd = " ".join(sys.argv[1:])
        code = f"""
import subprocess
res = subprocess.run({repr(sh_cmd)}, shell=True, executable='/bin/bash')
"""
        asyncio.run(exec_remote(code))
    else:
        test_code = """
import os, subprocess, sys

print("=== SYSTEM INFO ===")
subprocess.run("uname -a", shell=True)
subprocess.run("whoami", shell=True)
subprocess.run("df -h", shell=True)
subprocess.run("free -m", shell=True)

print("\\n=== PYTHON & DOCKER ===")
subprocess.run("python3 --version; which python3; pip --version", shell=True)
subprocess.run("docker --version 2>/dev/null || echo 'No docker'", shell=True)

print("\\n=== LISTENING PORTS ===")
subprocess.run("ss -tulpn", shell=True)

print("\\n=== /opt/hackathon/ai.env ===")
if os.path.exists("/opt/hackathon/ai.env"):
    with open("/opt/hackathon/ai.env") as f:
        print(f.read())

print("\\n=== ~/project GIT STATUS ===")
subprocess.run("git status", cwd=os.path.expanduser("~/project"), shell=True)
subprocess.run("git remote -v", cwd=os.path.expanduser("~/project"), shell=True)
"""
        asyncio.run(exec_remote(test_code))
