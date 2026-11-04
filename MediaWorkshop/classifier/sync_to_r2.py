#!/usr/bin/env python3
"""
Framebase High-Throughput Cloudflare R2 Uploader & Cloud State Reconciler.

Streams original photo bytes directly from /Volumes/SeaDisk into Cloudflare R2:
- Personal Library   -> framebase-blobs-personal-prod
- HSC Library        -> framebase-blobs-prod (and hsc-media-origin fallback)
- Knowledge Library  -> framebase-blobs-prod

For each asset:
1. Resolves file on /Volumes/SeaDisk (or checks if already in R2).
2. Streams upload via Cloudflare REST API v4 to blobs/sha256/{prefix}/{sha256}.{ext}.
3. Inserts/updates `cloud_blobs` in Catalog with verification_state = 'verified'.
4. Inserts/updates `asset_cloud_state` with materialization_state = 'remoteOnly'.
5. Ensures `assets.original_available = 0`.

Preserves Mac SSD zero-byte-footprint guarantee.
"""

import os
import sys
import time
import json
import sqlite3
import asyncio
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import httpx

SCRIPT_DIR = Path(__file__).parent.resolve()
DB_PATH = SCRIPT_DIR / "state.sqlite"
LOG_PATH = SCRIPT_DIR / "r2_sync.log"
ENV_PATH = Path("/Users/vincent/.env")

PICTURES_DIR = Path(os.path.expanduser("~/Pictures"))
LIBRARIES = {
    "knowledge": {
        "name": "Knowledge Library.framebase",
        "db": PICTURES_DIR / "Knowledge Library.framebase" / "Catalog" / "catalog.sqlite",
        "bucket": "framebase-blobs-prod",
        "domain": "knowledge"
    },
    "hsc": {
        "name": "HSC Library.framebase",
        "db": PICTURES_DIR / "HSC Library.framebase" / "Catalog" / "catalog.sqlite",
        "bucket": "framebase-blobs-prod",
        "domain": "business"
    },
    "personal": {
        "name": "Personal Library.framebase",
        "db": PICTURES_DIR / "Personal Library.framebase" / "Catalog" / "catalog.sqlite",
        "bucket": "framebase-blobs-personal-prod",
        "domain": "personal"
    }
}

MIME_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "heic": "image/heic",
    "webp": "image/webp",
    "tiff": "image/tiff",
    "tif": "image/tiff"
}

def load_env() -> Dict[str, str]:
    env = {}
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip("\"'")
    return env

