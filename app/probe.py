"""Look up a download before it starts: name, size, resume support (files), 
total size (torrents), and free disk space."""
import os
import re
import shutil
from urllib.parse import parse_qs, urlparse, unquote

import requests

from core import UA, filename_from_response, safe_name


def free_space(path):
    """Free bytes on the drive that holds `path` (the folder may not exist yet)."""
    p = os.path.abspath(path or os.path.expanduser("~"))
    while p and not os.path.exists(p):
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    try:
        return shutil.disk_usage(p).free
    except OSError:
        return None


def drive_name(path):
    d = os.path.splitdrive(os.path.abspath(path or ""))[0]
    return d or "this drive"


# ---------------------------------------------------------------- files
def probe_file(url, headers=None, timeout=20):
    s = requests.Session()
    s.headers["User-Agent"] = UA
    for k, v in (headers or {}).items():
        if v:
            s.headers[k] = v
    r = s.get(url, headers={"Range": "bytes=0-"}, stream=True, timeout=timeout)
    try:
        r.raise_for_status()
        out = {"kind": "file", "name": safe_name(filename_from_response(r, url)), "final_url": r.url,
               "mime": r.headers.get("Content-Type", "").split(";")[0].strip()}
        if r.status_code == 206:
            m = re.search(r"/(\d+)", r.headers.get("Content-Range", ""))
            out["size"] = int(m.group(1)) if m else 0
            out["resumable"] = out["size"] > 0
        else:
            out["size"] = int(r.headers.get("Content-Length") or 0)
            out["resumable"] = False
        if out["mime"].startswith("text/html"):
            out["page"] = True     # a web page, not a file — probably needs the Video type or a direct link
        return out
    finally:
        r.close()
