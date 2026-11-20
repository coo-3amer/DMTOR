"""YouTube and other video sites on Windows 7.

The official yt-dlp no longer runs on Windows 7, so the "video add-on" (downloaded once, on request) is:
  * yt-dlp built for Windows 7 (github.com/nicolaasjan/yt-dlp, unofficial)
  * QuickJS (bellard.org) — the small JavaScript engine yt-dlp needs to solve YouTube's checks
  * ffmpeg (64-bit Windows only) — joins HD video and sound into one file
All three live in %APPDATA%\\MZ-DManager Lite\\tools and run as separate programs.
"""
import os
import re
import sys
import json
import time
import shutil
import zipfile
import subprocess

import requests

import core
from core import Item, safe_name

VIDEO_SITES = re.compile(r"(youtube\.com|youtu\.be|facebook\.com|fb\.watch|instagram\.com|tiktok\.com|twitter\.com|"
                         r"x\.com|vimeo\.com|dailymotion\.com|twitch\.tv|reddit\.com|soundcloud\.com)", re.I)

QUALITIES = [("best", "Best"), ("1080", "1080p"), ("720", "720p"), ("480", "480p"), ("360", "360p"),
             ("audio", "Sound only (m4a)")]

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = {"User-Agent": "MZ-DManager-Lite", "Accept": "application/vnd.github+json"}


def is_video_url(url):
    return bool(VIDEO_SITES.search(url or ""))


def tools_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "MZ-DManager Lite", "tools")
    os.makedirs(d, exist_ok=True)
    return d


def is_64bit_windows():
    return (os.environ.get("PROCESSOR_ARCHITEW6432") or os.environ.get("PROCESSOR_ARCHITECTURE", "")).upper() \
        in ("AMD64", "ARM64")


def ytdlp_path():
    p = os.path.join(tools_dir(), "yt-dlp.exe")
    return p if os.path.isfile(p) else ""


def qjs_path():
    p = os.path.join(tools_dir(), "qjs.exe")
    return p if os.path.isfile(p) else ""


def ffmpeg_path():
    p = os.path.join(tools_dir(), "ffmpeg.exe")
    return p if os.path.isfile(p) else ""


def ready():
    return bool(ytdlp_path() and qjs_path())


