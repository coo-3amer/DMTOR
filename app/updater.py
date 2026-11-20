"""Updates for the Windows 7 edition: version.txt + Setup on the 'download-win7' branch."""
import os
import sys
import tempfile

import requests

from version import VERSION, REPO, BRANCH

RAW = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/"


def _v(s):
    out = []
    for p in str(s).strip().lstrip("v").split("."):
        try:
            out.append(int(p))
        except ValueError:
            out.append(0)
    return tuple(out)


def check_latest(timeout=10):
    r = requests.get(RAW + "version.txt", timeout=timeout, headers={"Cache-Control": "no-cache"})
    r.raise_for_status()
    latest = r.text.strip()
    return {"version": latest, "newer": _v(latest) > _v(VERSION), "url": RAW + "MZ-DManager-Lite-Setup.exe"}


def download(url, progress=None):
    path = os.path.join(tempfile.gettempdir(), "MZ-DManager-Lite-Setup.exe")
    with requests.get(url, stream=True, timeout=30) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(256 * 1024):
                f.write(chunk)
                done += len(chunk)
                if progress:
                    progress(done, total)
    return path


def install_key():
    if sys.platform != "win32":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\MZ-DManager Lite") as k:
            return winreg.QueryValueEx(k, "InstallKey")[0] or ""
    except OSError:
        return ""


def run_installer(path):
    """Start the Setup (Windows asks for admin approval); it closes the app, updates it and reopens it."""
    args = ["/SILENT", "/NORESTART", "/CLOSEAPPLICATIONS"]
    key = install_key()
    if key:
        args.append('/PASSWORD="' + key.replace('"', "") + '"')
    import ctypes
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", path, " ".join(args), None, 1)
    if rc <= 32:
        raise OSError("Admin approval was not given" if rc == 5 else "Couldn't start the Setup (%d)" % rc)
