"""Hand-drawn line icons for MZ-DManager (rendered from inline SVG)."""
from PySide6.QtCore import Qt, QByteArray
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

_FILE = '<path d="M14 3.5H7a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5z"/><path d="M14 3.5v5h5"/>'

PATHS = {
    "add": '<circle cx="12" cy="12" r="8.5"/><path d="M12 8v8M8 12h8"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z"/>',
    "pause": '<rect x="6.5" y="5" width="3.5" height="14" rx="1"/><rect x="14" y="5" width="3.5" height="14" rx="1"/>',
    "trash": '<path d="M4 7h16M9.5 7V4.5h5V7M6.5 7l.9 12.5h9.2L17.5 7M10 11v5.5M14 11v5.5"/>',
    "resume_all": '<path d="M4 6v12l7-6zM12.5 6v12l7-6z"/>',
    "pause_all": '<rect x="5.5" y="5.5" width="13" height="13" rx="2.5"/>',
    "open": _FILE + '<path d="M9.5 14.5 14 10M10.5 10H14v3.5"/>',
    "folder": '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "settings": '<path d="M4 7h9M17 7h3M15 5v4M4 12h3M11 12h9M9 10v4M4 17h11M19 17h1M17 15v4"/>',
    "link": '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 1 0-5.66-5.66l-1.2 1.2"/>'
            '<path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 1 0 5.66 5.66l1.2-1.2"/>',
    "all": '<path d="M4 6.5h16M4 12h16M4 17.5h16"/>',
    "active": '<path d="M12 4v11M7.5 10.5 12 15l4.5-4.5M5 20h14"/>',
    "done": '<circle cx="12" cy="12" r="8.5"/><path d="m8.5 12.2 2.4 2.4 4.6-5"/>',
    "paused": '<circle cx="12" cy="12" r="8.5"/><path d="M10 9v6M14 9v6"/>',
    "error": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5.5M12 16.2v.3"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2.5"/><path d="m16 10.5 5-3v9l-5-3z"/>',
    "music": '<path d="M9 17.5V5.5l10-2v12"/><circle cx="6.5" cy="17.5" r="2.5"/><circle cx="16.5" cy="15.5" r="2.5"/>',
    "programs": '<rect x="4" y="4" width="16" height="16" rx="3.5"/><path d="M4 9h16M7.5 6.5h.01M10 6.5h.01"/>',
    "documents": _FILE + '<path d="M8.5 13h7M8.5 16.5h4.5"/>',
    "compressed": '<rect x="3.5" y="4" width="17" height="4.5" rx="1.2"/>'
                  '<path d="M5 8.5v9.5a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5M10 12.5h4"/>',
    "images": '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><circle cx="9" cy="9.5" r="1.6"/>'
              '<path d="m4 17 5-5 4 4 2.5-2.5L20 18"/>',
    "other": _FILE,
    "catch": '<path d="M12 3.5 5 6.5v5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9v-5z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
    "catch_off": '<path d="M12 3.5 5 6.5v5c0 4.2 2.9 7.6 7 9 4.1-1.4 7-4.8 7-9v-5z"/><path d="M9.5 9.5l5 5M14.5 9.5l-5 5"/>',
    "gauge": '<path d="M4.5 16.5a8 8 0 1 1 15 0"/><path d="M12 13.5 15.5 9"/><circle cx="12" cy="14" r="1.3"/>',
    "upload": '<path d="M12 20V9M7.5 13.5 12 9l4.5 4.5M5 4h14"/>',
    "power": '<path d="M12 3.5v8"/><path d="M7 6.3a7.5 7.5 0 1 0 10 0"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "update": '<path d="M4.5 12a7.5 7.5 0 0 1 13-5.1L20 9.5M20 4.5v5h-5"/><path d="M19.5 12a7.5 7.5 0 0 1-13 5.1L4 14.5M4 19.5v-5h5"/>',
    "palette": '<path d="M12 3.5a8.5 8.5 0 1 0 0 17c1.2 0 1.8-.8 1.8-1.7 0-1.3-1.1-1.6-1.1-2.7 0-1 .8-1.6 1.8-1.6h2.2a3.8 3.8 0 0 0 3.8-3.8C20.5 6.6 16.7 3.5 12 3.5z"/><circle cx="7.8" cy="11" r="1"/><circle cx="10.5" cy="7.3" r="1"/><circle cx="15" cy="7.5" r="1"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4 4"/>',
    "cloud_dl": '<path d="M7.5 18.5a4.5 4.5 0 0 1-.6-8.96A6 6 0 0 1 18.4 8.6a4 4 0 0 1-.4 7.9"/><path d="M12 11v8M9 16l3 3 3-3"/>',
    "link_add": '<path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 1 0-5.66-5.66l-1.2 1.2"/><path d="M13 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 4.2 6.6"/><path d="M17 15v6M14 18h6"/>',
    "stop": '<rect x="5.5" y="5.5" width="13" height="13" rx="2.5"/>',
    "stop_all": '<path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5"/><path d="M12 7.5V12l2.5 1.5"/><rect x="15" y="15" width="6" height="6" rx="1.2"/>',
    "share": '<path d="M14 5l6 6-6 6"/><path d="M20 11h-7a8 8 0 0 0-8 8"/>',
    "gear": '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
    "calendar": '<rect x="3.5" y="5" width="15" height="14" rx="2.5"/><path d="M3.5 9.5h15M8 3v4M14 3v4"/><circle cx="17.5" cy="17.5" r="3.5"/><path d="M17.5 16v1.6l1 .8"/>',
    "disk": '<rect x="3.5" y="5" width="17" height="6" rx="2"/><rect x="3.5" y="13" width="17" height="6" rx="2"/><path d="M7 8h.01M7 16h.01"/>',
    "dots": '<path d="M5 12h.01M12 12h.01M19 12h.01"/>',
    "chev_up": '<path d="m6 15 6-6 6 6"/>',
    "chev_down": '<path d="m6 9 6 6 6-6"/>',
    "stack": '<rect x="8" y="3.5" width="12.5" height="12.5" rx="2.5"/><path d="M16 20.5H6a2.5 2.5 0 0 1-2.5-2.5V8"/>',
    "unfinished": '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v3"/><path d="M3.5 7.5v9a2 2 0 0 0 2 2h7"/><path d="M17.5 14v7M14.5 18l3 3 3-3"/>',
    "finished": '<path d="M3.5 7.5a2 2 0 0 1 2-2h4l2 2h7a2 2 0 0 1 2 2v3"/><path d="M3.5 7.5v9a2 2 0 0 0 2 2h7"/><path d="m14.5 18 2 2 4-4.5"/>',
    "broom": '<path d="M14 4l6 6M9.5 8.5l6 6"/><path d="M9.5 8.5 4 14c-1 1-1 3 1 5s4 2 5 1l5.5-5.5"/>',
    "home": '<path d="M4 10.5 12 4l8 6.5V19a1.5 1.5 0 0 1-1.5 1.5H15v-6H9v6H5.5A1.5 1.5 0 0 1 4 19z"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.5 2.6 3.6 5.4 3.6 8.5s-1.1 5.9-3.6 8.5c-2.5-2.6-3.6-5.4-3.6-8.5S9.5 6.1 12 3.5z"/>',
    "wifi": '<path d="M3.5 9.5a12 12 0 0 1 17 0M6.5 12.8a7.7 7.7 0 0 1 11 0M9.5 16a3.4 3.4 0 0 1 5 0"/><path d="M12 19.5h.01"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "magnet": '<path d="M5 3.5h4.5v8a2.5 2.5 0 0 0 5 0v-8H19v8a7 7 0 0 1-14 0z"/><path d="M5 7.5h4.5M14.5 7.5H19"/>',
}

CATEGORY_ICON = {
    "Video": ("video", "#ff7a7a"),
    "Music": ("music", "#c48cff"),
    "Programs": ("programs", "#5b9cff"),
    "Documents": ("documents", "#46c2f5"),
    "Compressed": ("compressed", "#f2a93b"),
    "Images": ("images", "#3fd39a"),
    "Torrents": ("magnet", "#2dd4bf"),
    "Other": ("other", "#9aa3af"),
}

_cache = {}


def icon(name, color="#d8dce2", size=20, stroke=1.9):
    key = (name, color, size, stroke)
    if key in _cache:
        return _cache[key]
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">'
           f'{PATHS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    ic = QIcon()
    for scale in (1, 2, 3):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(scale)
        ic.addPixmap(pm)
    _cache[key] = ic
    return ic


def pixmap(name, color, size):
    return icon(name, color, size).pixmap(size, size)
