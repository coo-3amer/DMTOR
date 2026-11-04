"""Hand-drawn line icons for DMTOR (rendered from inline SVG)."""
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