# ---------------------------------------------------------------- installing the add-on
def _fetch(url, dest, progress=None, label=""):
    tmp = dest + ".tmp"
    with requests.get(url, stream=True, timeout=30, headers={"User-Agent": "MZ-DManager-Lite"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(label, done, total)
    os.replace(tmp, dest)
    return dest


def _ytdlp_url():
    r = requests.get("https://api.github.com/repos/nicolaasjan/yt-dlp/releases/latest", timeout=20, headers=UA)
    r.raise_for_status()
    want = "yt-dlp_win7.exe" if is_64bit_windows() else "yt-dlp_x86_win7.exe"
    for a in r.json().get("assets", []):
        if a.get("name") == want:
            return a["browser_download_url"]
    raise IOError(f"{want} not found in the latest release")


QJS_VERSIONS = ["2026-06-04", "2025-09-13", "2025-04-26"]


def _install_qjs(progress):
    arch = "x86_64" if is_64bit_windows() else "i686"
    last = None
    for v in QJS_VERSIONS:
        url = f"https://bellard.org/quickjs/binary_releases/quickjs-win-{arch}-{v}.zip"
        z = os.path.join(tools_dir(), "qjs.zip")
        try:
            _fetch(url, z, progress, "JavaScript engine")
            with zipfile.ZipFile(z) as zf:
                for n in zf.namelist():
                    base = os.path.basename(n)
                    if base.lower() in ("qjs.exe",) or base.lower().endswith(".dll"):
                        with zf.open(n) as src, open(os.path.join(tools_dir(), base), "wb") as dst:
                            shutil.copyfileobj(src, dst)
            os.remove(z)
            if qjs_path():
                return
        except Exception as e:
            last = e
    raise IOError(f"Couldn't get QuickJS: {last}")


def _install_ffmpeg(progress):
    if not is_64bit_windows():
        return                                   # no ffmpeg builds for 32-bit Windows 7
    url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-lgpl.zip"
    z = os.path.join(tools_dir(), "ffmpeg.zip")
    _fetch(url, z, progress, "Video joiner (ffmpeg)")
    with zipfile.ZipFile(z) as zf:
        member = next((n for n in zf.namelist() if n.lower().endswith("/bin/ffmpeg.exe")), None)
        if member:
            with zf.open(member) as src, open(os.path.join(tools_dir(), "ffmpeg.exe"), "wb") as dst:
                shutil.copyfileobj(src, dst)
    os.remove(z)


def install(progress=None, with_ffmpeg=True):
    """Download the video add-on. progress(label, done, total)."""
    if not ytdlp_path():
        _fetch(_ytdlp_url(), os.path.join(tools_dir(), "yt-dlp.exe"), progress, "Video downloader (yt-dlp)")
    if not qjs_path():
        _install_qjs(progress)
    if with_ffmpeg and not ffmpeg_path():
        try:
            _install_ffmpeg(progress)
        except Exception:
            pass                                 # still works without it, up to the best single file


def update_ytdlp():
    """yt-dlp updates itself (YouTube changes often)."""
    if ytdlp_path():
        try:
            subprocess.run([ytdlp_path(), "-U"], capture_output=True, timeout=120, creationflags=NO_WINDOW)
        except Exception:
            pass


# ---------------------------------------------------------------- running yt-dlp
def base_args():
    a = [ytdlp_path(), "--no-config", "--no-playlist", "--windows-filenames", "--no-colors",
         "--remote-components", "ejs:github"]
    if qjs_path():
        a += ["--no-js-runtimes", "--js-runtimes", "quickjs:" + qjs_path()]
    if ffmpeg_path():
        a += ["--ffmpeg-location", ffmpeg_path()]
    return a


def fmt_for(quality):
    if quality == "audio":
        return "bestaudio[ext=m4a]/bestaudio"
    if not ffmpeg_path():                         # can't join separate video + sound
        h = "" if quality == "best" else f"[height<={quality}]"
        return f"best{h}[acodec!=none][vcodec!=none]/best"
    if quality == "best":
        return "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
    return f"bv*[height<={quality}][ext=mp4]+ba[ext=m4a]/bv*[height<={quality}]+ba/b[height<={quality}]/b"


def probe(url, timeout=90):
    """{'kind': 'video', 'name', 'duration', 'site'} or {'error'}."""
    if not ready():
        return {"error": "addon"}
    try:
        p = subprocess.run(base_args() + ["-J", "--skip-download", url], capture_output=True, timeout=timeout,
                           creationflags=NO_WINDOW)
        if p.returncode != 0:
            err = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            msg = next((l for l in reversed(err) if l.startswith("ERROR")), err[-1] if err else "failed")
            return {"error": msg.replace("ERROR: ", "")[:200]}
        info = json.loads(p.stdout.decode("utf-8", "replace") or "{}")
        return {"kind": "video", "name": info.get("title") or "video", "duration": info.get("duration") or 0,
                "site": info.get("extractor_key") or ""}
    except subprocess.TimeoutExpired:
        return {"error": "The site took too long to answer"}
    except Exception as e:
        return {"error": str(e)[:200]}


class VideoDownload(Item):
    kind = "video"

    def __init__(self, url, save_dir, quality="best", title="", categorize=True, id=None):
        super().__init__(id)
        self.url = url
        self.save_dir = save_dir
        self.quality = quality
        self.name = title
        self.categorize = categorize
        self._done = 0
        self._stage = 0               # each stream (video, then sound) counts as a stage
        self._proc = None

    @property
    def done(self):
        return self._done

    def _folder(self):
        cat = "Music" if self.quality == "audio" else "Video"
        return core.resolve_folder(self.save_dir, cat) if self.categorize else self.save_dir

    def _run(self):
        if not ready():
            raise IOError("The video add-on isn't installed — open Add download and get it first.")
        folder = self._folder()
        os.makedirs(folder, exist_ok=True)
        name = safe_name(self.name) if self.name else "%(title)s"
        out = os.path.join(folder, name[:150] + " [%(id)s].%(ext)s" if not self.name else name[:150] + ".%(ext)s")
        args = base_args() + ["-f", fmt_for(self.quality), "-o", out, "--newline", "--progress",
                              "--progress-template", "download:MZP %(progress.downloaded_bytes)s "
                                                     "%(progress.total_bytes)s %(progress.total_bytes_estimate)s",
                              "--print", "after_move:MZF %(filepath)s", "--no-simulate", "-N", "4"]
        if self.quality != "audio" and ffmpeg_path():
            args += ["--merge-output-format", "mp4"]
        if self.limit or core.GLOBAL_LIMIT.rate:
            rate = min(x for x in (self.limit * 1024, core.GLOBAL_LIMIT.rate) if x)
            args += ["-r", str(int(rate))]
        args.append(self.url)
        self._proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      creationflags=NO_WINDOW)
        base_done = 0
        last_total = 0
        last_dl = 0
        errors = []

        import threading

        def read_err():
            for line in self._proc.stderr:
                t = line.decode("utf-8", "replace").strip()
                if t.startswith("ERROR"):
                    errors.append(t.replace("ERROR: ", ""))
        threading.Thread(target=read_err, daemon=True).start()

        for raw in self._proc.stdout:
            if self._stop.is_set():
                break
            line = raw.decode("utf-8", "replace").strip()
            if line.startswith("MZP "):
                parts = line.split()
                try:
                    dl = int(float(parts[1])) if parts[1] != "NA" else 0
                    tot = parts[2] if parts[2] != "NA" else parts[3]
                    tot = int(float(tot)) if tot != "NA" else 0
                except (ValueError, IndexError):
                    continue
                if dl < last_dl:                  # a new stream started (e.g. the sound after the video)
                    base_done += last_total or last_dl
                    self._stage += 1
                last_dl, last_total = dl, tot
                self._done = base_done + dl
                self.total = max(self.total, base_done + tot)
            elif line.startswith("MZF "):
                self.path = line[4:].strip()
                self.name = os.path.basename(self.path)
        if self._stop.is_set():
            self._kill()
            self._ended_by_stop()
            return
        rc = self._proc.wait()
        if rc == 0 and (not self.path or os.path.isfile(self.path)):
            self._done = self.total = max(self.total, self._done)
            self.status = "done"
            self.speed = 0.0
        else:
            raise IOError(errors[-1] if errors else f"yt-dlp stopped (code {rc})")

    def _kill(self):
        p = self._proc
        if p and p.poll() is None:
            try:
                subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True,
                               creationflags=NO_WINDOW, timeout=10)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def pause(self):
        super().pause()
        if self._stop.is_set():
            self._kill()

    def stop_for_remove(self):
        super().stop_for_remove()
        self._kill()

    def delete_files(self):
        if self.path and os.path.isfile(self.path):
            try:
                os.remove(self.path)
            except OSError:
                pass

    def to_dict(self):
        d = {k: getattr(self, k) for k in ("id", "kind", "url", "save_dir", "quality", "name", "categorize",
                                           "total", "path", "status", "error", "added", "limit")}
        d["done"] = self._done
        return d

    @classmethod
    def from_dict(cls, d):
        it = cls(d["url"], d["save_dir"], d.get("quality", "best"), d.get("name", ""), d.get("categorize", True),
                 id=d["id"])
        for k in ("total", "path", "status", "error", "added"):
            if k in d:
                setattr(it, k, d[k])
        it._done = d.get("done", 0)
        it.set_limit(d.get("limit", 0))
        return it
