"""Torrent downloads (magnet links and .torrent files) via libtorrent."""
import os
import base64
import threading
from urllib.parse import parse_qs, urlparse, unquote

import requests

from core import Item, safe_name, UA, resolve_folder

try:
    import libtorrent as lt
    AVAILABLE = True
except Exception:          # library missing (e.g. unsupported Python version)
    lt = None
    AVAILABLE = False


def is_torrent_source(text):
    t = (text or "").strip().lower()
    return t.startswith("magnet:") or t.split("?")[0].endswith(".torrent")


def magnet_name(uri):
    try:
        dn = parse_qs(urlparse(uri).query).get("dn")
        return unquote(dn[0]) if dn else ""
    except Exception:
        return ""


# Session-wide torrent limits in bytes/s (0 = none); set by the manager.
LIMITS = {"down": 0, "up": 0}


def set_session_limits(down, up):
    LIMITS["down"], LIMITS["up"] = max(0, int(down)), max(0, int(up))
    if Engine._inst is not None:
        Engine._inst.apply_limits()


def list_files(ti):
    """[(index, path, size)] for real files (padding files skipped)."""
    out = []
    if ti is None:
        return out
    fs = ti.files()
    for i in range(fs.num_files()):
        try:
            if fs.file_flags(i) & lt.file_storage.flag_pad_file:
                continue
        except Exception:
            pass
        out.append((i, fs.file_path(i).replace("\\", "/"), fs.file_size(i)))
    return out


def _num_files(ti):
    return ti.files().num_files() if ti is not None else 0


def _is_paused(status):
    try:
        return bool(status.flags & lt.torrent_flags.paused)
    except Exception:
        return bool(getattr(status, "paused", False))


class Engine:
    """One shared libtorrent session for the whole app."""
    _inst = None

    @classmethod
    def get(cls):
        if cls._inst is None:
            from manager import data_dir
            cls._inst = cls(data_dir())
        return cls._inst

    def __init__(self, folder):
        self.dir = os.path.join(folder, "torrents")
        os.makedirs(self.dir, exist_ok=True)
        cat = lt.alert.category_t
        self.ses = lt.session({
            "listen_interfaces": "0.0.0.0:6881,[::]:6881",
            "user_agent": "EDENLOAD/1.5",
            "enable_dht": True, "enable_lsd": True,
            "enable_upnp": True, "enable_natpmp": True,
            "alert_mask": cat.error_notification | cat.status_notification | cat.storage_notification,
        })
        self.apply_limits()
        self.items = []
        self.pending = 0
        self._lock = threading.Lock()

    def apply_limits(self):
        try:
            self.ses.apply_settings({"download_rate_limit": LIMITS["down"],
                                     "upload_rate_limit": LIMITS["up"]})
        except Exception:
            pass

    def resume_path(self, item_id):
        return os.path.join(self.dir, item_id + ".resume")

    def _item(self, handle):
        for it in self.items:
            if it.handle is not None and it.handle == handle:
                return it
        return None

    def request_save(self, item):
        h = item.handle
        if h is None or not h.is_valid():
            return
        try:
            st = h.status()
            if not st.has_metadata:
                return
            flags = lt.save_resume_flags_t.flush_disk_cache
            if hasattr(lt.save_resume_flags_t, "save_info_dict"):
                flags |= lt.save_resume_flags_t.save_info_dict
            h.save_resume_data(flags)
            with self._lock:
                self.pending += 1
        except Exception:
            pass

    def pump(self):
        for a in self.ses.pop_alerts():
            if isinstance(a, lt.save_resume_data_alert):
                it = self._item(a.handle)
                if it:
                    try:
                        data = lt.write_resume_data_buf(a.params)
                        tmp = self.resume_path(it.id) + ".tmp"
                        with open(tmp, "wb") as f:
                            f.write(data)
                        os.replace(tmp, self.resume_path(it.id))
                    except Exception:
                        pass
                with self._lock:
                    self.pending = max(0, self.pending - 1)
            elif isinstance(a, lt.save_resume_data_failed_alert):
                with self._lock:
                    self.pending = max(0, self.pending - 1)
            elif isinstance(a, (lt.torrent_error_alert, lt.file_error_alert)):
                it = self._item(a.handle)
                if it:
                    it.status = "error"
                    it.error = a.message()[:300]
            elif isinstance(a, lt.metadata_received_alert):
                it = self._item(a.handle)
                if it:
                    it.on_metadata()
                    self.request_save(it)   # persist the info dict right away

    def save_all_and_wait(self, timeout=5.0):
        import time
        for it in self.items:
            self.request_save(it)
        end = time.time() + timeout
        while self.pending and time.time() < end:
            self.ses.wait_for_alert(200)
            self.pump()

    def remove(self, item, delete_files):
        if item.handle is not None and item.handle.is_valid():
            try:
                if delete_files:
                    self.ses.remove_torrent(item.handle, lt.options_t.delete_files)
                else:
                    self.ses.remove_torrent(item.handle)
            except Exception:
                pass
        item.handle = None
        if item in self.items:
            self.items.remove(item)
        try:
            os.remove(self.resume_path(item.id))
        except OSError:
            pass


