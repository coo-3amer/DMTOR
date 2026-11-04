"""Look up a download before it starts: name, size, resume support (files), size per quality (videos),
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


# ---------------------------------------------------------------- videos
def _fsize(f, duration):
    size = f.get("filesize") or f.get("filesize_approx")
    if size:
        return int(size)
    tbr = f.get("tbr") or ((f.get("vbr") or 0) + (f.get("abr") or 0))
    if tbr and duration:
        return int(tbr * 1000 / 8 * duration)
    return None


def estimate_sizes(info, has_ffmpeg=True):
    """{'best': bytes, '1080': bytes, ..., 'audio': bytes} — None where it can't be estimated."""
    duration = info.get("duration") or 0
    formats = info.get("formats") or []
    if not formats:     # single-format sites
        size = _fsize(info, duration)
        return {k: size for k in ("best", "1080", "720", "480", "360")} | {"audio": None}
    has_v = lambda f: f.get("vcodec") not in (None, "none")          # noqa: E731
    has_a = lambda f: f.get("acodec") not in (None, "none")          # noqa: E731
    video_only = [f for f in formats if has_v(f) and not has_a(f)]
    combined = [f for f in formats if has_v(f) and has_a(f)]
    audio_only = [f for f in formats if has_a(f) and not has_v(f)]

    best_audio = max(audio_only, key=lambda f: (f.get("abr") or f.get("tbr") or 0), default=None)
    audio_size = _fsize(best_audio, duration) if best_audio else None

    def pick(cands, h):
        ok = [f for f in cands if (f.get("height") or 0) and (h is None or f["height"] <= h)]
        if not ok:
            return None
        return max(ok, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))

    out = {}
    for key, h in (("best", None), ("1080", 1080), ("720", 720), ("480", 480), ("360", 360)):
        size = None
        v = pick(video_only, h) if has_ffmpeg else None
        c = pick(combined, h)
        if v and (not c or (v.get("height") or 0) > (c.get("height") or 0)):
            vs = _fsize(v, duration)
            size = vs + (audio_size or 0) if vs else None
        elif c:
            size = _fsize(c, duration)
        out[key] = size
    # MP3 at 192 kbps
    out["audio"] = int(192000 / 8 * duration) if (duration and has_ffmpeg) else audio_size
    return out


def probe_video(url, referrer="", has_ffmpeg=True):
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "skip_download": True}
    if referrer:
        opts["http_headers"] = {"Referer": referrer}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False, process=False) or {}
        if info.get("_type") in ("url", "url_transparent"):
            info = ydl.extract_info(info["url"], download=False, process=False) or info
    title = safe_name(info.get("title") or "")
    return {"kind": "video", "name": title, "duration": info.get("duration") or 0,
            "sizes": estimate_sizes(info, has_ffmpeg), "site": info.get("extractor_key") or ""}


# ---------------------------------------------------------------- torrents
def probe_torrent(src, headers=None, timeout=20):
    if src.lower().startswith("magnet:"):
        dn = parse_qs(urlparse(src).query).get("dn")
        return {"kind": "torrent", "name": unquote(dn[0]) if dn else "", "size": None, "magnet": True}
    import torrent as tmod
    if src.lower().startswith(("http://", "https://")):
        s = requests.Session()
        s.headers["User-Agent"] = UA
        s.headers.update({k: v for k, v in (headers or {}).items() if v})
        r = s.get(src, timeout=timeout)
        r.raise_for_status()
        data = r.content
    else:
        with open(src, "rb") as f:
            data = f.read()
    if not tmod.AVAILABLE:
        return {"kind": "torrent", "name": "", "size": None}
    lt = tmod.lt
    ti = lt.torrent_info(lt.bdecode(data))
    files = tmod.list_files(ti)
    return {"kind": "torrent", "name": ti.name(), "size": sum(sz for _, _, sz in files), "files": len(files)}
