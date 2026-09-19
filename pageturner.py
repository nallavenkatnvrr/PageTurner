r"""
PageTurner - a lightweight PDF & EPUB reader for Windows 11.
Built with PySide6 (Qt 6) and PyMuPDF.

Run:    python pageturner.py [optional\path\to\book.pdf]
Build:  build.bat  (creates dist\PageTurner\PageTurner.exe)
"""
import hashlib
import html
import io
import logging
import os
import posixpath
import re
import sys
import threading
import zipfile
from urllib.parse import unquote
from bisect import bisect_right
from collections import OrderedDict

import pymupdf as fitz  # PyMuPDF
from PySide6.QtCore import QEvent, QObject, QRectF, QSettings, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QIcon, QImage, QKeySequence,
                           QPainter, QPixmap)
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
    QDockWidget, QFileDialog, QPlainTextEdit, QTextBrowser,
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QProgressBar, QPushButton, QScrollArea, QSizePolicy,
    QSpinBox, QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

APP = "PageTurner"
APP_VERSION = "1.1.1"   # keep in step with installer\PageTurner.iss

# MuPDF prints harmless complaints about broken books (e.g. a stylesheet the
# publisher forgot to include) to the console. The app handles these itself.
try:
    fitz.TOOLS.mupdf_display_errors(False)
    fitz.TOOLS.mupdf_display_warnings(False)
except Exception:
    pass
for _lg in ("pyhanko", "pyhanko_certvalidator"):
    logging.getLogger(_lg).setLevel(logging.CRITICAL)
PT_TO_PX = 96 / 72          # "100%" = real printed size on a 96-dpi screen
EPUB_W, EPUB_H = 420, 620   # "Fixed book page" size (points) for EPUBs
PAD = 12                    # space around pages (px)
GAP = 16                    # space between pages in two-page view (px)
MAX_COLUMN_PX = 900         # keeps EPUB lines readable on very wide windows

# theme: (tint (ink, paper) or None, background around pages, paper colour, UI text colour)
THEMES = {
    "light": (None, "#e4e4e4", "#ffffff", "#555555"),
    "sepia": ((0x5B4636, 0xF4ECD8), "#d8cbaf", "#f4ecd8", "#5b4636"),
    "night": ((0xCFCBC4, 0x1E1E1E), "#121212", "#1e1e1e", "#9a9a9a"),
}
FONTS = {"Publisher's font": None, "Serif": "serif", "Sans-serif": "sans-serif"}
SPACING = ["Publisher's", "1.2", "1.4", "1.6", "1.8", "2.0"]
MARGINS = {"Narrow": 1, "Normal": 2.5, "Wide": 4.5, "Extra wide": 7}
FILE_FILTER = ("Books & documents (*.pdf *.epub *.mobi *.fb2 *.xps *.cbz);;"
               "PDF (*.pdf);;EPUB (*.epub);;All files (*.*)")
ZOOM_PRESETS = ["Fit width", "Fit page", "50%", "75%", "100%",
                "125%", "150%", "200%", "300%"]



