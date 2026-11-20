"""Interface language: English (default) or Arabic.

Fixed texts are translated by walking the widgets (translate_tree), so most code keeps plain
English strings. Texts with numbers in them go through tr("… {n} …").format(n=…).
"""
import re

LANG = "en"
LANGUAGES = [("en", "English"), ("ar", "العربية")]


def set_lang(code):
    global LANG
    LANG = code if code in ("en", "ar") else "en"


def is_rtl():
    return LANG == "ar"


AR = {
    # ---- main window ----
    "Add download": "إضافة تحميل",
    "Add a link or a torrent (Ctrl+N)": "إضافة رابط أو تورنت (Ctrl+N)",
    "All downloads": "كل التحميلات",
    "Downloading": "جاري التحميل",
    "Completed": "مكتملة",
    "Paused": "متوقفة",
    "Failed": "فشلت",
    "Scheduled": "مجدولة",
    "TORRENTS": "التورنت",
    "All torrents": "كل التورنت",
    "Seeding": "مشاركة",
    "Speed limit": "حد السرعة",
    "Speed limits": "حدود السرعة",
    "Speed: limited": "السرعة: محدودة",
    "Speed: {r}": "السرعة: {r}",
    "Speed limit: {r}": "حد السرعة: {r}",
    "Speed limit on": "حد السرعة مفعّل",
    "When done": "بعد الانتهاء",
    "When done: Sleep": "بعد الانتهاء: سكون",
    "When done: Shut down": "بعد الانتهاء: إطفاء",
    "When done: Close": "بعد الانتهاء: إغلاق",
    "Today": "اليوم",
    "Yesterday": "أمس",
    "When downloads finish": "عند انتهاء التحميلات",
    "When downloads finish: {a}": "عند انتهاء التحميلات: {a}",
    "Settings": "الإعدادات",
    "Connect browser": "ربط المتصفح",
    "More": "المزيد",
    "Resume all": "استئناف الكل",
    "Stop all": "إيقاف الكل",
    "Delete all": "حذف الكل",
    "Open .torrent": "فتح ملف تورنت",
    "Resume everything in this list": "استئناف كل ما في هذه القائمة",
    "Stop everything in this list": "إيقاف كل ما في هذه القائمة",
    "Delete all downloads in this list": "حذف كل التحميلات في هذه القائمة",
    "Open .torrent files (Ctrl+O). Magnet links: use Add download":
        "فتح ملفات تورنت (Ctrl+O). روابط الماجنت: استخدم إضافة تحميل",
    "Search": "بحث",
    "All types": "كل الأنواع",
    "All": "الكل",
    "Video": "فيديو",
    "Music": "موسيقى",
    "Docs": "مستندات",
    "Apps": "برامج",
    "Archives": "مضغوطة",
    "Images": "صور",
    "Others": "أخرى",
    "Select all": "تحديد الكل",
    "Select every download in this list (Ctrl+A)": "تحديد كل التحميلات في هذه القائمة (Ctrl+A)",
    "Newest first": "الأحدث أولاً",
    "Oldest first": "الأقدم أولاً",
    "Name": "الاسم",
    "Size": "الحجم",
    "Status": "الحالة",
    "Sort: {s}": "ترتيب: {s}",
    "TODAY": "اليوم",
    "YESTERDAY": "أمس",
    "THIS WEEK": "هذا الأسبوع",
    "EARLIER": "أقدم",
    "{n} selected": "{n} محدد",
    "{n} active  ·  {s}/s": "{n} نشط  ·  \u2066{s}/s\u2069",
    "{n} items": "{n} عنصر",
    "{n} item": "عنصر واحد",
    "Resume": "استئناف",
    "Stop": "إيقاف",
    "Folder": "المجلد",
    "Copy link": "نسخ الرابط",
    "Delete": "حذف",
    "Clear selection": "إلغاء التحديد",
    "Browser: catching": "المتصفح: يلتقط",
    "Browser: not catching": "المتصفح: لا يلتقط",
    "Catching downloads from the browser — click to turn off": "يلتقط التحميلات من المتصفح — اضغط للإيقاف",
    "Not catching — the browser downloads files itself. Click to turn on":
        "لا يلتقط — المتصفح يحمّل الملفات بنفسه. اضغط للتشغيل",
    "{s} free": "{s} متاح",
    "{a} free of {b}": "{a} متاح من {b}",
    "No downloads yet": "لا توجد تحميلات بعد",
    "Click a download link in Chrome or Edge and it lands here.\nOr press + to paste a link, or drop a .torrent file here.":
        "اضغط على أي رابط تحميل في كروم أو إيدج وسيظهر هنا.\nأو اضغط + للصق رابط، أو اسحب ملف تورنت إلى هنا.",
    "Nothing here": "لا يوجد شيء هنا",
    "No downloads match this view.": "لا توجد تحميلات في هذا العرض.",
    "No downloads match this view or search.": "لا توجد تحميلات تطابق هذا العرض أو البحث.",
    "No torrents yet": "لا يوجد تورنت بعد",
    "Open a .torrent file, paste a magnet link in Add download,\nor drop a .torrent file here.":
        "افتح ملف تورنت، أو الصق رابط ماجنت في إضافة تحميل،\nأو اسحب ملف تورنت إلى هنا.",
    "Torrents": "التورنت",
    # rows
    "Choose files to start": "اختر الملفات للبدء",
    "Getting info…": "جاري جلب المعلومات…",
    "Checking…": "جاري الفحص…",
    "Waiting in queue": "في قائمة الانتظار",
    "Stopping…": "جاري الإيقاف…",
    "Stopped": "متوقف",
    "Stopped at {p}%": "توقف عند \u2066{p}%\u2069",
    "{a} of {b}": "{a} من {b}",
    "{s}/s": "\u2066{s}/s\u2069",
    "{t} left": "متبقي {t}",
    "{n} peers": "{n} نظير",
    "will restart (no resume)": "سيبدأ من جديد (لا يدعم الاستئناف)",
    "Completed · seeding": "مكتمل · مشاركة",
    "Failed": "فشل",
    "scheduled": "مجدول",
    "max {r}": "حد {r}",
    # menus
    "Add URL…": "إضافة رابط…",
    "Open torrent file…": "فتح ملف تورنت…",
    "Open downloads folder": "فتح مجلد التحميلات",
    "Catch browser downloads": "التقاط تحميلات المتصفح",
    "Scheduler…": "الجدولة…",
    "Schedule…": "الجدولة…",
    "Disk Cleaner…": "منظف القرص…",
    "Disk Cleaner": "منظف القرص",
    "Theme": "المظهر",
    "Connect browser…": "ربط المتصفح…",
    "Check for updates": "البحث عن تحديثات",
    "Quit MZ-DManager": "إغلاق MZ-DManager",
    "Quit": "خروج",
    "Open MZ-DManager": "فتح MZ-DManager",
    "Limit speed": "تحديد السرعة",
    "Pause all": "إيقاف الكل",
    "WHEN ALL DOWNLOADS FINISH": "عند انتهاء كل التحميلات",
    "Do nothing": "لا شيء",
    "Put the computer to sleep": "وضع الكمبيوتر في السكون",
    "Shut down the computer": "إيقاف تشغيل الكمبيوتر",
    "Close MZ-DManager": "إغلاق MZ-DManager",
    "No limit": "بدون حد",
    "Custom…": "مخصص…",
    "Download speed limit": "حد سرعة التحميل",
    "Torrent download limit": "حد تحميل التورنت",
    "Torrent upload limit": "حد رفع التورنت",
    "Speed limits…": "حدود السرعة…",
    "Open file": "فتح الملف",
    "Show in folder": "عرض في المجلد",
    "Choose files…": "اختيار الملفات…",
    "Remove from schedule": "إزالة من الجدولة",
    "Add to schedule": "إضافة للجدولة",
    "Speed limit for this download": "حد السرعة لهذا التحميل",
    "Limit upload": "تحديد الرفع",
    "Upload limit for this torrent": "حد الرفع لهذا التورنت",
    "Delete…": "حذف…",
    "Retry": "إعادة المحاولة",
    "Pause": "إيقاف مؤقت",
    "Open torrent files": "فتح ملفات تورنت",
    "Open torrent file": "فتح ملف تورنت",
    "Torrent files (*.torrent)": "ملفات تورنت (*.torrent)",
    # banner / updates
    "Update now": "تحديث الآن",
    "Skip this version": "تخطي هذا الإصدار",
    "Later": "لاحقاً",
    "Installing the update — MZ-DManager will reopen by itself…": "جاري تثبيت التحديث — سيفتح MZ-DManager تلقائياً…",
    "Download complete": "اكتمل التحميل",
    "All downloads finished.": "انتهت كل التحميلات.",
    "Still running in the tray and catching browser downloads.\nRight-click the tray icon → Quit to exit.":
        "البرنامج ما زال يعمل بجانب الساعة ويلتقط تحميلات المتصفح.\nاضغط بزر الماوس الأيمن على الأيقونة ← خروج للإغلاق.",
    # delete
    "Delete all {n} downloads?": "حذف كل التحميلات ({n})؟",
    "Delete all {n} download?": "حذف التحميل؟",
    "They're removed from the list. Running downloads stop first.": "ستُزال من القائمة. التحميلات الجارية تتوقف أولاً.",
    "Also delete the files from my PC": "حذف الملفات من الكمبيوتر أيضاً",
    "Only finished downloads ({n})": "التحميلات المكتملة فقط ({n})",
    "Cancel": "إلغاء",
    "Remove {n} downloads?": "إزالة {n} تحميلات؟",
    "Remove {n} download?": "إزالة التحميل؟",
    "You can keep the file on disk or delete it too.": "يمكنك إبقاء الملف على القرص أو حذفه أيضاً.",
    "Remove from list": "إزالة من القائمة",
    "Delete file too": "حذف الملف أيضاً",
    # add dialog
    "New download": "تحميل جديد",
    "Paste from clipboard": "لصق من الحافظة",
    "Open a .torrent file": "فتح ملف تورنت",
    "Video (YouTube, Facebook, Instagram, TikTok…)": "فيديو (يوتيوب، فيسبوك، إنستجرام، تيك توك…)",
    "Torrent (magnet link or .torrent file)": "تورنت (رابط ماجنت أو ملف تورنت)",
    "File": "ملف",
    "Optional — taken from the server": "اختياري — يُؤخذ من الخادم",
    "Link": "الرابط",
    "URL": "الرابط",
    "Type": "النوع",
    "Quality": "الجودة",
    "File name": "اسم الملف",
    "Save to": "الحفظ في",
    "Download now": "تحميل الآن",
    "Download later": "تحميل لاحقاً",
    "Add to the schedule (starts at {t})": "إضافة للجدولة (يبدأ الساعة {t})",
    "Paste a link to a file, a video page, or a magnet link.": "الصق رابط ملف، أو صفحة فيديو، أو رابط ماجنت.",
    "size unknown": "الحجم غير معروف",
    "Unknown size": "حجم غير معروف",
    "{s} free on {d}": "{s} متاح على {d}",
    "The server didn't say how big it is": "الخادم لم يحدد حجم الملف",
    "Pause & resume: yes": "الإيقاف والاستئناف: مدعوم",
    "Pause & resume: no — if paused it starts over": "الإيقاف والاستئناف: غير مدعوم — لو توقف يبدأ من جديد",
    "This link opens a web page, not a file. For a video on it, choose Type → Video.":
        "هذا الرابط يفتح صفحة ويب وليس ملفاً. لتحميل فيديو منها اختر النوع ← فيديو.",
    "size is an estimate": "الحجم تقديري",
    "The size appears once the torrent connects — you'll pick the files then":
        "يظهر الحجم بعد اتصال التورنت — وستختار الملفات وقتها",
    "Checking size…": "جاري معرفة الحجم…",
    "Couldn't check this link: {e}": "تعذر فحص هذا الرابط: {e}",
    "Length {t}": "المدة {t}",
    "{n} file": "ملف واحد",
    "{n} files": "{n} ملفات",
    "Saves to": "يُحفظ في",
    "Not enough space on {d} — it needs {a}, only {b} is free. Choose another folder below.":
        "لا توجد مساحة كافية على {d} — يحتاج {a} والمتاح {b} فقط. اختر مجلداً آخر بالأسفل.",
    "Choose download folder": "اختر مجلد التحميل",
    "HD video needs a small add-on (~30 MB). Without it videos come as a single file (usually up to 720p).":
        "الفيديو بجودة عالية يحتاج إضافة صغيرة (~30 ميجا). بدونها يُحمّل الفيديو كملف واحد (غالباً حتى 720p).",
    "Download add-on": "تحميل الإضافة",
    "Starting…": "جاري البدء…",
    "Couldn't download the add-on. Check your internet and try again.": "تعذر تحميل الإضافة. تأكد من الإنترنت وحاول مرة أخرى.",
    "HD video support is ready ✓": "دعم الفيديو عالي الجودة جاهز ✓",
    # torrent files dialog
    "Choose files": "اختيار الملفات",
    "Filter files…": "تصفية الملفات…",
    "Select none": "إلغاء التحديد",
    "Videos only": "الفيديو فقط",
    "Files": "الملفات",
    "Remove torrent": "إزالة التورنت",
    "Download selected": "تحميل المحدد",
    "Apply": "تطبيق",
    # speed dialog
    "Limit speed  (Ctrl+L turns this on and off)": "تحديد السرعة  (Ctrl+L للتشغيل والإيقاف)",
    "Downloads (all together)": "التحميلات (مجتمعة)",
    "Torrent download": "تحميل التورنت",
    "Torrent upload": "رفع التورنت",
    "Save": "حفظ",
    "Set limit": "تعيين الحد",
    "Set 0 for no limit.": "اكتب 0 لإلغاء الحد.",
    "Keep some internet for everyone else. A single download can also get its own limit from right-click → Limit speed.":
        "اترك جزءاً من الإنترنت للآخرين. يمكن تحديد سرعة تحميل واحد من الزر الأيمن ← تحديد السرعة.",
    # finish countdown
    "Going to sleep": "جاري الدخول في السكون",
    "Shutting down": "جاري إيقاف التشغيل",
    "Closing MZ-DManager": "جاري إغلاق MZ-DManager",
    "Close": "إغلاق",
    # cleaner
    "Clean the list": "تنظيف القائمة",
    "Leftover pieces of downloads that were cancelled or removed from the list. Downloads still in your list are never touched.":
        "بقايا تحميلات أُلغيت أو أُزيلت من القائمة. التحميلات الموجودة في قائمتك لا تُمس.",
    "Nothing to clean — no leftovers found. ✓": "لا يوجد ما يُنظف — لا توجد بقايا. ✓",
    # settings
    "General": "عام",
    "Downloads": "التحميلات",
    "Folders": "المجلدات",
    "Schedule": "الجدولة",
    "Updates": "التحديثات",
    "Language": "اللغة",
    "Start with Windows (runs next to the clock)": "التشغيل مع ويندوز (يعمل بجانب الساعة)",
    "Watch the clipboard — offer to download copied links": "مراقبة الحافظة — عرض تحميل الروابط المنسوخة",
    "Also for video pages (YouTube, Facebook, TikTok…)": "وأيضاً لصفحات الفيديو (يوتيوب، فيسبوك، تيك توك…)",
    "System follows Windows: light during the day if Windows is light, dark otherwise.":
        "النظام يتبع ويندوز: فاتح لو ويندوز فاتح، وغامق غير ذلك.",
    "Copy a link to a file (.exe, .zip, .mp4, .pdf…) or a magnet link anywhere, and MZ-DManager asks if you want to download it.":
        "انسخ رابط ملف (.exe, .zip, .mp4, .pdf…) أو رابط ماجنت من أي مكان، وسيسألك MZ-DManager إن كنت تريد تحميله.",
    "Sort downloads into Music, Videos, Programs, Documents, Torrents and Others":
        "ترتيب التحميلات في مجلدات: موسيقى، فيديو، برامج، مستندات، تورنت، أخرى",
    "Download folder": "مجلد التحميل",
    "Simultaneous downloads": "التحميلات في نفس الوقت",
    "Connections per file": "الاتصالات لكل ملف",
    "Default": "افتراضي",
    "Choose folder": "اختر مجلداً",
    "Choose where each kind of download is saved. Leave empty to use the default.":
        "اختر مكان حفظ كل نوع من التحميلات. اتركه فارغاً لاستخدام الافتراضي.",
    "These apply to the default download folder. If you pick another folder when adding a download, the file goes straight into that folder.":
        "هذه الإعدادات للمجلد الافتراضي. لو اخترت مجلداً آخر عند إضافة تحميل، يُحفظ الملف فيه مباشرة.",
    "Turn on the scheduler": "تشغيل الجدولة",
    "Start at": "البدء الساعة",
    "Stop at": "الإيقاف الساعة",
    "Days": "الأيام",
    "When they finish": "عند الانتهاء",
    "Download at night or whenever the internet is free. Downloads you add with “Add to the schedule” (or right-click → Add to schedule) start at the start time and pause at the stop time.":
        "حمّل بالليل أو وقت ما يكون الإنترنت فاضي. التحميلات المضافة بـ «إضافة للجدولة» (أو الزر الأيمن ← إضافة للجدولة) تبدأ وقت البدء وتتوقف وقت الإيقاف.",
    "For a one-time action — like shutting down after the downloads that are running now — use the “When done” button at the top of the window.":
        "لإجراء لمرة واحدة — مثل إيقاف التشغيل بعد التحميلات الجارية الآن — استخدم زر «بعد الانتهاء» في القائمة الجانبية.",
    "Let me choose which files to download": "اسألني عن الملفات التي أريد تحميلها",
    "Keep seeding torrents after they finish": "استمرار مشاركة التورنت بعد الانتهاء",
    "Open magnet links and .torrent files with MZ-DManager": "فتح روابط الماجنت وملفات التورنت بـ MZ-DManager",
    "Check for updates automatically": "البحث عن التحديثات تلقائياً",
    "Check now": "افحص الآن",
    "Installed version": "الإصدار المثبت",
    "When a new version is out, a bar appears at the top of MZ-DManager with an “Update now” button. Your downloads and settings are kept.":
        "عند صدور إصدار جديد يظهر شريط أعلى MZ-DManager فيه زر «تحديث الآن». تحميلاتك وإعداداتك تبقى كما هي.",
    "Restart MZ-DManager to switch the language.": "أعد تشغيل MZ-DManager لتغيير اللغة.",
    "Restart now": "إعادة التشغيل الآن",
    "System (follow Windows)": "النظام (يتبع ويندوز)",
    "STARTUP": "التشغيل", "CLIPBOARD": "الحافظة", "BROWSER": "المتصفح", "SPEED": "السرعة", "TIP": "ملاحظة",
    "TORRENT": "التورنت", "UPDATES": "التحديثات", "FOLDERS": "المجلدات", "SCHEDULE": "الجدولة",
    ".torrent file…": "ملف تورنت…",
    "About MZ-DManager {v}": "عن MZ-DManager {v}",
    "Mon": "اثنين", "Tue": "ثلاثاء", "Wed": "أربعاء", "Thu": "خميس", "Fri": "جمعة", "Sat": "سبت", "Sun": "أحد",
    "Yes": "نعم", "No": "لا", "OK": "موافق",
}

