#!/usr/bin/env python3
import argparse, os
from pathlib import Path
from huggingface_hub import snapshot_download

ap=argparse.ArgumentParser()
ap.add_argument("--repo-id", default="happyme531/MeloTTS-RKNN2")
ap.add_argument("--local-dir", default=os.getenv("MELOTTS_DIR","/home/rock/MeloTTS-RKNN2"))
args=ap.parse_args()
Path(args.local_dir).parent.mkdir(parents=True, exist_ok=True)
snapshot_download(repo_id=args.repo_id, local_dir=args.local_dir, local_dir_use_symlinks=False, resume_download=True)
print("[OK] downloaded to", args.local_dir)
