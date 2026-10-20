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
import os, openai

with open('/opt/hackathon/ai.env') as f:
    for line in f:
        line = line.strip()
        if line and '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            os.environ[k] = v.strip('\\"\\'')

client = openai.OpenAI(
    base_url=os.environ.get('OPENAI_BASE_URL'),
    api_key=os.environ.get('OPENAI_API_KEY')
)

resp = client.chat.completions.create(
    model='ai-sage/GigaChat3-10B-A1.8B',
    messages=[{'role': 'user', 'content': 'Привет! Ответь одним словом: работает'}]
)
print('LLM Response:', resp.choices[0].message.content)
"""

if __name__ == "__main__":
    asyncio.run(exec_remote(code))
