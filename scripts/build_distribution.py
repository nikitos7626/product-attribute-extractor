import os
import shutil
import zipfile
import sys
from pathlib import Path

# Fix Windows console UTF-8 output if needed
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent

# Desktop target locations
DESKTOPS = [
    Path(r"C:\Users\nikit\OneDrive\Рабочий стол"),
    Path(r"C:\Users\nikit\Desktop"),
]

print(f"Repository Root: {REPO_ROOT}")

# 1. Build Standalone HTML
html = (REPO_ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
css = (REPO_ROOT / "frontend" / "css" / "style.css").read_text(encoding="utf-8")
presets = (REPO_ROOT / "frontend" / "js" / "presets.js").read_text(encoding="utf-8")
api = (REPO_ROOT / "frontend" / "js" / "api.js").read_text(encoding="utf-8")
render = (REPO_ROOT / "frontend" / "js" / "render.js").read_text(encoding="utf-8")
app = (REPO_ROOT / "frontend" / "js" / "app.js").read_text(encoding="utf-8")

# Replace link css
html_standalone = html.replace(
    '<link rel="stylesheet" href="css/style.css">',
    f'<style>\n{css}\n</style>'
)

old_scripts = (
    '<script src="js/presets.js"></script>\n'
    '  <script src="js/api.js"></script>\n'
    '  <script src="js/render.js"></script>\n'
    '  <script src="js/app.js"></script>'
)
new_scripts = f"""<script>
{presets}
</script>
<script>
{api}
</script>
<script>
{render}
</script>
<script>
{app}
</script>"""

if old_scripts in html_standalone:
    html_standalone = html_standalone.replace(old_scripts, new_scripts)
else:
    print("Notice: old_scripts block not directly matched, trying normalized newlines")
    html_standalone_norm = html_standalone.replace("\r\n", "\n")
    old_scripts_norm = old_scripts.replace("\r\n", "\n")
    assert old_scripts_norm in html_standalone_norm, "old_scripts not found in html"
    html_standalone = html_standalone_norm.replace(old_scripts_norm, new_scripts)

standalone_path = REPO_ROOT / "frontend" / "mvideo_ai_standalone.html"
standalone_path.write_text(html_standalone, encoding="utf-8")
print(f"Generated standalone HTML at {standalone_path} ({len(html_standalone)} bytes)")

# 2. Files and folders to include in the complete package
INCLUDE_PATTERNS = [
    "backend",
    "frontend",
    "data",
    "scripts",
    "output",
    "notebooks",
    "docs",
    "Dockerfile",
    "docker-compose.yml",
    "extract.py",
    "requirements.txt",
    "run_docker.bat",
    "run_docker.sh",
    "README.md",
    "LICENSE",
    ".dockerignore",
    ".gitignore",
    ".env.example",
]

def ignore_patterns(path, names):
    ignored = set()
    for name in names:
        if name in ("__pycache__", ".pytest_cache", ".git", ".mypy_cache", ".ruff_cache", "skus.pkl", "dist_staging"):
            ignored.add(name)
        elif name.endswith((".pyc", ".pyo")):
            ignored.add(name)
    return ignored

# Staging temp dir for clean packaging
staging_dir = REPO_ROOT / "dist_staging" / "product-attribute-extractor"
if staging_dir.parent.exists():
    shutil.rmtree(staging_dir.parent)
staging_dir.mkdir(parents=True, exist_ok=True)

for item in INCLUDE_PATTERNS:
    src = REPO_ROOT / item
    if not src.exists():
        print(f"Notice: optional item {item} not present, skipping")
        continue
    dst = staging_dir / item
    if src.is_dir():
        shutil.copytree(src, dst, ignore=ignore_patterns)
    else:
        shutil.copy2(src, dst)

print(f"Copied all project files to staging: {staging_dir}")

# Create ZIP archive
zip_path = REPO_ROOT / "product-attribute-extractor.zip"
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(staging_dir):
        for f in files:
            full_path = Path(root) / f
            arc_name = full_path.relative_to(staging_dir)
            zf.write(full_path, arc_name)

print(f"Created ZIP archive at {zip_path} ({zip_path.stat().st_size / (1024*1024):.2f} MB)")

# Copy to user desktops
for desktop in DESKTOPS:
    if not desktop.exists():
        try:
            desktop.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"Could not create {desktop}: {e}")
            continue

    print(f"\nDeploying to Desktop: {str(desktop)}")
    
    # 1. Target directory
    target_dir = desktop / "product-attribute-extractor"
    if target_dir.exists():
        try:
            shutil.rmtree(target_dir)
        except Exception as e:
            print(f"Warning removing {target_dir}: {e}")
    shutil.copytree(staging_dir, target_dir, dirs_exist_ok=True, ignore=ignore_patterns)
    print(f"  -> Project folder deployed: {str(target_dir)}")

    # 2. Target ZIP
    target_zip = desktop / "product-attribute-extractor.zip"
    shutil.copy2(zip_path, target_zip)
    print(f"  -> ZIP archive deployed: {str(target_zip)}")

    # 3. Target Standalone HTML
    target_html = desktop / "mvideo_ai_standalone.html"
    shutil.copy2(standalone_path, target_html)
    print(f"  -> Standalone UI deployed: {str(target_html)}")

# Clean up staging dir
shutil.rmtree(staging_dir.parent)
print("\nDeployment complete successfully!")
