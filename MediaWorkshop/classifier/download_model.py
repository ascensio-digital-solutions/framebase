import sys
import time
from pathlib import Path
from huggingface_hub import snapshot_download

target_dir = Path("/Users/vincent/mlx-models/qwen2.5-vl-32b")
target_dir.mkdir(parents=True, exist_ok=True)

repo_id = "mlx-community/Qwen2.5-VL-32B-Instruct-4bit"
print(f"[{time.strftime('%X')}] Starting download of {repo_id} to {target_dir}...")

try:
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        max_workers=4,
    )
    print(f"[{time.strftime('%X')}] Successfully downloaded {repo_id}!")
except Exception as e:
    print(f"Download failed: {e}")
    sys.exit(1)
