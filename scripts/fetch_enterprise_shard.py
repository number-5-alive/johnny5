"""Stream an Enterprise HTML dump and keep only its first NDJSON member (capped), for parser development.

The archive is one ~140 GB tar.gz; streaming lets us stop after the first member instead of downloading it all.
Usage (on argo): uv run python scripts/fetch_enterprise_shard.py URL OUT_DIR [MAX_GB]
"""

import sys
import tarfile
import urllib.request
from pathlib import Path

USER_AGENT = "laya-qwen/0.1 (https://number5alive.com)"

url, out_dir = sys.argv[1], Path(sys.argv[2])
max_bytes = int(float(sys.argv[3]) * 1e9) if len(sys.argv) > 3 else int(4e9)
out_dir.mkdir(parents=True, exist_ok=True)

req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
with urllib.request.urlopen(req) as resp, tarfile.open(fileobj=resp, mode="r|gz") as tar:
    for member in tar:
        if not member.isfile():
            continue
        name = Path(member.name).name
        print(f"member {member.name} size {member.size / 1e9:.2f} GB", flush=True)
        src = tar.extractfile(member)
        written, tail = 0, b""
        with open(out_dir / name, "wb") as f:
            while written < max_bytes:
                buf = src.read(8 << 20)
                if not buf:
                    break
                f.write(buf)
                written += len(buf)
            truncated = written >= max_bytes and written < member.size
        if truncated:  # cut back to the last complete NDJSON line
            data = (out_dir / name).read_bytes()
            (out_dir / name).write_bytes(data[: data.rfind(b"\n") + 1])
        print(f"wrote {out_dir / name} ({(out_dir / name).stat().st_size / 1e9:.2f} GB, truncated={truncated})")
        break
