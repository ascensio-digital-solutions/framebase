import sys
import time
from pathlib import Path
from huggingface_hub import snapshot_download

target_dir = Path("/Users/vincent/mlx-models/qwen2.5-vl-7b")
target_dir.mkdir(parents=True, exist_ok=True)

repo_id = "mlx-community/Qwen2.5-VL-7B-Instruct-4bit"
print(f"[{time.strftime('%X')}] Starting download of {repo_id} to {target_dir}...")
start_time = time.time()

try:
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(target_dir),
        max_workers=4,
    )
    elapsed = time.time() - start_time
    print(f"[{time.strftime('%X')}] Successfully downloaded {repo_id} in {elapsed:.1f}s!")
except Exception as e:
    print(f"Download failed: {e}")
    sys.exit(1)