def resource_path(*parts):
    """Finds bundled files both when run from source and from the PyInstaller exe."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


LOGO_PNG = resource_path("assets", "logo.png")
LOGO_ICO = resource_path("assets", "logo.ico")


def app_icon():
    for p in (LOGO_ICO, LOGO_PNG):
        if os.path.exists(p):
            return QIcon(p)
    return QIcon()


def _attrs(tag):
    return {k.split(":")[-1]: v for k, v in re.findall(r'([\w:.-]+)\s*=\s*["\']([^"\']*)["\']', tag)}


def patch_epub(path):
    """
    Fixes two common publisher EPUB problems and returns the repaired book's
    bytes (or None if nothing needed fixing). Original page numbers are kept.

    1. "Click here to view code image"-style links point to XHTML files that
       are left out of the reading order, so they can't be followed. Those
       files are appended to the reading order as non-linear extras.
    2. Pages reference stylesheets that aren't in the file (e.g. Pearson's
       override_v1.css). Empty placeholders are added so the book lays out
       cleanly instead of failing to load them on every chapter.
    """
    with zipfile.ZipFile(path) as z:
        container = z.read("META-INF/container.xml").decode("utf-8", "replace")
        m = re.search(r'full-path\s*=\s*["\']([^"\']+)["\']', container)
        if not m:
            return None
        opf_name = m.group(1)
        opf = z.read(opf_name).decode("utf-8", "replace")

        spine_ids = {_attrs(t).get("idref") for t in re.findall(r"<(?:\w+:)?itemref\b[^>]*>", opf)}
        extra = []
        for tag in re.findall(r"<(?:\w+:)?item\b[^>]*>", opf):
            a = _attrs(tag)
            if (a.get("media-type") in ("application/xhtml+xml", "text/html")
                    and a.get("id") and a["id"] not in spine_ids
                    and "nav" not in a.get("properties", "").split()):
                extra.append(a["id"])
        names = set(z.namelist())
        missing_css = set()
        opf_dir = posixpath.dirname(opf_name)
        for tag in re.findall(r"<(?:\w+:)?item\b[^>]*>", opf):
            a = _attrs(tag)
            if a.get("media-type") == "text/css" and a.get("href"):
                full = posixpath.normpath(posixpath.join(opf_dir, unquote(a["href"])))
                if full not in names:
                    missing_css.add(full)
        for name in names:
            if name.lower().endswith((".xhtml", ".html", ".htm")):
                text = z.read(name).decode("utf-8", "replace")
                for href in re.findall(r'<link\b[^>]*?href\s*=\s*["\']([^"\'#?]+\.css)', text, re.I):
                    if "://" in href:
                        continue
                    full = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(href)))
                    if full not in names:
                        missing_css.add(full)

        close = re.search(r"</(\w+:)?spine\s*>", opf)
        if extra and close:
            prefix = close.group(1) or ""
            refs = "".join(f'<{prefix}itemref idref="{i}" linear="no"/>' for i in extra)
            opf = opf[:close.start()] + refs + opf[close.start():]
        elif not missing_css:
            return None

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as w:
            names = z.namelist()
            if "mimetype" in names:
                w.writestr(zipfile.ZipInfo("mimetype"), z.read("mimetype"), zipfile.ZIP_STORED)
            for name in names:
                if name == "mimetype" or name.endswith("/"):
                    continue
                data = opf.encode("utf-8") if name == opf_name else z.read(name)
                w.writestr(name, data)
            for name in sorted(missing_css):
                if not name.startswith(".."):
                    w.writestr(name, "/* stylesheet missing from the original book */\n")
        return out.getvalue()



# ------------------------------------------------------------------ signatures
# Digital-signature checking (like Acrobat's signature panel), done with pyHanko.

def trusted_certs_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP, "trusted_certs")
    os.makedirs(path, exist_ok=True)
    return path


def _load_cert_file(path):
    from asn1crypto import pem, x509
    with open(path, "rb") as f:
        data = f.read()
    if pem.detect(data):
        return [x509.Certificate.load(der) for _, _, der in pem.unarmor(data, multiple=True)]
    return [x509.Certificate.load(data)]


def load_trust_store():
    """
    Trust anchors = the Windows trusted root store (what Windows itself trusts)
    + certificates the user chose to trust in PageTurner.
    Intermediate certificates from Windows help build chains.
    """
    from asn1crypto import x509
    roots, others = [], []
    if sys.platform == "win32":
        import ssl
        for store, bucket in (("ROOT", roots), ("CA", others)):
            try:
                for der, enc, _trust in ssl.enum_certificates(store):
                    if enc == "x509_asn":
                        try:
                            bucket.append(x509.Certificate.load(der))
                        except Exception:
                            pass
            except Exception:
                pass
    else:
        try:
            import certifi
            roots += _load_cert_file(certifi.where())
        except Exception:
            pass
    folder = trusted_certs_dir()
    for name in os.listdir(folder):
        try:
            roots += _load_cert_file(os.path.join(folder, name))
        except Exception:
            pass
    return roots, others


def _name(cert_name):
    try:
        n = cert_name.native
        return n.get("common_name") or n.get("organization_name") or cert_name.human_friendly
    except Exception:
        return str(cert_name)


def _fmt_time(dt):
    if dt is None:
        return ""
    try:
        return dt.astimezone().strftime("%d %b %Y, %I:%M:%S %p %Z").strip()
    except Exception:
        return str(dt)


def _pdf_date(value):
    """Parses a PDF date string like D:20260919083000+05'30'."""
    import datetime
    s = str(value or "")
    m = re.match(r"D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz+\-])?(\d{2})?'?(\d{2})?", s)
    if not m:
        return None
    y, mo, d, h, mi, se = (int(g) if g else dflt for g, dflt in zip(m.groups()[:6], (0, 1, 1, 1, 1, 0)))
    tz = datetime.timezone.utc
    if m.group(7) in ("+", "-") and m.group(8):
        off = datetime.timedelta(hours=int(m.group(8)), minutes=int(m.group(9) or 0))
        tz = datetime.timezone(off if m.group(7) == "+" else -off)
    try:
        return datetime.datetime(y, mo, d, h, mi, se, tzinfo=tz)
    except ValueError:
        return None


def validate_pdf_signatures(data, password=None):
    """
    Checks every digital signature in a PDF. Returns a list of dicts with a
    plain-language verdict for each one: 'valid', 'unknown' or 'invalid'.
    """
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    from pyhanko_certvalidator import ValidationContext

    reader = PdfFileReader(io.BytesIO(data), strict=False)
    if reader.encrypted:
        reader.decrypt(password or "")
    roots, others = load_trust_store()
    total_revs = reader.xrefs.total_revisions
    results = []
    for sig in reader.embedded_signatures:
        r = {"field": sig.field_name, "verdict": "unknown", "lines": [], "cert": None,
             "details": "", "signer": "Unknown signer"}
        so = sig.sig_object
        for key, label in (("/Reason", "Reason"), ("/Location", "Location"), ("/ContactInfo", "Contact")):
            val = so.get(key)
            val = getattr(val, "decrypted", val)  # text in encrypted PDFs
            if val:
                r[label.lower()] = str(val)
        try:
            r["signed_revision"] = sig.signed_revision + 1
        except Exception:
            r["signed_revision"] = None
        r["total_revisions"] = total_revs
        try:
            r["certification"] = sig.docmdp_level is not None
        except Exception:
            r["certification"] = False
        try:
            vc = ValidationContext(trust_roots=roots, other_certs=others, allow_fetching=True,
                                   revocation_mode="soft-fail")
            st = validate_pdf_signature(sig, vc)
        except Exception as ex:
            r["verdict"] = "unknown"
            r["lines"].append(("unknown", f"The signature could not be checked: {ex}"))
            results.append(r)
            continue

        cert = st.signing_cert
        r["cert"] = cert
        r["signer"] = _name(cert.subject) if cert is not None else (str(so.get("/Name") or "Unknown signer"))
        try:
            r["details"] = st.pretty_print_details()
        except Exception:
            r["details"] = ""

        crypto_ok = bool(st.intact and st.valid)
        mod = getattr(getattr(st, "modification_level", None), "name", "")
        cov = getattr(getattr(st, "coverage", None), "name", "")
        docmdp_ok = getattr(st, "docmdp_ok", True) is not False
        revoked = bool(getattr(st, "revoked", False))
        trusted = bool(st.trusted)

        # Integrity
        if not st.intact:
            r["lines"].append(("invalid", "The document has been altered or corrupted since it was signed."))
        elif not st.valid:
            r["lines"].append(("invalid", "The signature is corrupted or uses invalid cryptography."))
        elif cov == "ENTIRE_FILE":
            r["lines"].append(("valid", "The document has not been modified since this signature was applied."))
        elif mod in ("NONE", "LTA_UPDATES"):
            r["lines"].append(("valid", "The document has not been modified since this signature was applied "
                                        "(only validation data was added later)."))
        elif mod == "FORM_FILLING":
            r["lines"].append(("valid", "The document was changed after signing: form fields were filled in "
                                        "or other signatures added. These changes are permitted."))
        elif mod == "ANNOTATIONS":
            r["lines"].append(("valid", "The document was changed after signing: comments or annotations "
                                        "were added. These changes are permitted."))
        else:
            r["lines"].append(("invalid", "The document was changed after signing in ways that are not "
                                          "permitted, so this signature no longer covers what you see."))
        integrity_ok = crypto_ok and docmdp_ok and (cov == "ENTIRE_FILE" or mod in (
            "NONE", "LTA_UPDATES", "FORM_FILLING", "ANNOTATIONS"))

        # Identity
        if revoked:
            r["lines"].append(("invalid", "The signer's certificate has been revoked."))
        elif trusted:
            r["lines"].append(("valid", "The signer's identity is valid: the certificate is trusted."))
        else:
            r["lines"].append(("unknown", "The signer's identity is unknown: the certificate is not in your "
                                          "trusted certificates (Windows trusted roots or ones you trusted "
                                          "in PageTurner)."))

        # Time
        ts = getattr(st, "timestamp_validity", None)
        if ts is not None and getattr(ts, "timestamp", None):
            ok = ts.intact and ts.valid and ts.trusted
            r["lines"].append(("valid" if ok else "unknown",
                               f"Signing time comes from a {'trusted ' if ok else ''}timestamp: "
                               f"{_fmt_time(ts.timestamp)}."))
        else:
            when = st.signer_reported_dt or _pdf_date(getattr(so.get("/M"), "decrypted", so.get("/M")))
            if when:
                r["lines"].append(("info", f"Signing time is from the signer's computer clock: {_fmt_time(when)}."))

        if integrity_ok and trusted and not revoked:
            r["verdict"] = "valid"
        elif not integrity_ok or revoked:
            r["verdict"] = "invalid"
        else:
            r["verdict"] = "unknown"
        results.append(r)
    return results


def cert_summary(cert):
    import hashlib
    v = cert["tbs_certificate"]["validity"]
    rows = [
        ("Issued to", cert.subject.human_friendly),
        ("Issued by", cert.issuer.human_friendly),
        ("Valid from", _fmt_time(v["not_before"].native)),
        ("Valid until", _fmt_time(v["not_after"].native)),
        ("Serial number", format(cert.serial_number, "X")),
        ("SHA-256 fingerprint", hashlib.sha256(cert.dump()).hexdigest().upper()),
    ]
    try:
        ku = cert.key_usage_value
        if ku:
            rows.append(("Key usage", ", ".join(sorted(ku.native))))
    except Exception:
        pass
    return rows


def trust_certificate(cert):
    import hashlib
    path = os.path.join(trusted_certs_dir(), hashlib.sha256(cert.dump()).hexdigest()[:24] + ".cer")
    with open(path, "wb") as f:
        f.write(cert.dump())
    return path


class _SigBridge(QObject):
    done = Signal(object, object, int)   # results, error message, token


def start_signature_check(bridge, data, password, token):
    """Runs the (possibly slow, online) signature check off the UI thread."""
    def work():
        try:
            bridge.done.emit(validate_pdf_signatures(data, password), None, token)
        except Exception as ex:
            bridge.done.emit(None, str(ex) or ex.__class__.__name__, token)
    threading.Thread(target=work, daemon=True).start()


VERDICT_STYLE = {   # symbol, text colour, bar colour, bar border
    "valid": ("✔", "#1e7b34", "#e6f4ea", "#b7dfc2"),
    "unknown": ("⚠", "#9a6700", "#fff4d6", "#f0d68a"),
    "invalid": ("✖", "#b3261e", "#fde7e7", "#f2b8b5"),
    "checking": ("⏳", "#1f4e8c", "#e8f0fb", "#b8cbe8"),
}


SHORTCUTS_HELP = """
<b>Open</b>: Ctrl+O &nbsp; (or drag a file onto the window)<br>
<b>Next / previous page</b>: Right / Left, N / P<br>
<b>Scroll down / up (turns page at the end)</b>: Space / Shift+Space, PgDn / PgUp, mouse wheel<br>
<b>First / last page</b>: Home / End<br>
<b>Go to page</b>: Ctrl+G<br>
<b>Back (after clicking a link)</b>: Alt+Left, Backspace, or mouse back button<br>
<b>Search</b>: Ctrl+F, then Enter / F3 for next, Shift+F3 for previous<br>
<b>Zoom in / out</b>: Ctrl + / Ctrl -, or Ctrl + mouse wheel (changes text size in EPUBs)<br>
<b>Fit width / fit page</b>: Ctrl+0 / Ctrl+9<br>
<b>EPUB text size</b>: Ctrl+] / Ctrl+[<br>
<b>Two-page view</b>: Ctrl+2<br>
<b>Reading settings (theme, font, spacing, margins)</b>: Ctrl+,<br>
<b>Night mode</b>: Ctrl+D<br>
<b>Signature panel</b>: Ctrl+Shift+S<br>
<b>Contents panel</b>: Ctrl+T<br>
<b>Full screen</b>: F11 (Esc to leave)
"""


class PageView(QScrollArea):
    """Scrollable page area. Scrolling past the top/bottom turns the page."""

    def __init__(self, reader):
        super().__init__()
        self.reader = reader
        self.label = QLabel(alignment=Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.setWidget(self.label)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        self._overscroll = 0
        self._press_pos = None
        self.label.setMouseTracking(True)
        self.label.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self.label and self.reader.doc is not None:
            t = e.type()
            if t == QEvent.MouseMove:
                link = self.reader.link_at(e.position())
                if link:
                    self.label.setCursor(Qt.PointingHandCursor)
                    self.label.setToolTip(self.reader.describe_link(link))
                else:
                    self.label.unsetCursor()
                    self.label.setToolTip("")
            elif t == QEvent.MouseButtonPress:
                if e.button() == Qt.BackButton:
                    self.reader.go_back()
                    return True
                if e.button() == Qt.LeftButton:
                    self._press_pos = e.position()
            elif t == QEvent.MouseButtonRelease and e.button() == Qt.LeftButton and self._press_pos:
                moved = (e.position() - self._press_pos).manhattanLength()
                self._press_pos = None
                if moved < 6:
                    link = self.reader.link_at(e.position())
                    if link:
                        self.reader.follow_link(link)
                        return True
        return super().eventFilter(obj, e)

    def wheelEvent(self, e):
        dy = e.angleDelta().y()
        if e.modifiers() & Qt.ControlModifier:
            if dy:
                self.reader.zoom_step(1 if dy > 0 else -1)
            return
        vs = self.verticalScrollBar()
        at_bottom = vs.value() >= vs.maximum()
        at_top = vs.value() <= vs.minimum()
        if (dy < 0 and at_bottom) or (dy > 0 and at_top):
            # A page that fits the window turns with one notch; a tall page
            # needs a little extra push so you don't fly past the end.
            need = 120 if vs.maximum() == 0 else 240
            self._overscroll += abs(dy)
            if self._overscroll >= need:
                self._overscroll = 0
                if dy < 0:
                    self.reader.next_page()
                else:
                    self.reader.prev_page(to_bottom=True)
            return
        self._overscroll = 0
        super().wheelEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.reader.on_resize()


class Reader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = s = QSettings(APP, APP)
        self.doc = None
        self.path = None
        self.page_no = 0
        self.zoom_mode = "width"
        self.zoom = 1.0
        self._zoom_used = PT_TO_PX

        self.theme = s.value("theme", "light")
        if self.theme not in THEMES:
            self.theme = "light"
        self._day_theme = self.theme if self.theme != "night" else "light"
        self.spread = s.value("spread", False, type=bool)
        self.epub_fill = s.value("epub_fill", True, type=bool)
        self.epub_family = s.value("epub_family", "Publisher's font")
        self.epub_spacing = s.value("epub_spacing", "Publisher's")
        self.epub_margin = s.value("epub_margin", "Normal")
        self.epub_justify = s.value("epub_justify", False, type=bool)
        self.font_size = int(s.value("epub_font", 12))
        self._layout_sig = None
        self.cache = OrderedDict()   # rendered page images, most recent last

        self.search_query = ""
        self.hit_page = None
        self.hit_rects = []
        self.hit_idx = 0
        self.links = []      # [(page_no, rect_in_page_coords, link_dict)] currently shown
        self.slots = {}      # page_no -> (x, y) of that page inside the rendered image
        self.history = []    # pages to return to after following a link
        self._toc_pages, self._toc_titles = [], []
        self._password = None
        self.sig_results = None      # list of signature checks for the open PDF
        self.sig_fields = {}         # field name -> (page, rect)
        self.sig_widget_xref = {}    # field name -> PDF object number of its widget
        self._sig_ap_backup = {}     # original appearance streams we replaced on screen
        self._sig_token = 0
        self._sig_bridge = _SigBridge()
        self._sig_bridge.done.connect(self._signatures_checked)

        self.setWindowTitle(APP)
        self.setWindowIcon(app_icon())
        self.resize(1150, 880)
        self.setAcceptDrops(True)

        self.view = PageView(self)
        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(0)
        self._build_sig_bar()
        cl.addWidget(self.sig_bar)
        cl.addWidget(self.view)
        self.setCentralWidget(central)
        self.view.label.linkActivated.connect(self._welcome_link)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(60)
        self._render_timer.timeout.connect(self.render)
        self._relayout_timer = QTimer(self)
        self._relayout_timer.setSingleShot(True)
        self._relayout_timer.setInterval(250)
        self._relayout_timer.timeout.connect(self._relayout_and_render)

        self._build_toc()
        self._build_settings_dock()
        self._build_sig_dock()
        self._build_actions()
        self._build_toolbar()
        self._build_menus()
        self._build_statusbar()

        geo = s.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        state = s.value("window_state")
        if state is not None:
            self.restoreState(state)

        self._apply_theme()
        self._update_ui()
        self._show_welcome()

    # ------------------------------------------------------------------ UI
    def _act(self, text, slot, shortcut=None, icon_text=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            seqs = shortcut if isinstance(shortcut, (list, tuple)) else [shortcut]
            a.setShortcuts([QKeySequence(x) for x in seqs])
            a.setToolTip(f"{text} ({seqs[0]})")
        if icon_text:
            a.setIconText(icon_text)
        a.setCheckable(checkable)
        a.triggered.connect(lambda checked=False: slot())
        self.addAction(a)  # keeps shortcuts alive in full screen
        return a

    def _build_actions(self):
        self.a_open = self._act("Open…", self.open_dialog, "Ctrl+O", "Open")
        self.a_quit = self._act("Exit", self.close, "Ctrl+Q")
        self.a_prev = self._act("Previous page", self.prev_page, ["Left", "P"], "◀")
        self.a_next = self._act("Next page", self.next_page, ["Right", "N"], "▶")
        self.a_pgdn = self._act("Scroll down", self.page_down, ["Space", "PgDown"])
        self.a_pgup = self._act("Scroll up", self.page_up, ["Shift+Space", "PgUp"])
        self.a_first = self._act("First page", lambda: self.goto(0), "Home")
        self.a_last = self._act("Last page",
                                lambda: self.goto(self.doc.page_count - 1) if self.doc is not None else None, "End")
        self.a_goto = self._act("Go to page…", self.goto_dialog, "Ctrl+G")
        self.a_back = self._act("Back", self.go_back, ["Alt+Left", "Backspace"], "↩ Back")
        self.a_zin = self._act("Zoom in", lambda: self.zoom_step(1), ["Ctrl++", "Ctrl+="], "+")
        self.a_zout = self._act("Zoom out", lambda: self.zoom_step(-1), "Ctrl+-", "−")
        self.a_fitw = self._act("Fit width", lambda: self.set_zoom_text("Fit width"), "Ctrl+0")
        self.a_fitp = self._act("Fit page", lambda: self.set_zoom_text("Fit page"), "Ctrl+9")
        self.a_fbig = self._act("Larger text (EPUB)", lambda: self.font_spin.stepUp(), "Ctrl+]")
        self.a_fsmall = self._act("Smaller text (EPUB)", lambda: self.font_spin.stepDown(), "Ctrl+[")
        self.a_spread = self._act("Two-page view", lambda: self.set_spread(self.a_spread.isChecked()),
                                  "Ctrl+2", "Two pages", checkable=True)
        self.a_spread.setChecked(self.spread)
        self.a_night = self._act("Night mode", self.toggle_night, "Ctrl+D", "☾", checkable=True)
        self.a_night.setChecked(self.theme == "night")
        self.a_full = self._act("Full screen", self.toggle_fullscreen, "F11")
        self.a_esc = self._act("Leave full screen",
                               lambda: self.toggle_fullscreen() if self.isFullScreen() else None, "Esc")
        self.a_find = self._act("Find…", self.focus_search, "Ctrl+F")
        self.a_fnext = self._act("Find next", lambda: self.find(False), "F3", "↓")
        self.a_fprev = self._act("Find previous", lambda: self.find(True), "Shift+F3", "↑")
        self.a_help = self._act("Keyboard shortcuts", self.show_shortcuts, "F1")
        self.a_toc = self.toc_dock.toggleViewAction()
        self.a_toc.setText("Contents panel")
        self.a_toc.setIconText("☰")
        self.a_toc.setShortcut(QKeySequence("Ctrl+T"))
        self.a_settings = self.settings_dock.toggleViewAction()
        self.a_settings.setText("Reading settings")
        self.a_settings.setIconText("Aa")
        self.a_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.a_settings.setToolTip("Theme, layout, font, spacing and margins (Ctrl+,)")
        self.a_sigpanel = self.sig_dock.toggleViewAction()
        self.a_sigpanel.setText("Signature panel")
        self.a_sigpanel.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self.a_recheck = self._act("Check signatures again", self.check_signatures)
        self.a_import_cert = self._act("Import trusted certificate…", self.import_trusted_cert)
        self.a_cert_folder = self._act("Open trusted certificates folder", lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(trusted_certs_dir())))

    def _build_toolbar(self):
        tb = QToolBar("Main toolbar", self)
        tb.setObjectName("main_toolbar")
        tb.setMovable(False)
        self.addToolBar(tb)
        self.toolbar = tb

        tb.addAction(self.a_open)
        tb.addAction(self.a_toc)
        tb.addSeparator()
        tb.addAction(self.a_back)
        tb.addAction(self.a_prev)
        self.page_spin = QSpinBox()
        self.page_spin.setKeyboardTracking(False)
        self.page_spin.setMinimum(1)
        self.page_spin.setMinimumWidth(70)
        self.page_spin.valueChanged.connect(self._page_spin_changed)
        tb.addWidget(self.page_spin)
        self.count_label = QLabel(" / 0 ")
        tb.addWidget(self.count_label)
        tb.addAction(self.a_next)
        tb.addSeparator()

        tb.addAction(self.a_zout)
        self.zoom_box = QComboBox()
        self.zoom_box.setEditable(True)
        self.zoom_box.setInsertPolicy(QComboBox.NoInsert)
        self.zoom_box.addItems(ZOOM_PRESETS)
        self.zoom_box.setMinimumWidth(105)
        self.zoom_box.activated.connect(lambda i: self.set_zoom_text(self.zoom_box.itemText(i)))
        self.zoom_box.lineEdit().returnPressed.connect(
            lambda: self.set_zoom_text(self.zoom_box.currentText()))
        tb.addWidget(self.zoom_box)
        tb.addAction(self.a_zin)
        tb.addSeparator()
        tb.addAction(self.a_spread)
        tb.addAction(self.a_night)
        tb.addAction(self.a_settings)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search (Ctrl+F)")
        self.search_box.setClearButtonEnabled(True)
        self.search_box.setFixedWidth(220)
        self.search_box.returnPressed.connect(lambda: self.find(False))
        tb.addWidget(self.search_box)
        tb.addAction(self.a_fprev)
        tb.addAction(self.a_fnext)

    def _build_menus(self):
        m = self.menuBar().addMenu("&File")
        m.addAction(self.a_open)
        self.recent_menu = m.addMenu("Open recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        m.addSeparator()
        m.addAction(self.a_quit)

        m = self.menuBar().addMenu("&View")
        for a in (self.a_toc, self.a_settings, self.a_spread, self.a_night, self.a_full):
            m.addAction(a)
        tm = m.addMenu("Theme")
        for key in THEMES:
            tm.addAction(key.capitalize(), lambda k=key: self.set_theme(k))
        m.addSeparator()
        for a in (self.a_zin, self.a_zout, self.a_fitw, self.a_fitp):
            m.addAction(a)
        m.addSeparator()
        m.addAction(self.a_fbig)
        m.addAction(self.a_fsmall)

        m = self.menuBar().addMenu("&Go")
        for a in (self.a_back, self.a_next, self.a_prev, self.a_first, self.a_last, self.a_goto):
            m.addAction(a)
        m.addSeparator()
        for a in (self.a_find, self.a_fnext, self.a_fprev):
            m.addAction(a)

        m = self.menuBar().addMenu("&Signatures")
        m.addAction(self.a_sigpanel)
        m.addAction(self.a_recheck)
        m.addSeparator()
        m.addAction(self.a_import_cert)
        m.addAction(self.a_cert_folder)

        m = self.menuBar().addMenu("&Help")
        m.addAction(self.a_help)
        m.addAction(QAction("About PageTurner", self, triggered=self.show_about))

    def _build_statusbar(self):
        self.chapter_label = QLabel()
        self.chapter_label.setMinimumWidth(50)
        self.statusBar().addWidget(self.chapter_label, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedSize(140, 6)
        self.statusBar().addPermanentWidget(self.progress)
        self.status = QLabel()
        self.statusBar().addPermanentWidget(self.status)

    def _build_toc(self):
        self.toc = QTreeWidget()
        self.toc.setHeaderHidden(True)
        self.toc.itemClicked.connect(self._toc_clicked)
        self.toc.itemActivated.connect(self._toc_clicked)
        self.toc_dock = QDockWidget("Contents", self)
        self.toc_dock.setObjectName("toc_dock")
        self.toc_dock.setWidget(self.toc)
        self.toc_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.toc_dock)
        self.resizeDocks([self.toc_dock], [260], Qt.Horizontal)

    def _build_settings_dock(self):
        w = QWidget()
        v = QVBoxLayout(w)

        v.addWidget(QLabel("Theme"))
        row = QHBoxLayout()
        self.theme_group = QButtonGroup(self)
        self.theme_buttons = {}
        for key in THEMES:
            _, _, paper, ink = THEMES[key]
            b = QPushButton(key.capitalize())
            b.setCheckable(True)
            b.setMinimumHeight(38)
            b.setStyleSheet(
                f"QPushButton {{ background:{paper}; color:{ink}; border:1px solid #8a8a8a;"
                f" border-radius:6px; }} QPushButton:checked {{ border:3px solid #2f6fd0; }}")
            b.setChecked(key == self.theme)
            b.clicked.connect(lambda checked=False, k=key: self.set_theme(k))
            self.theme_group.addButton(b)
            self.theme_buttons[key] = b
            row.addWidget(b)
        v.addLayout(row)

        form = QFormLayout()
        self.spread_combo = QComboBox()
        self.spread_combo.addItems(["One page", "Two pages side by side"])
        self.spread_combo.setCurrentIndex(int(self.spread))
        self.spread_combo.currentIndexChanged.connect(lambda i: self.set_spread(bool(i)))
        form.addRow("Layout", self.spread_combo)
        v.addLayout(form)

        self.epub_box = QGroupBox("EPUB, MOBI and FB2 books")
        f2 = QFormLayout(self.epub_box)
        self.fill_combo = QComboBox()
        self.fill_combo.addItems(["Fill the window", "Fixed book page"])
        self.fill_combo.setCurrentIndex(0 if self.epub_fill else 1)
        self.font_combo = QComboBox()
        self.font_combo.addItems(list(FONTS))
        self.font_combo.setCurrentText(self.epub_family)
        self.font_spin = QSpinBox()
        self.font_spin.setRange(6, 40)
        self.font_spin.setSuffix(" pt")
        self.font_spin.setValue(self.font_size)
        self.font_spin.setKeyboardTracking(False)
        self.spacing_combo = QComboBox()
        self.spacing_combo.addItems(SPACING)
        self.spacing_combo.setCurrentText(self.epub_spacing)
        self.margin_combo = QComboBox()
        self.margin_combo.addItems(list(MARGINS))
        self.margin_combo.setCurrentText(self.epub_margin)
        self.justify_check = QCheckBox("Justify paragraphs")
        self.justify_check.setChecked(self.epub_justify)
        f2.addRow("Page", self.fill_combo)
        f2.addRow("Font", self.font_combo)
        f2.addRow("Text size", self.font_spin)
        f2.addRow("Line spacing", self.spacing_combo)
        f2.addRow("Margins", self.margin_combo)
        f2.addRow(self.justify_check)
        for c in (self.fill_combo, self.font_combo, self.spacing_combo, self.margin_combo):
            c.currentIndexChanged.connect(lambda _=0: self._epub_settings_changed())
        self.font_spin.valueChanged.connect(lambda _=0: self._epub_settings_changed())
        self.justify_check.toggled.connect(lambda _=False: self._epub_settings_changed())
        v.addWidget(self.epub_box)

        note = QLabel("PDFs keep their printed layout. These book settings re-flow "
                      "the text and keep your place.")
        note.setWordWrap(True)
        note.setStyleSheet("color:#777; font-size:9pt;")
        v.addWidget(note)
        v.addStretch()

        self.settings_dock = QDockWidget("Reading settings", self)
        self.settings_dock.setObjectName("settings_dock")
        self.settings_dock.setWidget(w)
        self.settings_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.settings_dock)
        self.settings_dock.hide()

    def _is_book_fill(self):
        return bool(self.doc is not None and self.doc.is_reflowable and self.epub_fill)

    def _surround(self):
        _, around, paper, _ = THEMES[self.theme]
        return paper if self._is_book_fill() else around

    def _apply_theme(self):
        # Books that fill the window never need scrollbars (and hiding them
        # stops the text from re-flowing back and forth while resizing).
        policy = Qt.ScrollBarAlwaysOff if self._is_book_fill() else Qt.ScrollBarAsNeeded
        self.view.setVerticalScrollBarPolicy(policy)
        self.view.setHorizontalScrollBarPolicy(policy)
        ink = THEMES[self.theme][3]
        self.view.label.setStyleSheet(f"background:{self._surround()}; color:{ink};")

    def _show_welcome(self):
        self.view.label.clear()
        logo = ""
        if os.path.exists(LOGO_PNG):
            logo = (f"<img src='{QUrl.fromLocalFile(LOGO_PNG).toString()}' width='128' height='128'>"
                    "<br><br>")
        recent = ""
        items = self._recent()[:6]
        if items:
            link_col = "#8ab4f8" if self.theme == "night" else "#1a5fb4"
            rows = "".join(
                f"<div style='margin:4px'><a style='color:{link_col}; text-decoration:none' "
                f"href='recent:{i}'>{html.escape(os.path.basename(p))}</a></div>"
                for i, p in enumerate(items))
            recent = f"<div style='font-size:11pt; margin-top:22px'><b>Recent files</b>{rows}</div>"
        self.view.label.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
        self.view.label.setText(
            f"<div align='center'>{logo}</div>"
            "<div style='font-size:15pt'>Open a PDF or EPUB to start reading</div>"
            "<div style='font-size:10pt; margin-top:8px'>Ctrl+O, or drag a file onto this window</div>"
            f"{recent}")

    def _welcome_link(self, href):
        if href.startswith("recent:"):
            items = self._recent()[:6]
            i = int(href.split(":", 1)[1])
            if i < len(items):
                self.open_file(items[i])

    def _update_ui(self):
        has = self.doc is not None
        self.a_back.setEnabled(has and bool(self.history))
        for a in (self.a_prev, self.a_next, self.a_first, self.a_last, self.a_goto,
                  self.a_fnext, self.a_fprev, self.a_pgdn, self.a_pgup):
            a.setEnabled(has)
        zoomable = has and not self._is_book_fill()
        for a in (self.a_fitw, self.a_fitp):
            a.setEnabled(zoomable)
        self.a_zin.setEnabled(has)
        self.a_zout.setEnabled(has)
        self.zoom_box.setEnabled(zoomable)
        self.zoom_box.setToolTip("" if zoomable or not has else
                                 "This book fills the window - use Ctrl + / Ctrl - to change text size")
        reflow = has and self.doc.is_reflowable
        self.epub_box.setEnabled(reflow or not has)
        self.a_fbig.setEnabled(reflow)
        self.a_fsmall.setEnabled(reflow)
        self.page_spin.setEnabled(has)
        self.progress.setVisible(has)
        self.search_box.setEnabled(has)

    # ------------------------------------------------------------- opening
    def open_dialog(self):
        start = os.path.dirname(self.path) if self.path else self.settings.value(
            "last_dir", os.path.expanduser("~\\Documents"))
        path, _ = QFileDialog.getOpenFileName(self, "Open book or document", start, FILE_FILTER)
        if path:
            self.open_file(path)

    def open_file(self, path):
        path = os.path.abspath(path)
        try:
            data = None
            if path.lower().endswith(".epub"):
                try:
                    data = patch_epub(path)
                except Exception:
                    data = None  # unusual EPUB layout - open it as-is
            doc = fitz.open(stream=data, filetype="epub") if data else fitz.open(path)
        except Exception as ex:
            QMessageBox.warning(self, APP, f"Couldn't open this file.\n\n{path}\n\n{ex}")
            return
        password = None
        if doc.needs_pass:
            prompt = f"\u201c{os.path.basename(path)}\u201d is password protected.\nEnter the password to open it:"
            while True:
                pw, ok = QInputDialog.getText(self, "Password required", prompt, QLineEdit.Password)
                if not ok:
                    doc.close()
                    return
                if doc.authenticate(pw):
                    password = pw
                    break
                prompt = "That password is incorrect. Please try again:"

        self._save_position()
        old, old_path, old_sig = self.doc, self.path, self._layout_sig
        self.doc, self.path = doc, path
        self._layout_sig = None
        self.cache.clear()
        self.page_no = 0
        if doc.is_reflowable:
            self._relayout()
        if doc.page_count == 0:
            QMessageBox.warning(self, APP, "This file has no pages to show.")
            self.doc, self.path, self._layout_sig = old, old_path, old_sig
            doc.close()
            return
        if old is not None:
            old.close()
        self.hit_page, self.hit_rects, self.search_query = None, [], ""
        self.history = []
        self._password = password
        self._reset_signatures()

        kind = self._kind()
        self.zoom_mode = self.settings.value(f"zoom_mode_{kind}", "page" if kind == "epub" else "width")
        self.zoom = float(self.settings.value(f"zoom_{kind}", 1.0))
        self._sync_zoom_box()
        self._refresh_page_count()
        self._populate_toc()
        self._apply_theme()
        self._update_ui()

        title = (doc.metadata or {}).get("title") or os.path.basename(path)
        self.setWindowTitle(f"{title} - {APP}")
        self._add_recent(path)
        self.settings.setValue("last_file", path)
        self.settings.setValue("last_dir", os.path.dirname(path))
        self.goto(self._restore_position())
        self.check_signatures()

    def _kind(self):
        return "epub" if self.doc is not None and self.doc.is_reflowable else "pdf"

    def _key(self):
        return hashlib.md5(os.path.normcase(self.path).encode("utf-8")).hexdigest()

    def _save_position(self):
        if not (self.doc is not None and self.path):
            return
        key = self._key()
        self.settings.setValue(f"pos/{key}", self.page_no)
        if self.doc.is_reflowable:
            # Page numbers change with window size and text size, so books also
            # remember "chapter + how far into it".
            try:
                ch, pg = self.doc.location_from_page_number(self.page_no)
                frac = pg / max(1, self.doc.chapter_page_count(ch))
                self.settings.setValue(f"loc/{key}", f"{ch}:{frac:.5f}")
            except Exception:
                pass

    def _restore_position(self):
        key = self._key()
        if self.doc.is_reflowable:
            loc = self.settings.value(f"loc/{key}")
            if loc:
                try:
                    ch, frac = str(loc).split(":")
                    ch = int(ch)
                    pg = int(float(frac) * self.doc.chapter_page_count(ch) + 0.5)
                    pg = min(pg, self.doc.chapter_page_count(ch) - 1)
                    return self.doc.page_number_from_location((ch, max(0, pg)))
                except Exception:
                    pass
        return int(self.settings.value(f"pos/{key}", 0))

    def _recent(self):
        r = self.settings.value("recent", [])
        if isinstance(r, str):
            r = [r]
        return [p for p in (r or []) if os.path.exists(p)]

    def _add_recent(self, path):
        r = [path] + [p for p in self._recent() if os.path.normcase(p) != os.path.normcase(path)]
        self.settings.setValue("recent", r[:12])

    def _fill_recent_menu(self):
        self.recent_menu.clear()
        items = self._recent()
        if not items:
            a = self.recent_menu.addAction("No recent files")
            a.setEnabled(False)
            return
        for p in items:
            a = self.recent_menu.addAction(os.path.basename(p))
            a.setToolTip(p)
            a.triggered.connect(lambda checked=False, p=p: self.open_file(p))

    def _refresh_page_count(self):
        self.page_spin.blockSignals(True)
        self.page_spin.setMaximum(self.doc.page_count)
        self.page_spin.blockSignals(False)
        self.count_label.setText(f" / {self.doc.page_count} ")

    def _populate_toc(self):
        self.toc.clear()
        root = self.toc.invisibleRootItem()
        stack = [(0, root)]
        try:
            toc = self.doc.get_toc(simple=True)
        except Exception:
            toc = []
        flat = []
        for entry in toc:
            level, title, page = entry[0], entry[1], entry[2]
            while stack[-1][0] >= level:
                stack.pop()
            text = (title or "").strip() or "(untitled)"
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.UserRole, page - 1)
            item.setToolTip(0, text)
            stack[-1][1].addChild(item)
            stack.append((level, item))
            if page >= 1:
                flat.append((page - 1, text))
        flat.sort(key=lambda t: t[0])
        self._toc_pages = [p for p, _ in flat]
        self._toc_titles = [t for _, t in flat]
        if not toc:
            item = QTreeWidgetItem(["No table of contents"])
            item.setFlags(Qt.NoItemFlags)
            root.addChild(item)

    def _toc_clicked(self, item, _col=0):
        page = item.data(0, Qt.UserRole)
        if page is not None and page >= 0:
            self.goto(page)

    def _chapter_title(self):
        i = bisect_right(self._toc_pages, self.page_no) - 1
        return self._toc_titles[i] if i >= 0 else ""

    # --------------------------------------------------------- book layout
    def _epub_css(self):
        m = MARGINS.get(self.epub_margin, 2.5)
        css = [f"@page {{ margin: 2em {m}em; }}"]
        fam = FONTS.get(self.epub_family)
        if fam:
            css.append("body, p, li, blockquote, dd, dt, td, th, h1, h2, h3, h4, h5, h6 "
                       f"{{ font-family: {fam} !important; }}")
            css.append("pre, code, kbd, samp, tt { font-family: monospace !important; }")
        if self.epub_spacing in SPACING[1:]:
            css.append(f"p, li, blockquote, dd {{ line-height: {self.epub_spacing} !important; }}")
        if self.epub_justify:
            css.append("p { text-align: justify !important; }")
        return "\n".join(css)

    def _epub_page_size(self):
        if not self.epub_fill:
            return EPUB_W, EPUB_H
        vp = self.view.viewport()
        vw, vh = max(240, vp.width()), max(240, vp.height() - 4)
        cols = 2 if self.spread else 1
        colw = min((vw - GAP * (cols - 1)) / cols, MAX_COLUMN_PX)
        return int(colw / PT_TO_PX), int(vh / PT_TO_PX)

    def _relayout(self):
        """Re-flows a book for the current settings/window. Keeps the reading spot."""
        d = self.doc
        if not d or not d.is_reflowable:
            return False
        w, h = self._epub_page_size()
        css = self._epub_css()
        sig = (w, h, css, self.font_size)
        if sig == self._layout_sig:
            return False
        bm = None
        if self._layout_sig is not None:
            try:
                bm = d.make_bookmark(d.location_from_page_number(self.page_no))
            except Exception:
                bm = None
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            d.apply_css(css)
            d.layout(width=w, height=h, fontsize=self.font_size)
            if bm is not None:
                try:
                    self.page_no = d.page_number_from_location(d.find_bookmark(bm))
                except Exception:
                    pass
            self.page_no = max(0, min(self.page_no, d.page_count - 1))
        finally:
            QApplication.restoreOverrideCursor()
        self._layout_sig = sig
        self.cache.clear()
        self.hit_page, self.hit_rects = None, []
        self._refresh_page_count()
        if bm is not None:
            self._populate_toc()
        return True

    def _relayout_and_render(self):
        if self._relayout():
            self._save_position()
        self.render()

    def _epub_settings_changed(self):
        self.epub_fill = self.fill_combo.currentIndex() == 0
        self.epub_family = self.font_combo.currentText()
        self.font_size = self.font_spin.value()
        self.epub_spacing = self.spacing_combo.currentText()
        self.epub_margin = self.margin_combo.currentText()
        self.epub_justify = self.justify_check.isChecked()
        for k, v in (("epub_fill", self.epub_fill), ("epub_family", self.epub_family),
                     ("epub_font", self.font_size), ("epub_spacing", self.epub_spacing),
                     ("epub_margin", self.epub_margin), ("epub_justify", self.epub_justify)):
            self.settings.setValue(k, v)
        if self.doc is not None and self.doc.is_reflowable:
            self._apply_theme()
            self._update_ui()
            self._relayout_and_render()

    def on_resize(self):
        if self.doc is None:
            return
        if self._is_book_fill():
            self._relayout_timer.start()
        elif self.zoom_mode in ("width", "page"):
            self._render_timer.start()

    # ---------------------------------------------------------- navigation
    def _visible_pages(self, start=None):
        n = self.page_no if start is None else start
        if self.spread and n + 1 < self.doc.page_count:
            return [n, n + 1]
        return [n]

    def goto(self, n, to_bottom=False, y=None):
        """Show page n. y (page coordinates) scrolls to a spot on that page."""
        if self.doc is None:
            return
        n = max(0, min(int(n), self.doc.page_count - 1))
        self.page_no = n
        self.render()
        vs = self.view.verticalScrollBar()

        def scroll():
            if y is not None:
                oy = self._page_origin()[1] + self.slots.get(n, (0, 0))[1]
                vs.setValue(int(oy + y * self._zoom_used) - 20)
            else:
                vs.setValue(vs.maximum() if to_bottom else vs.minimum())
        QTimer.singleShot(0, scroll)
        self._save_position()

    def next_page(self):
        if self.doc is None:
            return
        step = len(self._visible_pages())
        if self.page_no + step < self.doc.page_count:
            self.goto(self.page_no + step)

    def prev_page(self, to_bottom=False):
        if self.doc is not None and self.page_no > 0:
            self.goto(self.page_no - (2 if self.spread else 1), to_bottom=to_bottom)

    def page_down(self):
        vs = self.view.verticalScrollBar()
        if vs.value() >= vs.maximum():
            self.next_page()
        else:
            vs.setValue(vs.value() + max(40, vs.pageStep() - 40))

    def page_up(self):
        vs = self.view.verticalScrollBar()
        if vs.value() <= vs.minimum():
            self.prev_page(to_bottom=True)
        else:
            vs.setValue(vs.value() - max(40, vs.pageStep() - 40))

    def goto_dialog(self):
        if self.doc is None:
            return
        n, ok = QInputDialog.getInt(self, "Go to page", f"Page (1–{self.doc.page_count}):",
                                    self.page_no + 1, 1, self.doc.page_count)
        if ok:
            self.goto(n - 1)

    def _page_spin_changed(self, v):
        if self.doc is not None and v - 1 != self.page_no:
            self.goto(v - 1)

    def go_back(self):
        if not self.history:
            return
        page, scroll = self.history.pop()
        self.goto(page)
        vs = self.view.verticalScrollBar()
        QTimer.singleShot(0, lambda: vs.setValue(scroll))
        self.a_back.setEnabled(bool(self.history))

    # ---------------------------------------------------------------- links
    def _page_origin(self):
        """Top-left of the rendered image inside the label, in screen pixels."""
        pm = self.view.label.pixmap()
        if pm is None or pm.isNull():
            return 0.0, 0.0
        pw, ph = pm.width() / pm.devicePixelRatio(), pm.height() / pm.devicePixelRatio()
        return (max(0.0, (self.view.label.width() - pw) / 2),
                max(0.0, (self.view.label.height() - ph) / 2))

    def link_at(self, pos):
        if self.doc is None or not self.links:
            return None
        ox, oy = self._page_origin()
        z = self._zoom_used
        for pno, rect, link in self.links:
            sx, sy = self.slots.get(pno, (0, 0))
            pt = fitz.Point((pos.x() - ox - sx) / z, (pos.y() - oy - sy) / z)
            if pt in rect:
                return link
        return None

    def _link_target(self, link):
        """Returns (page_index, y) for internal links, or None."""
        page = link.get("page", -1)
        to = link.get("to")
        if page is None or page < 0:
            uri = link.get("uri") or link.get("nameddest") or link.get("name")
            if not uri or link.get("kind") == fitz.LINK_URI and "://" in uri:
                return None
            try:
                loc, x, y = self.doc.resolve_link(uri if uri.startswith("#") else "#" + uri)
                page = self.doc.page_number_from_location(loc) if isinstance(loc, tuple) else loc
                to = fitz.Point(x, y) if y == y else None  # y != y means NaN
            except Exception:
                return None
            if page is None or page < 0:
                return None
        y = None
        if to is not None and to.y == to.y and to.y > 0:
            y = to.y
        return page, y

    def describe_link(self, link):
        if link.get("kind") == "sig":
            return "Digital signature - click to see who signed and whether it's valid"
        if link.get("kind") == fitz.LINK_URI and link.get("uri"):
            return link["uri"]
        if link.get("kind") == fitz.LINK_GOTOR:
            return f"Opens another file: {link.get('file', '')}"
        target = self._link_target(link)
        if target:
            return f"Go to page {target[0] + 1}"
        return "Link target isn't available in this file"

    def follow_link(self, link):
        kind = link.get("kind")
        if kind == "sig":
            self.show_signature(link.get("field"))
            return
        uri = link.get("uri") or ""
        if (kind == fitz.LINK_URI and "://" in uri) or uri.lower().startswith("mailto:"):
            if uri.lower().startswith(("http://", "https://", "mailto:")):
                QDesktopServices.openUrl(QUrl(uri))
            elif QMessageBox.question(self, APP, f"This link points to:\n\n{uri}\n\nOpen it?") \
                    == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(uri))
            return
        if kind == fitz.LINK_GOTOR:
            f = link.get("file", "")
            if self.path and f and not os.path.isabs(f):
                f = os.path.join(os.path.dirname(self.path), f)
            if f and os.path.isfile(f):
                self.open_file(f)
            else:
                self.statusBar().showMessage("The linked file wasn't found.", 5000)
            return
        if kind == fitz.LINK_LAUNCH:
            self.statusBar().showMessage("This link tries to launch a program - ignored for safety.", 5000)
            return
        target = self._link_target(link)
        if not target:
            self.statusBar().showMessage("This link's target isn't included in the file.", 5000)
            return
        self.history.append((self.page_no, self.view.verticalScrollBar().value()))
        self.history = self.history[-50:]
        self.a_back.setEnabled(True)
        self.goto(target[0], y=target[1])
        self.statusBar().showMessage("Press Alt+Left or Backspace to go back.", 5000)

    # ------------------------------------------------------------ rendering
    def schedule_render(self):
        if self.doc is not None:
            self._render_timer.start()

    def _effective_zoom(self, pages):
        if self._is_book_fill():
            return PT_TO_PX
        vp = self.view.viewport()
        vsb = self.view.verticalScrollBar()
        vw = max(100, vp.width() - 2 * PAD - (0 if vsb.isVisible() else vsb.sizeHint().width()))
        vh = max(100, vp.height() - 2 * PAD)
        gaps = GAP * (len(pages) - 1)
        total_w = sum(p.rect.width for p in pages)
        max_h = max(p.rect.height for p in pages)
        if self.zoom_mode == "width":
            return (vw - gaps) / total_w
        if self.zoom_mode == "page":
            return min((vw - gaps) / total_w, vh / max_h)
        return self.zoom * PT_TO_PX

    def _page_image(self, pno, scale):
        key = (pno, round(scale, 4), self.theme, self._layout_sig)
        img = self.cache.get(key)
        if img is not None:
            self.cache.move_to_end(key)
            return img
        pix = self.doc.load_page(pno).get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        tint = THEMES[self.theme][0]
        if tint:
            pix.tint_with(*tint)
        img = QImage(pix.samples, pix.width, pix.height, pix.stride,
                     QImage.Format_RGB888).convertToFormat(QImage.Format_RGB32)
        self.cache[key] = img
        while len(self.cache) > 16:
            self.cache.popitem(last=False)
        return img

    def render(self):
        if self.doc is None:
            return
        pnos = self._visible_pages()
        pages = [self.doc.load_page(p) for p in pnos]
        z = max(0.05, self._effective_zoom(pages))
        self._zoom_used = z
        dpr = self.devicePixelRatioF()
        s = z * dpr
        imgs = [self._page_image(p, s) for p in pnos]
        gap = int(GAP * dpr) if len(imgs) > 1 else 0
        width = sum(i.width() for i in imgs) + gap * (len(imgs) - 1)
        height = max(i.height() for i in imgs)

        comp = QImage(width, height, QImage.Format_RGB32)
        comp.fill(QColor(self._surround()))
        painter = QPainter(comp)
        self.slots, self.links = {}, []
        x = 0
        framed = not self._is_book_fill()
        for pno, page, img in zip(pnos, pages, imgs):
            y = (height - img.height()) // 2
            painter.drawImage(x, y, img)
            if framed:
                painter.setPen(QColor(0, 0, 0, 45))
                painter.drawRect(x, y, img.width() - 1, img.height() - 1)
            self.slots[pno] = (x / dpr, y / dpr)
            rot = page.rotation_matrix
            try:
                self.links += [(pno, fitz.Rect(l["from"]) * rot, l) for l in page.get_links()]
                for name, (spno, srect) in self.sig_fields.items():
                    if spno == pno and not srect.is_empty:
                        self.links.append((pno, srect, {"kind": "sig", "field": name}))
            except Exception:
                pass
            if self.hit_page == pno and self.hit_rects:
                for i, r in enumerate(self.hit_rects):
                    col = QColor(255, 140, 0, 140) if i == self.hit_idx else QColor(255, 215, 0, 90)
                    painter.fillRect(QRectF(x + r.x0 * s, y + r.y0 * s, r.width * s, r.height * s), col)
            x += img.width() + gap
        painter.end()

        qpix = QPixmap.fromImage(comp)
        qpix.setDevicePixelRatio(dpr)
        self.view.label.setPixmap(qpix)
        self._update_status(pnos, z)
        QTimer.singleShot(40, self._prefetch)

    def _update_status(self, pnos, z):
        count = self.doc.page_count
        self.page_spin.blockSignals(True)
        self.page_spin.setValue(self.page_no + 1)
        self.page_spin.blockSignals(False)
        self.a_prev.setEnabled(self.page_no > 0)
        self.a_next.setEnabled(pnos[-1] < count - 1)
        shown = f"Pages {pnos[0] + 1}–{pnos[-1] + 1}" if len(pnos) > 1 else f"Page {pnos[0] + 1}"
        pct_read = round((pnos[-1] + 1) / count * 100)
        extra = "" if self._is_book_fill() else f"   |   {round(z / PT_TO_PX * 100)}%"
        self.status.setText(f"{shown} of {count}   |   {pct_read}% read{extra}  ")
        self.progress.setValue(int((pnos[-1] + 1) / count * 1000))
        chapter = self._chapter_title()
        self.chapter_label.setText(f"  {chapter}" if chapter else "")
        self.chapter_label.setToolTip(chapter)

    def _prefetch(self):
        """Renders the next page(s) in the background so turning feels instant."""
        if self.doc is None or self.doc.is_closed:
            return
        try:
            nxt = self.page_no + len(self._visible_pages())
            if nxt < self.doc.page_count:
                pnos = self._visible_pages(nxt)
                pages = [self.doc.load_page(p) for p in pnos]
                s = max(0.05, self._effective_zoom(pages)) * self.devicePixelRatioF()
                for p in pnos:
                    self._page_image(p, s)
        except Exception:
            pass

    # --------------------------------------------------------------- themes
    def set_theme(self, key):
        if key not in THEMES:
            return
        self.theme = key
        if key != "night":
            self._day_theme = key
        self.settings.setValue("theme", key)
        self.theme_buttons[key].setChecked(True)
        self.a_night.setChecked(key == "night")
        self._apply_theme()
        if self.doc is not None:
            self.render()
        else:
            self._show_welcome()

    def toggle_night(self):
        self.set_theme(self._day_theme if self.theme == "night" else "night")

    def set_spread(self, on):
        self.spread = bool(on)
        self.settings.setValue("spread", self.spread)
        self.a_spread.setChecked(self.spread)
        self.spread_combo.blockSignals(True)
        self.spread_combo.setCurrentIndex(int(self.spread))
        self.spread_combo.blockSignals(False)
        if self.doc is not None:
            self._relayout()
            self.goto(self.page_no)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.toolbar.show()
            self.menuBar().show()
            self.statusBar().show()
        else:
            self.toolbar.hide()
            self.menuBar().hide()
            self.statusBar().hide()
            self.showFullScreen()

    # ----------------------------------------------------------------- zoom
    def set_zoom_text(self, text):
        if self._is_book_fill():
            return
        t = text.strip().lower()
        if t == "fit width":
            self.zoom_mode = "width"
        elif t == "fit page":
            self.zoom_mode = "page"
        else:
            try:
                self.zoom = max(0.1, min(8.0, float(t.rstrip("%").strip()) / 100))
                self.zoom_mode = "custom"
            except ValueError:
                pass
        self._after_zoom_change()

    def zoom_step(self, direction):
        if self.doc is None:
            return
        if self._is_book_fill():  # books that fill the window zoom by text size
            self.font_spin.setValue(self.font_spin.value() + (1 if direction > 0 else -1))
            return
        current = self._zoom_used / PT_TO_PX
        self.zoom = max(0.1, min(8.0, current * (1.2 if direction > 0 else 1 / 1.2)))
        self.zoom_mode = "custom"
        self._after_zoom_change()

    def _after_zoom_change(self):
        self._sync_zoom_box()
        if self.doc is not None:
            kind = self._kind()
            self.settings.setValue(f"zoom_mode_{kind}", self.zoom_mode)
            self.settings.setValue(f"zoom_{kind}", self.zoom)
            self.render()

    def _sync_zoom_box(self):
        self.zoom_box.blockSignals(True)
        if self.zoom_mode == "width":
            self.zoom_box.setCurrentIndex(0)
        elif self.zoom_mode == "page":
            self.zoom_box.setCurrentIndex(1)
        else:
            self.zoom_box.setEditText(f"{round(self.zoom * 100)}%")
        self.zoom_box.blockSignals(False)

    # --------------------------------------------------------------- search
    def focus_search(self):
        if self.isFullScreen():
            self.toggle_fullscreen()
        self.search_box.setFocus()
        self.search_box.selectAll()

    def find(self, backwards=False):
        q = self.search_box.text().strip()
        if not q or self.doc is None:
            return
        if q != self.search_query:
            self.search_query, self.hit_page, self.hit_rects = q, None, []

        step = -1 if backwards else 1
        visible = self._visible_pages()
        if self.hit_page in visible and self.hit_rects:
            ni = self.hit_idx + step
            if 0 <= ni < len(self.hit_rects):
                self.hit_idx = ni
                self.render()
                self._scroll_to_hit()
                return
            start = self.hit_page + step
        else:
            start = self.page_no

        n = self.doc.page_count
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            for i in range(n):
                p = (start + step * i) % n
                page = self.doc.load_page(p)
                rects = page.search_for(q)
                if rects:
                    rot = page.rotation_matrix
                    self.hit_page = p
                    self.hit_rects = [r * rot for r in rects]
                    self.hit_idx = len(rects) - 1 if backwards else 0
                    QApplication.restoreOverrideCursor()
                    if p in visible:
                        self.render()
                    else:
                        self.goto(p)
                    QTimer.singleShot(0, self._scroll_to_hit)
                    self.statusBar().showMessage(
                        f'"{q}" found on page {p + 1} ({len(rects)} on this page)', 4000)
                    return
                if i % 25 == 0:
                    QApplication.processEvents()
        finally:
            if QApplication.overrideCursor():
                QApplication.restoreOverrideCursor()
        self.hit_page, self.hit_rects = None, []
        self.render()
        self.statusBar().showMessage(f'No matches for "{q}"', 4000)

    def _scroll_to_hit(self):
        if self.hit_page not in self.slots or not self.hit_rects:
            return
        r = self.hit_rects[self.hit_idx]
        z = self._zoom_used
        ox, oy = self._page_origin()
        sx, sy = self.slots[self.hit_page]
        cx, cy = ox + sx + (r.x0 + r.x1) / 2 * z, oy + sy + (r.y0 + r.y1) / 2 * z
        self.view.ensureVisible(int(cx), int(cy), 120, self.view.viewport().height() // 3)

    # --------------------------------------------------------- misc events
    # ----------------------------------------------------------- signatures
    def _build_sig_bar(self):
        self.sig_bar = QFrame()
        lay = QHBoxLayout(self.sig_bar)
        lay.setContentsMargins(12, 6, 8, 6)
        self.sig_bar_label = QLabel()
        self.sig_bar_label.setWordWrap(True)
        lay.addWidget(self.sig_bar_label, 1)
        btn = QPushButton("Signature panel")
        btn.clicked.connect(lambda: self.show_signature(None))
        lay.addWidget(btn)
        self.sig_bar.hide()

    def _set_sig_bar(self, verdict, text):
        sym, ink, bg, border = VERDICT_STYLE[verdict]
        self.sig_bar.setStyleSheet(
            f"QFrame {{ background:{bg}; border-bottom:1px solid {border}; }}"
            f" QLabel {{ color:#202020; border:none; background:transparent; }}")
        self.sig_bar_label.setText(f"<span style='color:{ink}; font-size:12pt'>{sym}</span>&nbsp; {text}")
        self.sig_bar.show()

    def _build_sig_dock(self):
        self.sig_view = QTextBrowser()
        self.sig_view.setOpenLinks(False)
        self.sig_view.anchorClicked.connect(self._sig_link)
        self.sig_dock = QDockWidget("Signatures", self)
        self.sig_dock.setObjectName("sig_dock")
        self.sig_dock.setWidget(self.sig_view)
        self.sig_dock.setFeatures(QDockWidget.DockWidgetClosable | QDockWidget.DockWidgetMovable)
        self.addDockWidget(Qt.RightDockWidgetArea, self.sig_dock)
        self.resizeDocks([self.sig_dock], [360], Qt.Horizontal)
        self.sig_dock.hide()
        self.sig_view.setHtml("<p style='color:#777'>Open a signed PDF to see its signatures here.</p>")

    def _reset_signatures(self):
        self._sig_token += 1
        self.sig_results = None
        self.sig_fields = {}
        self.sig_widget_xref = {}
        self._sig_ap_backup = {}
        self.sig_bar.hide()
        self.sig_view.setHtml("<p style='color:#777'>This document has no digital signatures.</p>")

    def check_signatures(self):
        """Looks for digital signatures in the open PDF and checks them in the background."""
        if self.doc is None or not self.path or self.doc.is_reflowable:
            return
        try:
            signed = self.doc.get_sigflags() > 0
        except Exception:
            signed = False
        if not signed:
            return
        self.sig_fields = {}
        try:
            for page in self.doc:
                rot = page.rotation_matrix
                for w in page.widgets(types=[fitz.PDF_WIDGET_TYPE_SIGNATURE]):
                    self.sig_fields[w.field_name] = (page.number, fitz.Rect(w.rect) * rot)
                    self.sig_widget_xref[w.field_name] = w.xref
        except Exception:
            pass
        try:
            with open(self.path, "rb") as f:
                data = f.read()
        except OSError as ex:
            self._set_sig_bar("unknown", f"This PDF is signed, but it couldn't be read for checking: {ex}")
            return
        self._sig_token += 1
        self.sig_results = None
        self._set_sig_bar("checking", "Checking signatures… (this can take a few seconds when "
                                      "certificates are checked online)")
        self.sig_view.setHtml("<p>Checking signatures…</p>")
        start_signature_check(self._sig_bridge, data, self._password, self._sig_token)
        self.render()

    def _signatures_checked(self, results, error, token):
        if token != self._sig_token or self.doc is None:
            return  # a different file is open now
        if error is not None:
            self.sig_results = []
            self._set_sig_bar("unknown", f"This PDF is signed, but its signatures couldn't be checked: "
                                         f"{html.escape(error)}")
            self.sig_view.setHtml(f"<p>The signatures couldn't be checked:</p><p>{html.escape(error)}</p>")
            return
        self.sig_results = results
        verdicts = {r["verdict"] for r in results}
        if not results:
            self.sig_bar.hide()
        elif "invalid" in verdicts:
            self._set_sig_bar("invalid", "<b>At least one signature is invalid.</b>")
        elif "unknown" in verdicts:
            self._set_sig_bar("unknown", "<b>At least one signature has problems.</b> "
                                         "The signer's identity could not be verified.")
        else:
            n = len(results)
            self._set_sig_bar("valid", "<b>Signed and all signatures are valid.</b>" if n > 1 else
                                       "<b>Signed and the signature is valid.</b>")
        self._fill_sig_panel()
        try:
            if self._show_sig_status_on_page():
                self.render()
        except Exception:
            pass  # purely cosmetic - never let it break the reader

    # Many signing tools (UIDAI e-Aadhaar, DSC tools, e-Sign services) still draw
    # signatures the old Acrobat 6 way: a "?" mark and "Signature Not Verified"
    # printed inside the signature box, which the viewer is expected to replace
    # with the real result. Acrobat does this; so does PageTurner (on screen only -
    # the file itself is never changed).
    def _ref(self, xref, key):
        try:
            kind, val = self.doc.xref_get_key(xref, key)
        except Exception:
            return None
        m = re.match(r"(\d+) 0 R", val or "") if kind == "xref" else None
        return int(m.group(1)) if m else None

    def _xobject_children(self, xref):
        try:
            kind, val = self.doc.xref_get_key(xref, "Resources/XObject")
        except Exception:
            return []
        if kind == "xref":
            sub = self._ref(xref, "Resources/XObject")
            val = self.doc.xref_object(sub, compressed=True) if sub else ""
        elif kind != "dict":
            return []
        return [(n, int(x)) for n, x in re.findall(r"/([A-Za-z0-9_.#-]+)\s+(\d+)\s+0\s+R", val)]

    def _legacy_sig_layers(self, widget_xref):
        start = self._ref(widget_xref, "AP/N")
        found, seen, stack = {}, set(), [(start, 0)] if start else []
        while stack:
            x, depth = stack.pop()
            if x in seen or depth > 4:
                continue
            seen.add(x)
            for name, child in self._xobject_children(x):
                if name in ("n1", "n2", "n3", "n4") and name not in found:
                    found[name] = child
                stack.append((child, depth + 1))
        return found

    def _bbox(self, xref):
        try:
            nums = [float(v) for v in re.findall(r"-?[\d.]+", self.doc.xref_get_key(xref, "BBox")[1])]
            if len(nums) == 4:
                return nums
        except Exception:
            pass
        return [0, 0, 100, 100]

    @staticmethod
    def _status_mark(bbox, valid):
        x0, y0, x1, y1 = bbox
        w, h = x1 - x0, y1 - y0
        sz = min(w, h)
        cx, cy = x0 + w / 2, y0 + h / 2
        lw = max(1.0, sz * 0.12)
        if valid:   # green tick
            path = (f"{cx - .36 * sz:.2f} {cy + .02 * sz:.2f} m {cx - .1 * sz:.2f} {cy - .28 * sz:.2f} l "
                    f"{cx + .38 * sz:.2f} {cy + .32 * sz:.2f} l S")
            col = "0.13 0.55 0.21 RG"
        else:       # red cross
            d = .3 * sz
            path = (f"{cx - d:.2f} {cy - d:.2f} m {cx + d:.2f} {cy + d:.2f} l S "
                    f"{cx - d:.2f} {cy + d:.2f} m {cx + d:.2f} {cy - d:.2f} l S")
            col = "0.8 0.1 0.1 RG"
        return f"q {col} {lw:.2f} w 1 J 1 j {path} Q".encode()

    def _show_sig_status_on_page(self):
        """Replaces the '?' / 'Signature Not Verified' placeholders with the real result."""
        if self.doc is None:
            return False
        changed = bool(self._sig_ap_backup)
        for x, data in self._sig_ap_backup.items():   # undo any earlier result first
            self.doc.update_stream(x, data)
        self._sig_ap_backup = {}
        for r in self.sig_results or []:
            wx = self.sig_widget_xref.get(r["field"])
            if not wx or r["verdict"] == "unknown":
                continue   # "not verified" is the honest result - leave it as drawn
            valid = r["verdict"] == "valid"
            layers = self._legacy_sig_layers(wx)
            if not layers:
                continue
            if "n1" in layers:
                x = layers["n1"]
                self._sig_ap_backup[x] = self.doc.xref_stream(x)
                self.doc.update_stream(x, self._status_mark(self._bbox(x), valid))
            new_text = b"Signature valid" if valid else b"Signature invalid"
            for name in ("n2", "n4"):
                x = layers.get(name)
                if not x:
                    continue
                old = self.doc.xref_stream(x) or b""
                new = re.sub(rb"\(\s*Signature\s+Not\s+Verified\s*\)", b"(" + new_text + b")", old, flags=re.I)
                if new == old and name == "n4":
                    new = b""   # status text we can't rewrite in place: hide it rather than show a wrong one
                if new != old:
                    self._sig_ap_backup[x] = old
                    self.doc.update_stream(x, new)
            changed = True
        if changed:
            self.cache.clear()
        return changed

    def _fill_sig_panel(self):
        dark = self.theme == "night"
        parts = []
        heads = {"valid": "Signature is VALID.", "unknown": "Signature validity is UNKNOWN.",
                 "invalid": "Signature is INVALID."}
        for i, r in enumerate(self.sig_results or []):
            sym, ink, _, _ = VERDICT_STYLE[r["verdict"]]
            if dark:
                ink = {"valid": "#81c995", "unknown": "#fdd663", "invalid": "#f28b82"}[r["verdict"]]
            who = "Certified by" if r.get("certification") else "Signed by"
            rev = f"Rev. {r['signed_revision']}: " if r.get("signed_revision") else ""
            items = []
            for kind, text in r["lines"]:
                mark = {"valid": "✔ ", "unknown": "⚠ ", "invalid": "✖ "}.get(kind, "")
                items.append(f"<li>{mark}{html.escape(text)}</li>")
            meta = []
            for key, label in (("reason", "Reason"), ("location", "Location"), ("contact", "Contact")):
                if r.get(key):
                    meta.append(f"<tr><td style='color:#888; padding-right:8px'>{label}</td>"
                                f"<td>{html.escape(r[key])}</td></tr>")
            sr, tr = r.get("signed_revision"), r.get("total_revisions")
            if sr and tr and sr < tr:
                meta.append(f"<tr><td style='color:#888; padding-right:8px'>Covers</td>"
                            f"<td>revision {sr} of {tr} (the file was saved again after this signature)</td></tr>")
            where = self.sig_fields.get(r["field"])
            actions = []
            if where and not where[1].is_empty:
                actions.append(f"<a href='goto:{i}'>Show on page {where[0] + 1}</a>")
            elif where:
                actions.append("Invisible signature")
            if r.get("cert") is not None:
                actions.append(f"<a href='cert:{i}'>Certificate details</a>")
            parts.append(
                f"<a name='sig{i}'></a>"
                f"<p style='margin-bottom:2px'><span style='color:{ink}; font-size:12pt'><b>{sym} {rev}{who} "
                f"{html.escape(r['signer'])}</b></span></p>"
                f"<p style='margin:2px 0'><b>{heads[r['verdict']]}</b></p>"
                f"<ul style='margin-left:-24px'>{''.join(items)}</ul>"
                f"<table>{''.join(meta)}</table>"
                f"<p>{' &nbsp;|&nbsp; '.join(actions)}</p><hr>")
        self.sig_view.setHtml("".join(parts) or "<p>No signatures found.</p>")

    def show_signature(self, field):
        self.sig_dock.show()
        self.sig_dock.raise_()
        if field and self.sig_results:
            for i, r in enumerate(self.sig_results):
                if r["field"] == field:
                    self.sig_view.scrollToAnchor(f"sig{i}")
                    break

    def _sig_link(self, url):
        kind, _, idx = url.toString().partition(":")
        if not idx.isdigit() or not self.sig_results:
            return
        r = self.sig_results[int(idx)]
        if kind == "goto":
            where = self.sig_fields.get(r["field"])
            if where:
                self.goto(where[0], y=max(0.0, where[1].y0 - 40))
        elif kind == "cert":
            self.show_certificate(r)

    def show_certificate(self, r):
        cert = r["cert"]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Certificate - {r['signer']}")
        dlg.resize(620, 560)
        v = QVBoxLayout(dlg)
        form = QFormLayout()
        for label, value in cert_summary(cert):
            lab = QLabel(value)
            lab.setWordWrap(True)
            lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addRow(f"{label}:", lab)
        v.addLayout(form)
        v.addWidget(QLabel("Technical validation details:"))
        details = QPlainTextEdit(r.get("details") or "")
        details.setReadOnly(True)
        details.setStyleSheet("font-family: Consolas, monospace; font-size: 9pt;")
        v.addWidget(details, 1)
        box = QDialogButtonBox(QDialogButtonBox.Close)
        box.rejected.connect(dlg.reject)
        if r["verdict"] != "valid":
            trust = box.addButton("Trust this certificate", QDialogButtonBox.ActionRole)

            def do_trust():
                if QMessageBox.question(
                        dlg, "Trust this certificate?",
                        f"Only trust this certificate if you're sure it really belongs to "
                        f"\u201c{r['signer']}\u201d - for example, you received it from them directly.\n\n"
                        f"Signatures made with it will then be shown as valid.") == QMessageBox.Yes:
                    trust_certificate(cert)
                    dlg.accept()
                    self.check_signatures()
            trust.clicked.connect(do_trust)
        v.addWidget(box)
        dlg.exec()

    def import_trusted_cert(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import a certificate to trust", "",
                                              "Certificates (*.cer *.crt *.pem *.der);;All files (*.*)")
        if not path:
            return
        try:
            certs = _load_cert_file(path)
            for c in certs:
                trust_certificate(c)
        except Exception as ex:
            QMessageBox.warning(self, APP, f"That file couldn't be read as a certificate.\n\n{ex}")
            return
        QMessageBox.information(self, APP, f"Added {len(certs)} trusted certificate(s).")
        self.check_signatures()

    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle(f"About {APP}")
        box.setText(f"<b>{APP}</b> {APP_VERSION}<br>A simple PDF &amp; EPUB reader for Windows.<br><br>"
                    f"PyMuPDF {fitz.VersionBind}")
        if os.path.exists(LOGO_PNG):
            box.setIconPixmap(QPixmap(LOGO_PNG).scaled(96, 96, Qt.KeepAspectRatio,
                                                        Qt.SmoothTransformation))
        box.exec()

    def show_shortcuts(self):
        QMessageBox.information(self, "Keyboard shortcuts", SHORTCUTS_HELP)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            if u.isLocalFile():
                self.open_file(u.toLocalFile())
                break

    def closeEvent(self, e):
        self._save_position()
        if self.isFullScreen():
            self.showNormal()
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("window_state", self.saveState())
        self._render_timer.stop()
        self._relayout_timer.stop()
        if self.doc is not None:
            self.doc.close()
            self.doc = None
        super().closeEvent(e)


def main():
    if sys.platform == "win32":
        try:  # own taskbar icon group instead of python.exe's
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("PageTurner.Reader")
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setApplicationName(APP)
    app.setOrganizationName(APP)
    app.setWindowIcon(app_icon())
    w = Reader()
    w.show()

    args = [a for a in sys.argv[1:] if os.path.isfile(a)]
    if args:  # opened from "Open with PageTurner" / double-click on a file
        w.open_file(args[0])
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