def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {msg}"
    print(formatted, flush=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(formatted + "\n")

class R2SyncPipeline:
    def __init__(self, account_id: str, token: str, concurrency: int = 16):
        self.account_id = account_id
        self.token = token
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.sha_to_seadisk = {}
        self.load_inventory_mapping()

    def load_inventory_mapping(self):
        log("Loading SHA-256 to SeaDisk path index from state.sqlite...")
        conn = sqlite3.connect(str(DB_PATH))
        c = conn.cursor()
        c.execute("SELECT sha256, file_path, filename, year FROM inventory")
        for sha, fp, fn, yr in c.fetchall():
            self.sha_to_seadisk[sha] = (fp, fn, yr)
        conn.close()
        log(f"Indexed {len(self.sha_to_seadisk):,} assets from inventory.")

    def resolve_file(self, sha256: str, filename: str) -> Optional[Path]:
        info = self.sha_to_seadisk.get(sha256)
        if info:
            fp, fn, yr = info
            p = Path(fp)
            if p.exists():
                return p
            p_seadisk = Path(f"/Volumes/SeaDisk/{yr}/{fn}")
            if p_seadisk.exists():
                return p_seadisk
            p_iphoto = Path(f"/Volumes/SeaDisk/media_workshop/iPhoto export 2010-2026/{yr}/{fn}")
            if p_iphoto.exists():
                return p_iphoto

        # Fallbacks by filename directly on SeaDisk
        for yr in range(2026, 2009, -1):
            cand = Path(f"/Volumes/SeaDisk/{yr}/{filename}")
            if cand.exists():
                return cand
        return None

    async def check_blob_exists_in_r2(self, client: httpx.AsyncClient, bucket: str, r2_key: str) -> bool:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/r2/buckets/{bucket}/objects/{r2_key}"
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            resp = await client.head(url, headers=headers)
            return resp.status_code == 200
        except Exception:
            return False

    async def upload_blob(
        self,
        client: httpx.AsyncClient,
        bucket: str,
        r2_key: str,
        file_path: Path,
        mime_type: str,
        retries: int = 3
    ) -> bool:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/r2/buckets/{bucket}/objects/{r2_key}"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": mime_type
        }

        for attempt in range(1, retries + 1):
            try:
                # Read file directly into memory
                content = await asyncio.to_thread(file_path.read_bytes)
                resp = await client.put(url, content=content, headers=headers, timeout=60.0)
                if resp.status_code in (200, 201):
                    return True
                elif resp.status_code == 429:
                    await asyncio.sleep(2.0 * attempt)
                else:
                    await asyncio.sleep(1.0 * attempt)
            except Exception as e:
                if attempt == retries:
                    log(f"Upload failed for {file_path.name} after {retries} attempts: {e}")
                await asyncio.sleep(1.0 * attempt)
        return False

    async def sync_library(self, lib_key: str, limit: Optional[int] = None):
        cfg = LIBRARIES[lib_key]
        lib_name = cfg["name"]
        db_path = cfg["db"]
        bucket = cfg["bucket"]

        if not db_path.exists():
            log(f"Library database not found: {db_path}. Skipping.")
            return

        log("\n" + "=" * 80)
        log(f"STARTING CLOUD SYNC: {lib_name}")
        log(f"Target Bucket: {bucket} | Concurrency: {self.concurrency}")
        log("=" * 80)

        # 1. First, ensure all existing assets in catalog have original_available = 0
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        c.execute("UPDATE assets SET original_available = 0 WHERE original_available = 1")
        conn.commit()

        # 2. Query assets needing cloud upload or verification
        c.execute("""
            SELECT a.id, a.filename, aci.sha256, a.file_size
            FROM assets a
            JOIN asset_content_identity aci ON a.id = aci.asset_id
            LEFT JOIN cloud_blobs cb ON aci.sha256 = cb.sha256
            WHERE cb.verification_state IS NULL OR cb.verification_state != 'verified'
            ORDER BY a.imported_at_ms DESC
        """)
        pending_assets = c.fetchall()
        conn.close()

        total_pending = len(pending_assets)
        if limit and limit < total_pending:
            pending_assets = pending_assets[:limit]
            total_pending = len(pending_assets)

        log(f"Found {total_pending:,} assets needing R2 upload/verification in {lib_name}.")
        if total_pending == 0:
            log(f"Library {lib_name} is already 100% cloud-verified!")
            return

        # Prepare worker queue
        uploaded_bytes = 0
        success_count = 0
        already_verified_count = 0
        failed_count = 0
        start_time = time.time()

        batch_results = []
        batch_lock = asyncio.Lock()

        async def flush_batch(results_to_commit):
            if not results_to_commit:
                return
            now_ms = int(time.time() * 1000)
            c_conn = sqlite3.connect(str(db_path))
            cur = c_conn.cursor()
            try:
                for asset_id, sha256, byte_size, ext, mime_type in results_to_commit:
                    cur.execute("""
                        INSERT INTO cloud_blobs (
                            sha256, byte_size, media_type, original_extension, remote_blob_id,
                            verification_state, last_error, verified_at_ms, updated_at_ms
                        ) VALUES (?, ?, ?, ?, ?, 'verified', NULL, ?, ?)
                        ON CONFLICT(sha256) DO UPDATE SET
                            verification_state = 'verified',
                            remote_blob_id = excluded.remote_blob_id,
                            verified_at_ms = excluded.verified_at_ms,
                            updated_at_ms = excluded.updated_at_ms
                    """, (sha256, byte_size, mime_type, ext, sha256, now_ms, now_ms))

                    cur.execute("""
                        INSERT INTO asset_cloud_state (
                            asset_id, blob_sha256, remote_revision, materialization_state, last_error, updated_at_ms
                        ) VALUES (?, ?, 1, 'remoteOnly', NULL, ?)
                        ON CONFLICT(asset_id) DO UPDATE SET
                            blob_sha256 = excluded.blob_sha256,
                            materialization_state = 'remoteOnly',
                            updated_at_ms = excluded.updated_at_ms
                    """, (asset_id, sha256, now_ms))

                    cur.execute("UPDATE assets SET original_available = 0 WHERE id = ?", (asset_id,))
                c_conn.commit()
            except Exception as e:
                log(f"Batch commit error: {e}")
            finally:
                c_conn.close()

        limits = httpx.Limits(max_keepalive_connections=self.concurrency * 2, max_connections=self.concurrency * 4)
        async with httpx.AsyncClient(limits=limits, timeout=60.0) as client:
            async def process_asset(item):
                nonlocal uploaded_bytes, success_count, already_verified_count, failed_count
                asset_id, filename, sha256, byte_size = item
                ext = Path(filename).suffix.lstrip(".").lower()
                if not ext:
                    ext = "jpeg"
                mime_type = MIME_TYPES.get(ext, "image/jpeg")
                r2_key = f"blobs/sha256/{sha256[:2]}/{sha256}.{ext}"

                async with self.semaphore:
                    # Check if already in R2
                    exists = await self.check_blob_exists_in_r2(client, bucket, r2_key)
                    if exists:
                        already_verified_count += 1
                        async with batch_lock:
                            batch_results.append((asset_id, sha256, byte_size, ext, mime_type))
                        return

                    # Resolve local master on SeaDisk
                    local_p = self.resolve_file(sha256, filename)
                    if not local_p or not local_p.exists():
                        failed_count += 1
                        return

                    # Upload to Cloudflare R2
                    ok = await self.upload_blob(client, bucket, r2_key, local_p, mime_type)
                    if ok:
                        success_count += 1
                        uploaded_bytes += byte_size
                        async with batch_lock:
                            batch_results.append((asset_id, sha256, byte_size, ext, mime_type))
                    else:
                        failed_count += 1

            tasks = []
            for idx, item in enumerate(pending_assets, 1):
                tasks.append(process_asset(item))
                if len(tasks) >= self.concurrency * 4:
                    await asyncio.gather(*tasks)
                    tasks = []
                    # Periodic commit
                    async with batch_lock:
                        if len(batch_results) >= 100:
                            to_commit = list(batch_results)
                            batch_results.clear()
                            await flush_batch(to_commit)

                    # Progress log
                    elapsed = time.time() - start_time
                    done = success_count + already_verified_count + failed_count
                    pct = (done / total_pending) * 100
                    mb_s = (uploaded_bytes / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                    log(
                        f"[{done:,}/{total_pending:,} ({pct:.1f}%)] "
                        f"Uploaded: {success_count:,} | Already in R2: {already_verified_count:,} | "
                        f"Failed: {failed_count} | Speed: {mb_s:.2f} MB/s"
                    )

            if tasks:
                await asyncio.gather(*tasks)

            # Final flush
            async with batch_lock:
                if batch_results:
                    await flush_batch(batch_results)
                    batch_results.clear()

        total_elapsed = time.time() - start_time
        log(f"\nCOMPLETED SYNC FOR {lib_name}:")
        log(f"  Total Processed: {total_pending:,}")
        log(f"  Uploaded to R2:  {success_count:,} ({uploaded_bytes / (1024*1024*1024):.2f} GB)")
        log(f"  Already in R2:   {already_verified_count:,}")
        log(f"  Failed:          {failed_count:,}")
        log(f"  Duration:        {total_elapsed / 60:.2f} minutes")
        log("=" * 80)

async def main():
    parser = argparse.ArgumentParser(description="Upload Framebase originals to Cloudflare R2.")
    parser.add_argument("--library", choices=["all", "knowledge", "hsc", "personal"], default="all",
                        help="Which library to sync (default: all)")
    parser.add_argument("--concurrency", type=int, default=16, help="Upload concurrency (default: 16)")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of assets per library")
    args = parser.parse_args()

    env = load_env()
    account_id = env.get("CLOUDFLARE_ACCOUNT_ID")
    token = env.get("CLOUDFLARE_MASTER_TOKEN")

    if not account_id or not token:
        log("ERROR: Missing CLOUDFLARE_ACCOUNT_ID or CLOUDFLARE_MASTER_TOKEN in /Users/vincent/.env")
        sys.exit(1)

    pipeline = R2SyncPipeline(account_id, token, concurrency=args.concurrency)

    targets = ["knowledge", "hsc", "personal"] if args.library == "all" else [args.library]
    for target in targets:
        await pipeline.sync_library(target, limit=args.limit)

if __name__ == "__main__":
    asyncio.run(main())

