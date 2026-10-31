"""Wikimedia Enterprise API client (stage 7 Q7/Q16): login with tokens cached, snapshot listing and download.

Credentials: ~/laya-data/enterprise.env (WME_USERNAME, WME_PASSWORD; must be mode 600).
Tokens:      ~/laya-data/enterprise-tokens.json (mode 600, managed here). Nothing secret is printed or logged.
"""

import json
import os
import stat
import time
from pathlib import Path

import httpx

ENV_FILE = Path(os.environ.get("LAYA_QWEN_ENTERPRISE_ENV", "~/laya-data/enterprise.env")).expanduser()
TOKEN_FILE = ENV_FILE.with_name("enterprise-tokens.json")
AUTH = "https://auth.enterprise.wikimedia.com/v1"
API = "https://api.enterprise.wikimedia.com/v2"
USER_AGENT = "laya-qwen/0.1 (https://number5alive.com)"


def _private(path: Path) -> None:
    mode = path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise PermissionError(f"{path} must not be readable by group/others (chmod 600)")


def credentials() -> tuple[str, str]:
    _private(ENV_FILE)
    env = dict(line.split("=", 1) for line in ENV_FILE.read_text().splitlines() if "=" in line and not line.startswith("#"))
    return env["WME_USERNAME"].strip(), env["WME_PASSWORD"].strip()


def _save_tokens(data: dict) -> None:
    data["obtained_at"] = time.time()
    TOKEN_FILE.touch(mode=0o600, exist_ok=True)
    os.chmod(TOKEN_FILE, 0o600)
    TOKEN_FILE.write_text(json.dumps(data))


def access_token() -> str:
    """A valid access token: cached if fresh, else refreshed, else a new login."""
    user, password = credentials()
    headers = {"User-Agent": USER_AGENT}
    if TOKEN_FILE.exists():
        _private(TOKEN_FILE)
        tok = json.loads(TOKEN_FILE.read_text())
        age = time.time() - tok.get("obtained_at", 0)
        if age < tok.get("expires_in", 0) - 300:
            return tok["access_token"]
        if tok.get("refresh_token") and age < 80 * 86400:  # refresh tokens last 90 days
            r = httpx.post(f"{AUTH}/token-refresh", json={"username": user, "refresh_token": tok["refresh_token"]},
                           headers=headers, timeout=30)
            if r.status_code == 200:
                new = r.json()
                new.setdefault("refresh_token", tok["refresh_token"])
                _save_tokens(new)
                return new["access_token"]
    r = httpx.post(f"{AUTH}/login", json={"username": user, "password": password}, headers=headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Enterprise login failed: HTTP {r.status_code} {r.text[:200]}")
    data = r.json()
    _save_tokens(data)
    return data["access_token"]


def api(method: str, path: str, **kw) -> httpx.Response:
    headers = {"Authorization": f"Bearer {access_token()}", "User-Agent": USER_AGENT, **kw.pop("headers", {})}
    return httpx.request(method, f"{API}{path}", headers=headers, timeout=kw.pop("timeout", 60), **kw)


def snapshots(project: str = "enwiki", namespace: int = 0) -> list[dict]:
    """Available snapshots for one project and namespace."""
    body = {"filters": [{"field": "is_part_of.identifier", "value": project},
                        {"field": "namespace.identifier", "value": namespace}]}
    r = api("POST", "/snapshots", json=body)
    if r.status_code == 405:  # some API versions list with GET
        r = api("GET", "/snapshots")
    r.raise_for_status()
    items = r.json()
    return [s for s in items if s.get("identifier", "").startswith(f"{project}_namespace_{namespace}")] or items


def _main() -> None:
    import sys

    if len(sys.argv) > 2 and sys.argv[1] == "download":
        download_snapshot(Path(sys.argv[2]).expanduser())
        return
    for s in snapshots():
        size = s.get("size", {})
        print(json.dumps({k: s.get(k) for k in ("identifier", "date_modified", "version", "chunks")} |
                         {"size": size}, default=str)[:400])


def download_snapshot(out_dir: Path, identifier: str = "enwiki_namespace_0") -> None:
    """Download every chunk of a snapshot, one at a time, resuming finished and partial chunks.

    Chunk downloads count against the free tier's 1,500/month (a 435-chunk enwiki snapshot fits); a whole-snapshot
    download would count against the 30/month, so chunks are used. Finished chunks are skipped by size."""
    out_dir.mkdir(parents=True, exist_ok=True)
    info = api("GET", f"/snapshots/{identifier}").json()
    (out_dir / "snapshot.json").write_text(json.dumps({k: v for k, v in info.items() if k != "chunks"}, indent=1))
    chunks = info["chunks"]
    for n, chunk in enumerate(chunks, 1):
        dest = out_dir / f"{chunk}.tar.gz"
        head = api("HEAD", f"/snapshots/{identifier}/chunks/{chunk}/download")
        total = int(head.headers.get("content-length", 0))
        if dest.exists() and dest.stat().st_size == total:
            continue
        part = dest.with_suffix(".part")
        for attempt in range(6):
            have = part.stat().st_size if part.exists() else 0
            try:
                headers = {"Authorization": f"Bearer {access_token()}", "User-Agent": USER_AGENT}
                if have:
                    headers["Range"] = f"bytes={have}-"
                with httpx.stream("GET", f"{API}/snapshots/{identifier}/chunks/{chunk}/download", headers=headers,
                                  timeout=120, follow_redirects=True) as r:
                    if r.status_code == 200 and have:  # server ignored the range: start over
                        have = 0
                        part.unlink(missing_ok=True)
                    r.raise_for_status()
                    with open(part, "ab") as f:
                        for buf in r.iter_bytes(8 << 20):
                            f.write(buf)
                if part.stat().st_size == total:
                    part.rename(dest)
                    break
            except (httpx.HTTPError, OSError) as e:
                print(f"{chunk}: attempt {attempt + 1} failed: {type(e).__name__}", flush=True)
                time.sleep(min(300, 15 * 2 ** attempt))
        else:
            raise RuntimeError(f"{chunk}: giving up after 6 attempts")
        print(f"[{n}/{len(chunks)}] {chunk} {total / 1e6:.0f} MB", flush=True)
    print("SNAPSHOT_DONE", flush=True)


if __name__ == "__main__":
    _main()
