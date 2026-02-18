#!/usr/bin/env python3
"""
Upload build artifacts to Aliyun OSS from GitHub Actions.

Usage:
  Static:       python upload_to_oss.py static <output_dir> <slug> <deployment_id>
  Python/Node:  python upload_to_oss.py python|node <zip_path> <slug> <deployment_id>

Environment variables required:
  ALIYUN_AK_ID, ALIYUN_AK_SECRET
"""
import gzip
import mimetypes
import os
import sys
from pathlib import Path

import oss2

# OSS transfer acceleration endpoint (works well from GitHub Actions outside China)
ACCELERATE_ENDPOINT = "oss-accelerate.aliyuncs.com"

# Buckets
STATIC_BUCKET = "miaobu-deployments"       # Hangzhou
PYTHON_BUCKET = "miaobu-deployments-qingdao"  # Qingdao

# Text extensions to gzip
GZIP_EXTENSIONS = {
    ".html", ".css", ".js", ".json", ".xml", ".svg",
    ".txt", ".md", ".csv", ".map",
}


def get_content_type(path: Path) -> str:
    ct, _ = mimetypes.guess_type(str(path))
    if ct:
        return ct
    defaults = {
        ".html": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".eot": "application/vnd.ms-fontobject",
    }
    return defaults.get(path.suffix.lower(), "application/octet-stream")


def upload_static(output_dir: str, slug: str, deployment_id: str):
    """Upload a static site's build output to OSS."""
    auth = oss2.Auth(os.environ["ALIYUN_AK_ID"], os.environ["ALIYUN_AK_SECRET"])
    bucket = oss2.Bucket(auth, ACCELERATE_ENDPOINT, STATIC_BUCKET)

    local_dir = Path(output_dir)
    if not local_dir.is_dir():
        print(f"ERROR: output directory not found: {output_dir}")
        sys.exit(1)

    oss_prefix = f"projects/{slug}/{deployment_id}/"
    files = [f for f in local_dir.rglob("*") if f.is_file()]
    print(f"Uploading {len(files)} files to {oss_prefix}")

    for i, fp in enumerate(files, 1):
        rel = fp.relative_to(local_dir)
        oss_key = oss_prefix + str(rel).replace("\\", "/")
        ct = get_content_type(fp)

        headers = {
            "Content-Type": ct,
            "Cache-Control": "public, max-age=31536000",
        }

        data = fp.read_bytes()
        if fp.suffix.lower() in GZIP_EXTENSIONS and len(data) > 1024:
            data = gzip.compress(data)
            headers["Content-Encoding"] = "gzip"

        bucket.put_object(oss_key, data, headers=headers)

        if i % 50 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] uploaded")

    print(f"Done — {len(files)} files uploaded to {oss_prefix}")


def upload_fc_package(zip_path: str, slug: str, deployment_id: str):
    """Upload a code package zip (Python or Node.js) to OSS."""
    auth = oss2.Auth(os.environ["ALIYUN_AK_ID"], os.environ["ALIYUN_AK_SECRET"])
    bucket = oss2.Bucket(auth, ACCELERATE_ENDPOINT, PYTHON_BUCKET)

    zp = Path(zip_path)
    if not zp.is_file():
        print(f"ERROR: zip file not found: {zip_path}")
        sys.exit(1)

    oss_key = f"projects/{slug}/{deployment_id}/package.zip"
    size_mb = zp.stat().st_size / (1024 * 1024)
    print(f"Uploading {zp.name} ({size_mb:.1f} MB) to {oss_key}")

    bucket.put_object_from_file(oss_key, str(zp))
    print(f"Done — uploaded to {oss_key}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    mode = sys.argv[1]
    if mode == "static":
        upload_static(sys.argv[2], sys.argv[3], sys.argv[4])
    elif mode in ("python", "node"):
        upload_fc_package(sys.argv[2], sys.argv[3], sys.argv[4])
    else:
        print(f"Unknown mode: {mode}")
        sys.exit(1)