_WS = re.compile(r"^(\s*)(.*?)(\s*)$", re.S)


_LRI, _PDI = "\u2066", "\u2069"


class _RtlText(str):
    """Arabic template: numbers and sizes put into it stay left-to-right ("12.1 MB", not "MB 12.1")."""
    def format(self, *args, **kw):
        iso = lambda v: v if isinstance(v, str) and re.search("[\u0600-\u06FF]", v) else _LRI + str(v) + _PDI  # noqa
        return str.format(self, *[iso(a) for a in args], **{k: iso(v) for k, v in kw.items()})


def tr(text):
    """Translate a fixed text (or a template, before .format)."""
    if LANG != "ar" or not text:
        return text
    if text in AR:
        return _RtlText(AR[text])
    if "\t" in text:                       # "Add URL…\tCtrl+N"
        a, b = text.split("\t", 1)
        return tr(a) + "\t" + b
    m = _WS.match(text)
    if m and m.group(2) in AR:
        return m.group(1) + AR[m.group(2)] + m.group(3)
    return text


def plural(n, one, many):
    """English one/many forms; Arabic templates take {n} the same way."""
    return tr(one if n == 1 else many).format(n=n)


def ltr(text):
    """Keep a number or size left-to-right inside Arabic text."""
    return _LRI + text + _PDI if LANG == "ar" else text