class TorrentDownload(Item):
    kind = "torrent"

    def __init__(self, source, save_dir, torrent_data=None, headers=None, seed=False,
                 ask_files=True, id=None):
        super().__init__(id)
        self.needs_selection = ask_files   # ask the user which files to download once we know them
        self.awaiting_files = False        # file list known, waiting for the user's choice
        self.file_priorities = []          # saved choice (0 = skip, 4 = download)
        self.source = source            # magnet:, http(s) link to a .torrent, or local .torrent path
        self.save_dir = save_dir
        self.save_path = resolve_folder(save_dir, "Torrents")
        self.torrent_data = torrent_data  # raw .torrent bytes, when we have them
        self.headers = headers or {}
        self.seed = seed
        self.handle = None
        self.name = magnet_name(source) if source.startswith("magnet:") else ""
        if not self.name and not source.startswith("magnet:"):
            self.name = os.path.splitext(os.path.basename(urlparse(source).path or source))[0]
        self.url = source
        if not self.torrent_data and os.path.isfile(source):
            try:
                with open(source, "rb") as f:
                    self.torrent_data = f.read()   # keep a copy, so moving/deleting the file is fine
            except OSError:
                pass
        self._done = 0
        self.upload = 0.0
        self.peers = 0
        self.phase = ""     # metadata | checking | "" (shown next to the status)
        self.seeding = False
        self.limit_up = 0   # this torrent's own upload limit, KB/s (0 = none)

    @property
    def done(self):
        return self._done

    # ---- lifecycle (no thread: libtorrent runs its own) ----
    def is_alive(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self):
        if not AVAILABLE:
            self.status = "error"
            self.error = "Torrent support isn't installed (needs Python 3.9–3.13 when building)."
            return False
        if self.is_alive():
            return False
        self.status = "downloading"
        self.error = ""
        if self.handle is not None and self.handle.is_valid():
            self.handle.resume()
            return True
        # adding may need a network fetch for http .torrent links → do it off the UI thread
        self._thread = threading.Thread(target=self._safe_add, daemon=True)
        self._thread.start()
        return True

    def _safe_add(self):
        try:
            self._add()
        except Exception as e:
            self.status = "error"
            self.error = str(e)[:300]

    def _load_data(self):
        if self.torrent_data:
            return
        src = self.source
        if src.lower().startswith(("http://", "https://")):
            s = requests.Session()
            s.headers["User-Agent"] = UA
            s.headers.update({k: v for k, v in self.headers.items() if v})
            r = s.get(src, timeout=30)
            r.raise_for_status()
            self.torrent_data = r.content
        elif os.path.isfile(src):
            with open(src, "rb") as f:
                self.torrent_data = f.read()

    def _add(self):
        eng = Engine.get()
        os.makedirs(self.save_path, exist_ok=True)
        rp = eng.resume_path(self.id)
        params = None
        if os.path.isfile(rp):
            try:
                with open(rp, "rb") as f:
                    params = lt.read_resume_data(f.read())
            except Exception:
                params = None
        if params is None:
            if self.source.startswith("magnet:"):
                params = lt.parse_magnet_uri(self.source)
            else:
                self._load_data()
                if not self.torrent_data:
                    raise IOError("Couldn't read the .torrent file")
                params = lt.add_torrent_params()
                params.ti = lt.torrent_info(lt.bdecode(self.torrent_data))
        params.save_path = self.save_path
        ti = getattr(params, "ti", None)
        if ti is not None and self.needs_selection and len(list_files(ti)) > 1:
            params.file_priorities = [0] * _num_files(ti)   # nothing downloads until the user picks
            self.awaiting_files = True
        elif ti is not None and self.file_priorities and len(self.file_priorities) == _num_files(ti):
            params.file_priorities = list(self.file_priorities)
        h = eng.ses.add_torrent(params)
        h.unset_flags(lt.torrent_flags.auto_managed)   # we decide when it runs, not the session queue
        if self._stop.is_set() or self.status != "downloading":
            h.pause()
        else:
            h.resume()
        self.handle = h
        self._apply_handle_limits()
        if self not in eng.items:
            eng.items.append(self)

    # ---- speed limits ----
    def set_limit(self, kb):
        self.limit = max(0, int(kb or 0))      # libtorrent does the limiting, not our limiter
        self._apply_handle_limits()

    def set_upload_limit(self, kb):
        self.limit_up = max(0, int(kb or 0))
        self._apply_handle_limits()

    def _apply_handle_limits(self):
        h = self.handle
        if h is None or not h.is_valid():
            return
        try:
            h.set_download_limit(self.limit * 1024 if self.limit else -1)
            h.set_upload_limit(self.limit_up * 1024 if self.limit_up else -1)
        except Exception:
            pass

    # ---- file selection ----
    def torrent_info(self):
        h = self.handle
        if h is not None and h.is_valid():
            try:
                return h.torrent_file()
            except Exception:
                return None
        return None

    def has_metadata(self):
        return self.torrent_info() is not None

    def files(self):
        return list_files(self.torrent_info())

    def current_priorities(self):
        h = self.handle
        try:
            return list(h.get_file_priorities())
        except Exception:
            try:
                return list(h.file_priorities())
            except Exception:
                return list(self.file_priorities)

    def on_metadata(self):
        """Magnet link just got its file list: hold everything until the user chooses."""
        ti = self.torrent_info()
        if ti is None:
            return
        if self.needs_selection and len(list_files(ti)) > 1:
            self.handle.prioritize_files([0] * _num_files(ti))
            self.awaiting_files = True
        else:
            self.needs_selection = False

    def apply_selection(self, priorities):
        """priorities: list with one entry per file in the torrent (0 = skip, 4 = download)."""
        self.file_priorities = list(priorities)
        self.needs_selection = False
        self.awaiting_files = False
        h = self.handle
        if h is not None and h.is_valid():
            h.prioritize_files(self.file_priorities)
            if self.status == "done" and any(self.file_priorities):
                self.status = "queued" if not self.is_alive() else "downloading"
                self.seeding = False
            Engine.get().request_save(self)

    def pause(self):
        if self.status in ("downloading", "queued", "pausing") or self.seeding:
            if self.handle is not None and self.handle.is_valid():
                self.handle.pause()
                Engine.get().request_save(self)
            self.seeding = False
            if self.status != "done":
                self.status = "paused"
            self.speed = self.upload = 0.0

    def stop_for_remove(self):
        self.status = "removed"
        self._stop.set()

    def update_speed(self):
        h = self.handle
        if h is None or not h.is_valid():
            if self.status != "downloading":
                self.speed = 0.0
            return
        try:
            s = h.status()
        except Exception:
            return
        if s.name:
            self.name = safe_name(s.name)
        self.total = s.total_wanted
        self._done = s.total_wanted_done
        self.peers = s.num_peers
        st = lt.torrent_status.states
        if not s.has_metadata:
            self.phase = "metadata"
        elif s.state in (st.checking_files, st.checking_resume_data):
            self.phase = "checking"
        else:
            self.phase = ""
        running = not _is_paused(s)
        self.speed = float(s.download_rate) if running else 0.0
        self.upload = float(s.upload_rate) if running else 0.0
        if self.awaiting_files:
            self.speed = 0.0
            return
        if self.status == "downloading" and s.has_metadata and s.is_finished and s.total_wanted > 0:
            self.path = os.path.join(self.save_path, s.name)
            self.status = "done"
            self.speed = 0.0
            Engine.get().request_save(self)
            if self.seed:
                self.seeding = True
            else:
                h.pause()
                self.upload = 0.0

    def delete_files(self):
        pass   # handled by Engine.remove(delete_files=True)

    # ---- persistence ----
    def to_dict(self):
        return {
            "id": self.id, "kind": "torrent", "source": self.source, "save_dir": self.save_dir,
            "save_path": self.save_path, "name": self.name, "total": self.total, "done": self._done,
            "path": self.path, "status": self.status, "error": self.error, "added": self.added,
            "seed": self.seed, "headers": self.headers,
            "needs_selection": self.needs_selection, "awaiting_files": self.awaiting_files,
            "file_priorities": self.file_priorities,
            "limit": self.limit, "limit_up": self.limit_up,
            "torrent_b64": base64.b64encode(self.torrent_data).decode() if self.torrent_data else "",
        }

    @classmethod
    def from_dict(cls, d):
        data = base64.b64decode(d["torrent_b64"]) if d.get("torrent_b64") else None
        it = cls(d["source"], d["save_dir"], data, d.get("headers"), d.get("seed", False),
                 d.get("needs_selection", False), id=d["id"])
        it.file_priorities = d.get("file_priorities", [])
        it.limit = d.get("limit", 0)
        it.limit_up = d.get("limit_up", 0)
        it.save_path = d.get("save_path", it.save_path)
        for k in ("name", "total", "path", "status", "error", "added"):
            if d.get(k) not in (None, ""):
                setattr(it, k, d[k])
        it._done = d.get("done", 0)
        return it