def translate_tree(root):
    """Translate every fixed text under a widget (labels, buttons, menus, tabs, combo boxes…)."""
    if LANG != "ar" or root is None:
        return
    from PySide6.QtWidgets import (QWidget, QLabel, QAbstractButton, QLineEdit, QComboBox, QTabWidget,
                                   QGroupBox, QMenu)
    widgets = [root] + root.findChildren(QWidget)
    for w in widgets:
        try:
            if w.isWindow() and w.windowTitle():
                w.setWindowTitle(tr(w.windowTitle()))
            if w.toolTip():
                w.setToolTip(tr(w.toolTip()))
            if isinstance(w, QLabel) and w.text() and not w.text().startswith("<"):
                t = tr(w.text())
                if t != w.text():
                    w.setText(t)
            elif isinstance(w, QAbstractButton) and w.text():
                t = tr(w.text())
                if t != w.text():
                    w.setText(t)
            elif isinstance(w, QLineEdit) and w.placeholderText():
                w.setPlaceholderText(tr(w.placeholderText()))
            elif isinstance(w, QComboBox):
                for i in range(w.count()):
                    w.setItemText(i, tr(w.itemText(i)))
            elif isinstance(w, QTabWidget):
                for i in range(w.count()):
                    w.setTabText(i, tr(w.tabText(i)))
            elif isinstance(w, QGroupBox) and w.title():
                w.setTitle(tr(w.title()))
            if isinstance(w, QMenu):
                if w.title():
                    w.setTitle(tr(w.title()))
                for a in w.actions():
                    if a.text():
                        a.setText(tr(a.text()))
                    if a.menu():
                        a.menu().setTitle(tr(a.menu().title()))
        except RuntimeError:
            pass


def install(app):
    """Translate every window and menu as it opens (dialogs, menus, message boxes)."""
    if LANG != "ar":
        return
    from PySide6.QtCore import QObject, QEvent, Qt
    from PySide6.QtWidgets import QWidget
    app.setLayoutDirection(Qt.RightToLeft)

    class _Hook(QObject):
        def eventFilter(self, obj, ev):
            if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
                translate_tree(obj)
            return False

    app._i18n_hook = _Hook(app)
    app.installEventFilter(app._i18n_hook)
