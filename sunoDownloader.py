import sys
import os
import re
import json
import time
import uuid
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import shutil
import base64
import hashlib
import subprocess
from bs4 import BeautifulSoup
from urllib.parse import urlparse

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    _CRYPTO_AVAILABLE = True
except Exception:
    _CRYPTO_AVAILABLE = False
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QCheckBox, QComboBox,
    QProgressBar, QMessageBox, QGroupBox, QLineEdit, QDialog,
    QListWidget, QListWidgetItem, QScrollArea, QFrame, QInputDialog,
    QScroller, QScrollerProperties,
)
from PySide6.QtCore import Qt, QThread, Signal, QPoint
from PySide6.QtGui import QMouseEvent

UUID_RE = re.compile(
    r"\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b")
WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# ==============================================================================
# MOBILE-FRIENDLY HIGH-CONTRAST DARK THEME
# ==============================================================================
DARK_STYLESHEET = """
QWidget {
    background-color: #12161F;
    color: #F0F6FC;
    font-family: 'Segoe UI', Roboto, Tahoma, sans-serif;
    font-size: 13px;
}
QScrollArea { border: none; background-color: #12161F; }
QGroupBox {
    background-color: #181D27;
    border: 1px solid #30363D;
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px 8px 8px 8px;
    font-weight: bold;
    color: #58A6FF;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px; padding: 0 6px;
    background-color: #181D27;
}
QLineEdit, QTextEdit, QListWidget, QComboBox {
    background-color: #0D1117;
    color: #FFFFFF;
    border: 1px solid #3D444D;
    border-radius: 6px;
    padding: 6px;
    selection-background-color: #1F6FEB;
    selection-color: #FFFFFF;
}
QLineEdit:focus, QTextEdit:focus, QListWidget:focus { border: 1px solid #58A6FF; }
QPushButton {
    background-color: #21262D;
    color: #F0F6FC;
    border: 1px solid #3D444D;
    border-radius: 6px;
    padding: 7px 10px;
    font-weight: 600;
    min-height: 22px;
}
QPushButton:hover { background-color: #30363D; border-color: #8B949E; }
QPushButton:pressed { background-color: #161B22; }
QPushButton:disabled {
    background-color: #161B22; color: #6E7681; border-color: #21262D;
}
QCheckBox { color: #F0F6FC; spacing: 6px; padding: 4px 2px; }
QCheckBox::indicator {
    width: 18px; height: 18px; border-radius: 4px;
    border: 1px solid #58A6FF; background-color: #0D1117;
}
QCheckBox::indicator:checked { background-color: #238636; border-color: #2EA043; }
QProgressBar {
    background-color: #0D1117; color: #FFFFFF;
    border: 1px solid #30363D; border-radius: 6px;
    text-align: center; font-weight: bold; min-height: 22px;
}
QProgressBar::chunk { background-color: #238636; border-radius: 5px; }
QLabel { color: #E6EDF3; background: transparent; }
"""


# ==============================================================================
# ANDROID & STORAGE HELPERS
# ==============================================================================
def get_script_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def is_android():
    return os.path.exists("/storage/emulated/0") or "ANDROID_ROOT" in os.environ


def get_android_root():
    for p in ["/storage/emulated/0", "/sdcard"]:
        if os.path.exists(p) and os.access(p, os.R_OK):
            return p
    return get_script_dir()


def get_default_save_dir():
    if is_android():
        root = get_android_root()
        dl = os.path.join(root, "Download", "Suno")
        try:
            os.makedirs(dl, exist_ok=True)
            return dl
        except Exception:
            return os.path.join(root, "Download")
    return get_script_dir()


def find_default_cookie_path():
    script_dir = get_script_dir()
    candidates = [
        os.path.join(script_dir, "cookie.txt"),
        os.path.join(script_dir, "cookies.txt"),
    ]
    if is_android():
        root = get_android_root()
        candidates.extend([
            os.path.join(root, "Download", "cookie.txt"),
            os.path.join(root, "Download", "cookies.txt"),
            os.path.join(root, "Download", "Suno", "cookie.txt"),
            os.path.join(root, "cookie.txt"),
            os.path.join(root, "Documents", "cookie.txt"),
            os.path.join(root, "Pydroid3", "cookie.txt"),
        ])
    for c in candidates:
        if os.path.isfile(c):
            return c
    if is_android():
        return os.path.join(get_android_root(), "Download", "cookie.txt")
    return os.path.join(script_dir, "cookie.txt")


def format_bytes_gb(num_bytes):
    return f"{num_bytes / (1024 ** 3):.2f} GB"


def human_size(num_bytes):
    n = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def get_storage_info(path):
    check_path = path
    while check_path and not os.path.exists(check_path):
        parent = os.path.dirname(check_path)
        if parent == check_path:
            break
        check_path = parent
    if not check_path or not os.path.exists(check_path):
        check_path = "/"
    try:
        total, used, free = shutil.disk_usage(check_path)
        pct = int((used / total) * 100) if total > 0 else 0
        return total, used, free, pct
    except Exception:
        return 0, 0, 0, 0


# ==============================================================================
# FFMPEG AUTO-DETECT
# ==============================================================================
_ffmpeg_cache = None
_ffmpeg_checked = False


def find_ffmpeg():
    """
    جستجوی ffmpeg به ترتیب:
      1) imageio-ffmpeg (پیشنهاد Pydroid: pip install imageio-ffmpeg)
      2) Termux
      3) system PATH
    """
    global _ffmpeg_cache, _ffmpeg_checked
    if _ffmpeg_checked:
        return _ffmpeg_cache
    _ffmpeg_checked = True

    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            if not os.access(exe, os.X_OK):
                try:
                    os.chmod(exe, 0o755)
                except Exception:
                    pass
            _ffmpeg_cache = exe
            return _ffmpeg_cache
    except Exception:
        pass

    for p in (
        "/data/data/com.termux/files/usr/bin/ffmpeg",
        "/system/bin/ffmpeg",
    ):
        if os.path.exists(p):
            _ffmpeg_cache = p
            return _ffmpeg_cache

    which = shutil.which("ffmpeg")
    if which:
        _ffmpeg_cache = which
        return _ffmpeg_cache

    return None


# ==============================================================================
# SUNO "MANGO" STREAM DECRYPTION (AES-GCM unwrap -> AES-CTR)
# ==============================================================================
MANGO_RIGHTS_ENDPOINTS = (
    "https://studio-api-prod.suno.com/api/mango/rights",
    "https://studio-api.prod.suno.com/api/mango/rights",
    "https://audiopipe.suno.ai/rights",
)
GCM_IV_LEN = 12
CTR_IV_LEN = 16


def _looks_like_audio(data):
    """Check magic bytes for common audio containers (MP4/M4A, MP3, WebM)."""
    if len(data) < 12:
        return False
    if data[4:8] == b"ftyp":
        return True
    if data[:3] == b"ID3":
        return True
    if data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return True
    if data[:4] == b"\x1aE\xdf\xa3":
        return True
    return False


def _gcm_unwrap(user_key, wrapped, aad):
    """Unwrap a mango key/iv blob: AES-GCM with nonce=wrapped[:12]."""
    if len(wrapped) <= GCM_IV_LEN:
        raise ValueError(f"wrapped blob too short: {len(wrapped)}B")
    return AESGCM(user_key).decrypt(wrapped[:GCM_IV_LEN], wrapped[GCM_IV_LEN:], aad)


def _decrypt_aes_ctr(ctr_key, ctr_iv, data):
    if len(ctr_iv) != CTR_IV_LEN:
        raise ValueError(
            f"CTR IV length {len(ctr_iv)}B (expected {CTR_IV_LEN}B)")
    if len(ctr_key) not in (16, 32):
        raise ValueError(
            f"CTR key length {len(ctr_key)}B (expected 16 or 32B)")
    decryptor = Cipher(algorithms.AES(ctr_key), modes.CTR(ctr_iv)).decryptor()
    return decryptor.update(data) + decryptor.finalize()


def _mango_browser_token():
    """Anonymous browser-token: {"token": STANDARD_base64_nopad(now_ms)}."""
    payload = json.dumps(
        {"timestamp": int(time.time() * 1000)}, separators=(",", ":"))
    b64 = base64.b64encode(payload.encode()).decode().rstrip("=")
    return json.dumps({"token": b64}, separators=(",", ":"))


def fetch_stream_rights(session, content_id, extra_headers=None):
    """
    Fetch mango rights for a clip and unwrap (ctr_key, ctr_iv).
    Tries nested payload shape first, then flat, across all endpoints.
    """
    if not _CRYPTO_AVAILABLE:
        raise RuntimeError(
            "cryptography package not available (pip install cryptography)")

    base_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://suno.com",
        "Referer": "https://suno.com/",
        "browser-token": _mango_browser_token(),
        "device-id": str(uuid.uuid4()),
    }
    if extra_headers:
        base_headers.update(extra_headers)

    payload_variants = [
        {"content_params": {"content_id": content_id, "content_type": "clip"}},
        {"content_id": content_id, "content_type": "clip"},
    ]

    last_err = None
    for endpoint in MANGO_RIGHTS_ENDPOINTS:
        for payload in payload_variants:
            try:
                r = session.post(endpoint, json=payload,
                                 headers=base_headers, timeout=20)
                if r.status_code != 200:
                    last_err = f"HTTP {r.status_code} from {urlparse(endpoint).netloc}"
                    continue
                data = r.json()
                wrapped_key = base64.b64decode(data["key"])
                wrapped_iv = base64.b64decode(data["iv"])
                glt = data["glt"]
                user_key = hashlib.sha256(glt.encode("utf-8")).digest()
                aad = content_id.encode("utf-8")
                ctr_key = _gcm_unwrap(user_key, wrapped_key, aad)
                ctr_iv = _gcm_unwrap(user_key, wrapped_iv, aad)
                return ctr_key, ctr_iv
            except KeyError as e:
                last_err = f"rights response missing field: {e}"
            except Exception as e:
                last_err = str(e)[:200]
    raise RuntimeError(f"mango rights failed: {last_err}")


def decrypt_stream(data, ctr_key, ctr_iv):
    """Decrypt an AES-CTR encrypted audio stream."""
    return _decrypt_aes_ctr(ctr_key, ctr_iv, data)


# ==============================================================================
# COOKIE & AUTH HELPERS
# ==============================================================================
def decode_jwt_payload(token):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
    except Exception:
        return {}


def check_jwt_expired(token):
    data = decode_jwt_payload(token)
    exp = data.get("exp")
    if exp and time.time() > float(exp):
        return True
    return False


def load_suno_cookie_from_file(path):
    if not path or not os.path.isfile(path):
        return "", "", "", False

    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
    except Exception:
        return "", "", "", False

    if not raw:
        return "", "", "", False

    cookie_dict = {}
    session_token = ""
    client_token = ""

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            for c in data:
                if not isinstance(c, dict):
                    continue
                domain = (c.get("domain") or "").lower()
                name = (c.get("name") or "").strip()
                value = (c.get("value") or "").strip()
                if "suno.com" in domain and name and value:
                    cookie_dict[name] = value
                    if name == "__session" or (name.startswith("__session_") and not session_token):
                        session_token = value
                    if name == "__client" or (name.startswith("__client_") and not client_token):
                        client_token = value
    except Exception:
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                domain, name, value = parts[0].lower(
                ), parts[5].strip(), parts[6].strip()
                if "suno.com" in domain and name and value:
                    cookie_dict[name] = value
                    if name == "__session" or (name.startswith("__session_") and not session_token):
                        session_token = value
                    if name == "__client" or (name.startswith("__client_") and not client_token):
                        client_token = value

    cookie_str = "; ".join(f"{k}={v}" for k, v in cookie_dict.items())
    is_expired = check_jwt_expired(session_token) if session_token else False
    return cookie_str, session_token, client_token, is_expired


# ==============================================================================
# FOLDER & FILE PICKER DIALOG
# ==============================================================================
class FolderDialog(QDialog):
    def __init__(self, start_path, mode="folder", parent=None):
        super().__init__(parent)
        self.mode = mode
        self.selected_file = ""
        self.setWindowTitle("Select Folder" if mode ==
                            "folder" else "Select Cookie File")
        self.resize(420, 560)

        if not start_path or not os.path.exists(start_path):
            start_path = get_default_save_dir()
        if os.path.isfile(start_path):
            start_path = os.path.dirname(start_path)
        self.current_path = os.path.abspath(start_path)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        mem_frame = QFrame()
        mem_frame.setStyleSheet(
            "background-color: #181D27; border: 1px solid #30363D; border-radius: 6px; padding: 4px;")
        mem_layout = QVBoxLayout(mem_frame)
        mem_layout.setContentsMargins(6, 4, 6, 4)
        mem_layout.setSpacing(4)

        self.mem_label = QLabel("💾 Storage Memory: Calculating...")
        self.mem_label.setStyleSheet(
            "font-weight: bold; color: #79C0FF; font-size: 12px;")
        self.mem_bar = QProgressBar()
        self.mem_bar.setMaximumHeight(16)
        mem_layout.addWidget(self.mem_label)
        mem_layout.addWidget(self.mem_bar)
        layout.addWidget(mem_frame)

        shortcut_layout = QHBoxLayout()
        shortcut_layout.setSpacing(4)

        if is_android():
            root = get_android_root()
            btn_int = QPushButton("📱 Internal")
            btn_int.clicked.connect(lambda: self.jump_to(root))
            btn_dl = QPushButton("📥 Download")
            btn_dl.clicked.connect(lambda: self.jump_to(
                os.path.join(root, "Download")))
            btn_mus = QPushButton("🎵 Music")
            btn_mus.clicked.connect(
                lambda: self.jump_to(os.path.join(root, "Music")))
            shortcut_layout.addWidget(btn_int)
            shortcut_layout.addWidget(btn_dl)
            shortcut_layout.addWidget(btn_mus)
        else:
            home = os.path.expanduser("~")
            btn_home = QPushButton("🏠 Home")
            btn_home.clicked.connect(lambda: self.jump_to(home))
            btn_dl = QPushButton("📥 Downloads")
            btn_dl.clicked.connect(lambda: self.jump_to(
                os.path.join(home, "Downloads")))
            shortcut_layout.addWidget(btn_home)
            shortcut_layout.addWidget(btn_dl)

        btn_app = QPushButton("🐍 App Dir")
        btn_app.clicked.connect(lambda: self.jump_to(get_script_dir()))
        shortcut_layout.addWidget(btn_app)
        layout.addLayout(shortcut_layout)

        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit(self.current_path)
        btn_go = QPushButton("Go")
        btn_go.clicked.connect(lambda: self.jump_to(
            self.path_edit.text().strip()))
        path_layout.addWidget(self.path_edit, stretch=1)
        path_layout.addWidget(btn_go)
        layout.addLayout(path_layout)

        hint = "Tap a folder to open it:" if mode == "folder" else "Tap a folder to open, or tap a .txt/.json file to select:"
        layout.addWidget(QLabel(hint))

        self.dir_list = QListWidget()
        self.dir_list.itemClicked.connect(self.on_item_clicked)
        layout.addWidget(self.dir_list, stretch=1)

        nav_layout = QHBoxLayout()
        btn_up = QPushButton("⬆️ Up")
        btn_up.clicked.connect(self.go_up)
        btn_new = QPushButton("➕ New Folder")
        btn_new.clicked.connect(self.create_new_folder)
        nav_layout.addWidget(btn_up)
        nav_layout.addWidget(btn_new)
        layout.addLayout(nav_layout)

        action_layout = QHBoxLayout()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        self.btn_choose = QPushButton(
            "✅ Select This Folder" if mode == "folder" else "✅ Select File")
        self.btn_choose.setStyleSheet(
            "background-color: #238636; color: #FFFFFF; font-weight: bold; padding: 10px;")
        self.btn_choose.clicked.connect(self.accept)
        action_layout.addWidget(btn_cancel, stretch=1)
        action_layout.addWidget(self.btn_choose, stretch=2)
        layout.addLayout(action_layout)

        self.refresh_lists()

    def update_memory_info(self):
        total, used, free, pct = get_storage_info(self.current_path)
        if total > 0:
            self.mem_label.setText(
                f"💾 Free: {format_bytes_gb(free)}  |  Used: {format_bytes_gb(used)} / {format_bytes_gb(total)}"
            )
            self.mem_bar.setValue(pct)
        else:
            self.mem_label.setText("💾 Storage Memory: N/A")
            self.mem_bar.setValue(0)

    def jump_to(self, path):
        if not path:
            return
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            pass
        if os.path.isdir(path) and os.access(path, os.R_OK):
            self.current_path = os.path.abspath(path)
            self.refresh_lists()
        else:
            QMessageBox.warning(self, "Access Denied",
                                f"Cannot open folder:\n{path}")

    def refresh_lists(self):
        self.path_edit.setText(self.current_path)
        self.update_memory_info()
        self.dir_list.clear()

        parent_dir = os.path.dirname(self.current_path)
        if parent_dir and parent_dir != self.current_path:
            up_item = QListWidgetItem("⬆️  [..] Go Up One Level")
            up_item.setData(Qt.UserRole, ("up", parent_dir))
            self.dir_list.addItem(up_item)

        try:
            entries = os.listdir(self.current_path)
        except Exception as e:
            err_item = QListWidgetItem(f"⚠️ Permission denied: {e}")
            err_item.setData(Qt.UserRole, ("none", ""))
            self.dir_list.addItem(err_item)
            return

        folders, files = [], []
        for d in entries:
            if d.startswith(".") or d.startswith("$"):
                continue
            full_p = os.path.join(self.current_path, d)
            if os.path.isdir(full_p):
                folders.append(d)
            elif self.mode == "file" and d.lower().endswith((".txt", ".json")):
                files.append(d)

        folders.sort(key=lambda s: s.lower())
        files.sort(key=lambda s: s.lower())

        for folder in folders:
            item = QListWidgetItem(f"📁  {folder}")
            item.setData(
                Qt.UserRole, ("dir", os.path.join(self.current_path, folder)))
            self.dir_list.addItem(item)

        for f in files:
            item = QListWidgetItem(f"🍪  {f}")
            item.setData(
                Qt.UserRole, ("file", os.path.join(self.current_path, f)))
            self.dir_list.addItem(item)

    def on_item_clicked(self, item):
        data = item.data(Qt.UserRole)
        if not data:
            return
        kind, target = data
        if kind in ("up", "dir"):
            if os.path.isdir(target) and os.access(target, os.R_OK):
                self.current_path = os.path.abspath(target)
                self.refresh_lists()
            elif is_android() and not os.access(target, os.R_OK):
                self.jump_to(get_android_root())
        elif kind == "file":
            self.selected_file = target
            self.accept()

    def go_up(self):
        parent = os.path.dirname(self.current_path)
        if parent and parent != self.current_path:
            if os.access(parent, os.R_OK):
                self.current_path = parent
                self.refresh_lists()
            elif is_android():
                self.jump_to(get_android_root())

    def create_new_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            safe_name = re.sub(r'[\x00-\x1f\\/*?:"<>|]', "_", name.strip())
            new_path = os.path.join(self.current_path, safe_name)
            try:
                os.makedirs(new_path, exist_ok=True)
                self.current_path = new_path
                self.refresh_lists()
            except Exception as e:
                QMessageBox.warning(
                    self, "Error", f"Could not create folder:\n{e}")

    def get_selected_path(self):
        if self.mode == "file" and self.selected_file:
            return self.selected_file
        return self.path_edit.text().strip() or self.current_path


# ==============================================================================
# DOWNLOAD WORKER
# ==============================================================================
class DownloadWorker(QThread):
    progress = Signal(int, str)
    log_msg = Signal(str, str)
    all_done = Signal(int, int)

    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://suno.com/",
    }

    def __init__(self, urls, save_dir, download_audio, download_lyrics,
                 download_cover, cookie_path, skip_existing=True, convert_to_mp3=True):
        super().__init__()
        self.urls = urls
        self.save_dir = os.path.abspath(save_dir)
        self.download_audio = download_audio
        self.download_lyrics = download_lyrics
        self.download_cover = download_cover
        self.cookie_path = cookie_path
        self.skip_existing = skip_existing
        self.convert_to_mp3 = convert_to_mp3
        self.cookie = ""
        self.session_token = ""
        self.client_token = ""
        self._stop = False

    def stop(self):
        self._stop = True

    def create_session(self):
        session = requests.Session()
        retry = Retry(
            total=2, backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD", "POST"]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(self.BASE_HEADERS)
        return session

    def try_refresh_clerk_token(self, session):
        if not self.cookie:
            return ""
        try:
            headers = {
                "Cookie": self.cookie,
                "Origin": "https://suno.com",
                "Referer": "https://suno.com/",
                "Accept": "application/json"
            }
            payload = decode_jwt_payload(self.session_token)
            sid = payload.get("sid")
            if sid:
                url = f"https://auth.suno.com/v1/client/sessions/{sid}/tokens?_clerk_js_version=5.15.0"
                r = session.post(url, headers=headers, timeout=12)
                if r.status_code == 200:
                    jwt_str = r.json().get("jwt")
                    if jwt_str:
                        return jwt_str

            r2 = session.get(
                "https://auth.suno.com/v1/client?_clerk_js_version=5.15.0", headers=headers, timeout=12)
            if r2.status_code == 200:
                resp_data = r2.json().get("response") or {}
                sessions = resp_data.get("sessions") or []
                if sessions:
                    last_token = (sessions[0].get(
                        "last_active_token") or {}).get("jwt")
                    if last_token:
                        return last_token
                    sid2 = sessions[0].get("id")
                    if sid2:
                        r3 = session.post(
                            f"https://auth.suno.com/v1/client/sessions/{sid2}/tokens?_clerk_js_version=5.15.0",
                            headers=headers, timeout=12
                        )
                        if r3.status_code == 200:
                            return r3.json().get("jwt") or ""
        except Exception:
            pass
        return ""

    def run(self):
        total = len(self.urls)
        success_count = 0
        fail_count = 0

        self.cookie, self.session_token, self.client_token, is_expired = load_suno_cookie_from_file(
            self.cookie_path)

        try:
            os.makedirs(self.save_dir, exist_ok=True)
        except Exception as e:
            self.log_msg.emit(f"❌ Cannot create save directory: {e}", "error")
            self.all_done.emit(0, total)
            return

        ffmpeg = find_ffmpeg()
        if ffmpeg:
            self.log_msg.emit(
                f"🎬 ffmpeg detected: {os.path.basename(os.path.dirname(ffmpeg)) or 'system'}", "success")
        else:
            self.log_msg.emit(
                "ℹ️ ffmpeg not found. Install: pip install imageio-ffmpeg", "info")

        with self.create_session() as session:
            if self.cookie:
                if is_expired:
                    self.log_msg.emit(
                        "🔄 __session token expired. Attempting auto-refresh...", "warning")
                    fresh_jwt = self.try_refresh_clerk_token(session)
                    if fresh_jwt:
                        self.session_token = fresh_jwt
                        self.log_msg.emit(
                            "✅ Bearer Token refreshed automatically!", "success")
                    else:
                        self.log_msg.emit(
                            "⚠️ Auto-refresh failed. Using existing cookie data.", "warning")
                else:
                    self.log_msg.emit(
                        f"✅ Cookie loaded: {os.path.basename(self.cookie_path)}", "success")
            else:
                self.log_msg.emit(
                    "ℹ️ No cookie. Public media_urls will be used (usually works).", "info")

            for idx, url in enumerate(self.urls):
                if self._stop:
                    self.log_msg.emit(
                        "🛑 Download cancelled by user.", "warning")
                    break
                try:
                    base_pct = int((idx / total) * 100)
                    self.progress.emit(
                        base_pct, f"[{idx + 1}/{total}] Processing: {url}")
                    ok = self.process_url(session, url, idx, total)
                    if ok:
                        success_count += 1
                    else:
                        fail_count += 1
                except InterruptedError:
                    self.log_msg.emit("🛑 Download interrupted.", "warning")
                    break
                except Exception as e:
                    fail_count += 1
                    self.log_msg.emit(f"❌ Error for {url}: {str(e)}", "error")

        self.progress.emit(100, "Finished")
        self.all_done.emit(success_count, fail_count)

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------
    @staticmethod
    def is_invalid_or_placeholder_audio(url):
        if not url:
            return True
        low = url.lower()
        return any(x in low for x in [
            "sil-100", "silent.mp3", "silence",
            "/api/forbidden", "forbidden", "error.mp3"
        ])

    @staticmethod
    def sanitize_filename(name, fallback="suno_song"):
        cleaned = re.sub(r'[\x00-\x1f\\/*?:"<>|]', "_", name or "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        if not cleaned or cleaned.upper() in WINDOWS_RESERVED_NAMES:
            cleaned = fallback
        return cleaned[:100]

    @staticmethod
    def _audio_ext_score(content_type, url):
        """Return (ext, priority_score) based on content-type / URL."""
        ct = (content_type or "").lower()
        if "mp3" in ct or "mpeg" in ct:
            return ".mp3", 100
        if "m4a" in ct or "opus" in ct:
            return ".m4a", 80
        if "mp4" in ct:
            return ".mp4", 60
        path = url.split("?")[0]
        ext = os.path.splitext(path)[1].lower()
        if ext in (".mp3", ".m4a", ".mp4", ".ogg", ".wav", ".flac"):
            return ext, 50
        return ".m4a", 40

    def _find_existing_audio(self, file_stem):
        for ext in (".mp3", ".m4a", ".mp4", ".ogg", ".wav", ".flac"):
            p = os.path.join(self.save_dir, f"{file_stem}{ext}")
            if os.path.exists(p) and os.path.getsize(p) > 10240:
                # Validate: skip only if the file is real audio. Encrypted
                # ciphertext (e.g. pre-fix mango downloads) must re-download.
                try:
                    with open(p, "rb") as f:
                        if _looks_like_audio(f.read(64)):
                            return p
                except Exception:
                    pass
                self.log_msg.emit(
                    f"♻️ Existing file is not valid audio; re-downloading: "
                    f"{os.path.basename(p)}",
                    "warning"
                )
        return None

    def _convert_with_ffmpeg(self, ffmpeg, src, dst, bitrate="192k"):
        try:
            subprocess.run(
                [ffmpeg, "-y", "-i", src, "-vn",
                 "-codec:a", "libmp3lame", "-b:a", bitrate, dst],
                check=True, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, timeout=300,
            )
            return os.path.exists(dst) and os.path.getsize(dst) > 1024
        except subprocess.CalledProcessError as e:
            err = (e.stderr or b"").decode(errors="ignore")[-300:]
            self.log_msg.emit(f"⚠️ ffmpeg conversion failed: {err}", "warning")
            return False
        except Exception as e:
            self.log_msg.emit(f"⚠️ ffmpeg error: {str(e)[:200]}", "warning")
            return False

    def _finalize_audio(self, source_path, file_stem, ext, idx, total):
        """Move downloaded file to final name, converting to mp3 if possible."""
        # Already mp3: rename to final
        if ext == ".mp3":
            final_path = os.path.join(self.save_dir, f"{file_stem}.mp3")
            if source_path != final_path:
                if os.path.exists(final_path):
                    try:
                        os.remove(final_path)
                    except Exception:
                        pass
                os.replace(source_path, final_path)
            return final_path

        # Try mp3 conversion
        if self.convert_to_mp3:
            ffmpeg = find_ffmpeg()
            if ffmpeg:
                self.progress.emit(
                    int((idx / total) * 100),
                    f"🔄 Converting {ext} → MP3..."
                )
                mp3_path = os.path.join(self.save_dir, f"{file_stem}.mp3")
                if self._convert_with_ffmpeg(ffmpeg, source_path, mp3_path):
                    try:
                        os.remove(source_path)
                    except Exception:
                        pass
                    size_mb = os.path.getsize(mp3_path) / (1024 * 1024)
                    self.log_msg.emit(
                        f"✅ MP3 created: {file_stem}.mp3 ({size_mb:.1f} MB)", "success"
                    )
                    return mp3_path
                else:
                    self.log_msg.emit(
                        f"⚠️ Conversion failed; keeping {ext} file", "warning")
            else:
                self.log_msg.emit(
                    f"ℹ️ ffmpeg missing; keeping {ext} file", "info")

        # Keep original format
        final_path = os.path.join(self.save_dir, f"{file_stem}{ext}")
        if source_path != final_path:
            if os.path.exists(final_path):
                try:
                    os.remove(final_path)
                except Exception:
                    pass
            os.replace(source_path, final_path)
        return final_path

    # ------------------------------------------------------------------
    # HTML / API PARSING
    # ------------------------------------------------------------------
    def extract_rsc_text(self, html_text):
        chunks = []
        for match in re.finditer(r'self\.__next_f\.push\(\[\s*\d+\s*,\s*"((?:\\.|[^"\\])*)"\s*\]\)', html_text):
            try:
                chunks.append(json.loads(f'"{match.group(1)}"'))
            except Exception:
                pass
        return "\n".join(chunks)

    def extract_song_uuid(self, soup, final_url, html_text, rsc_text):
        m = UUID_RE.search(final_url)
        if m:
            return m.group(1).lower()

        for tag, attr, key in [("link", "rel", "canonical"), ("meta", "property", "og:url"), ("meta", "property", "og:audio")]:
            elem = soup.find(tag, attrs={attr: key})
            if elem:
                content = elem.get("href") or elem.get("content") or ""
                if isinstance(content, list):
                    content = " ".join(content)
                m = UUID_RE.search(str(content))
                if m:
                    return m.group(1).lower()

        for source in (rsc_text, html_text):
            for pat in [
                r'"clip"\s*:\s*\{[^{}]*?"id"\s*:\s*"([0-9a-fA-F-]{36})"',
                r'"id"\s*:\s*"([0-9a-fA-F-]{36})"',
                r'https?://[^"\'\s<>]*?/([0-9a-fA-F-]{36})\.(?:mp3|m4a)'
            ]:
                m = re.search(pat, source)
                if m:
                    return m.group(1).lower()
        return None

    def fetch_clip_api(self, session, song_uuid):
        if not song_uuid:
            return {}

        endpoints = [
            f"https://studio-api.prod.suno.com/api/clip/{song_uuid}",
            f"https://studio-api-prod.suno.com/api/clip/{song_uuid}",
        ]

        header_variants = []
        if self.cookie or self.session_token:
            auth_h = {"Accept": "application/json",
                      "Origin": "https://suno.com", "Referer": "https://suno.com/"}
            if self.cookie:
                auth_h["Cookie"] = self.cookie
            if self.session_token:
                auth_h["Authorization"] = f"Bearer {self.session_token}"
            header_variants.append(auth_h)

        header_variants.append(
            {"Accept": "application/json", "Origin": "https://suno.com", "Referer": "https://suno.com/"})

        for hdrs in header_variants:
            for ep in endpoints:
                try:
                    r = session.get(ep, headers=hdrs, timeout=15)
                    if r.status_code == 200:
                        data = r.json()
                        if isinstance(data, dict) and data.get("id"):
                            self.log_msg.emit(
                                f"🌐 API metadata fetched ({song_uuid[:8]}).", "info")
                            return data
                except Exception:
                    continue
        return {}

    # ------------------------------------------------------------------
    # AUDIO CANDIDATES (priority-ordered)
    # ------------------------------------------------------------------
    def find_audio_candidates(self, clip_api_data, soup, html_text, rsc_text, song_uuid):
        """
        Returns list of (url, ext) sorted by priority:
          1. media_urls from /api/clip (CloudFront m4a-opus/mp3) ← most reliable
          2. audio_url (if not forbidden)
          3. og:audio
          4. CDN URLs found in HTML
          5. legacy cdn1.suno.ai/{uuid}.mp3
        """
        scored = []

        for media in clip_api_data.get("media_urls") or []:
            if not isinstance(media, dict):
                continue
            url = media.get("url")
            if not isinstance(url, str) or not url.startswith("http"):
                continue
            ext, score = self._audio_ext_score(media.get("content_type"), url)
            scored.append((url, ext, score))

        audio_url = clip_api_data.get("audio_url") or ""
        if audio_url.startswith("http") and "/api/forbidden" not in audio_url:
            ext, score = self._audio_ext_score("audio/mpeg", audio_url)
            scored.append((audio_url, ext, score - 10))

        og_audio = soup.find("meta", property="og:audio")
        if og_audio and og_audio.get("content"):
            url = og_audio.get("content")
            if url.startswith("http") and not self.is_invalid_or_placeholder_audio(url):
                ext, score = self._audio_ext_score("", url)
                scored.append((url, ext, score - 20))

        for source in (rsc_text, html_text):
            for m in re.finditer(
                r'https?://(?:cdn[0-9a-z-]*|audiopipe|cloudfront)[^\s"\'\\<>]*?\.(?:mp3|m4a|mp4)(?:\?[^\s"\'\\<>]*)?',
                source
            ):
                url = m.group(0).replace("\\u002F", "/").replace("\\/", "/")
                if self.is_invalid_or_placeholder_audio(url):
                    continue
                ext, score = self._audio_ext_score("", url)
                scored.append((url, ext, score - 30))

        if song_uuid:
            scored.append(
                (f"https://cdn1.suno.ai/{song_uuid}.mp3", ".mp3", 20))
            scored.append(
                (f"https://audiopipe.suno.ai/?item_id={song_uuid}", ".mp3", 15))

        seen, result = set(), []
        for url, ext, _ in sorted(scored, key=lambda x: -x[2]):
            if url in seen:
                continue
            seen.add(url)
            result.append((url, ext))
        return result

    # ------------------------------------------------------------------
    # METADATA EXTRACTION
    # ------------------------------------------------------------------
    def find_title(self, soup, rsc_text, clip_api_data, song_uuid):
        if clip_api_data.get("title"):
            return str(clip_api_data["title"]).strip()
        m = re.search(r'"title"\s*:\s*"((?:\\.|[^"\\])+)"', rsc_text)
        if m:
            try:
                return json.loads(f'"{m.group(1)}"').strip()
            except Exception:
                pass
        og = soup.find("meta", property="og:title")
        if og and og.get("content"):
            t = og.get("content", "")
            t = re.sub(r"\s*[\|\-]\s*Suno.*$", "", t, flags=re.I).strip()
            if t:
                return t
        return f"suno_{(song_uuid[:8] if song_uuid else 'unknown')}"

    def find_cover_url(self, soup, rsc_text, clip_api_data):
        if clip_api_data.get("image_large_url"):
            return clip_api_data["image_large_url"]
        if clip_api_data.get("image_url"):
            return clip_api_data["image_url"]
        og_img = soup.find("meta", property="og:image")
        if og_img and og_img.get("content"):
            return og_img["content"]
        m = re.search(r'"image_url"\s*:\s*"(https?://[^"]+)"', rsc_text)
        if m:
            return m.group(1)
        return None

    def find_lyrics(self, soup, rsc_text, clip_api_data):
        meta = clip_api_data.get("metadata")
        if isinstance(meta, dict):
            for key in ("prompt", "lyric", "lyrics"):
                val = meta.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()

        for pat in [r'"prompt"\s*:\s*"((?:\\.|[^"\\])+)"', r'"lyrics"\s*:\s*"((?:\\.|[^"\\])+)"']:
            for m in re.finditer(pat, rsc_text):
                try:
                    decoded = json.loads(f'"{m.group(1)}"').strip()
                    if len(decoded) > 5:
                        return decoded
                except Exception:
                    pass
        return None

    # ------------------------------------------------------------------
    # MANGO DECRYPTION
    # ------------------------------------------------------------------
    def _decrypt_if_encrypted(self, session, path, song_uuid):
        """
        Check downloaded file for valid audio magic bytes. If encrypted
        (Suno mango stream), fetch rights, unwrap keys, decrypt in place.
        Returns True if file is valid audio (or was successfully decrypted).
        """
        try:
            with open(path, "rb") as f:
                head = f.read(64)
        except Exception as e:
            self.log_msg.emit(
                f"⚠️ Cannot read {os.path.basename(path)}: {e}", "warning")
            return False

        if _looks_like_audio(head):
            return True

        if not song_uuid:
            self.log_msg.emit(
                "⚠️ Encrypted stream but no clip ID; cannot decrypt", "warning")
            return False

        if not _CRYPTO_AVAILABLE:
            self.log_msg.emit(
                "⚠️ Encrypted stream but 'cryptography' package missing "
                "(pip install cryptography)", "warning"
            )
            return False

        self.log_msg.emit("🔐 Encrypted stream detected, decrypting...", "info")
        try:
            extra = {}
            if self.cookie:
                extra["Cookie"] = self.cookie
            if self.session_token:
                extra["Authorization"] = "******"
            ctr_key, ctr_iv = fetch_stream_rights(session, song_uuid, extra)

            with open(path, "rb") as f:
                encrypted = f.read()
            plain = decrypt_stream(encrypted, ctr_key, ctr_iv)

            if not _looks_like_audio(plain[:64]):
                raise ValueError(
                    "decrypted data is not a recognized audio container")

            tmp = path + ".dec"
            with open(tmp, "wb") as f:
                f.write(plain)
            os.replace(tmp, path)
            self.log_msg.emit("✅ Decrypted", "success")
            return True
        except Exception as e:
            self.log_msg.emit(
                f"⚠️ Decryption failed: {str(e)[:200]}", "warning")
            return False

    # ------------------------------------------------------------------
    # MAIN PROCESS
    # ------------------------------------------------------------------
    def process_url(self, session, url, idx, total):
        if UUID_RE.fullmatch(url.strip()):
            url = f"https://suno.com/song/{url.strip()}"

        page_headers = {}
        if self.cookie:
            page_headers["Cookie"] = self.cookie

        resp = session.get(url, headers=page_headers,
                           allow_redirects=True, timeout=30)
        resp.raise_for_status()
        final_url, html_text = resp.url, resp.text
        soup = BeautifulSoup(html_text, "html.parser")
        rsc_text = self.extract_rsc_text(html_text)
        song_uuid = self.extract_song_uuid(
            soup, final_url, html_text, rsc_text)

        clip_api_data = self.fetch_clip_api(session, song_uuid)

        title = self.find_title(soup, rsc_text, clip_api_data, song_uuid)
        short_id = song_uuid[:8] if song_uuid else "unknown"
        safe_title = self.sanitize_filename(title, fallback=f"suno_{short_id}")
        file_stem = f"{safe_title}_{short_id}"

        audio_ok = True
        lyrics_ok = True
        cover_ok = True

        # -------- AUDIO --------
        if self.download_audio and not self._stop:
            existing = self._find_existing_audio(file_stem)
            if self.skip_existing and existing:
                self.log_msg.emit(
                    f"⏭️ Audio exists: {os.path.basename(existing)} ({human_size(os.path.getsize(existing))})",
                    "info"
                )
                audio_ok = True
            else:
                audio_ok = False
                candidates = self.find_audio_candidates(
                    clip_api_data, soup, html_text, rsc_text, song_uuid)
                if not candidates:
                    self.log_msg.emit(
                        f"❌ No audio URL found: {file_stem}", "error")
                else:
                    for cand_url, ext in candidates:
                        if self._stop:
                            raise InterruptedError()
                        temp_path = os.path.join(
                            self.save_dir, f"{file_stem}_source{ext}")
                        try:
                            self.download_file_with_fallback(
                                session, cand_url, temp_path, idx, total, file_stem
                            )
                            # Suno serves AES-CTR encrypted streams; detect and decrypt.
                            if not self._decrypt_if_encrypted(session, temp_path, song_uuid):
                                raise RuntimeError("decryption failed")
                            size = human_size(os.path.getsize(temp_path))
                            self.log_msg.emit(
                                f"✅ Downloaded: {file_stem}_source{ext} ({size})", "success"
                            )
                            self._finalize_audio(
                                temp_path, file_stem, ext, idx, total)
                            audio_ok = True
                            break
                        except InterruptedError:
                            raise
                        except Exception as e:
                            self.log_msg.emit(
                                f"⚠️ Candidate failed: {e}", "warning")
                            if os.path.exists(temp_path):
                                try:
                                    os.remove(temp_path)
                                except Exception:
                                    pass
                    if not audio_ok:
                        self.log_msg.emit(
                            f"❌ All audio candidates failed: {file_stem}", "error")

        # -------- LYRICS --------
        if self.download_lyrics and not self._stop:
            lyrics_dir = os.path.join(self.save_dir, "Lyrics")
            lyrics_path = os.path.join(lyrics_dir, f"{file_stem}_lyrics.txt")
            if self.skip_existing and os.path.exists(lyrics_path) and os.path.getsize(lyrics_path) > 0:
                self.log_msg.emit(
                    f"⏭️ Lyrics exist: Lyrics/{file_stem}_lyrics.txt", "info")
            else:
                lyrics = self.find_lyrics(soup, rsc_text, clip_api_data)
                if lyrics:
                    try:
                        os.makedirs(lyrics_dir, exist_ok=True)
                        with open(lyrics_path, "w", encoding="utf-8") as f:
                            f.write(lyrics)
                        self.log_msg.emit(
                            f"✅ Lyrics saved: Lyrics/{file_stem}_lyrics.txt", "success")
                    except Exception as e:
                        lyrics_ok = False
                        self.log_msg.emit(
                            f"❌ Failed to write lyrics: {e}", "error")
                else:
                    self.log_msg.emit(
                        f"⚠️ No lyrics found: {file_stem}", "warning")

        # -------- COVER --------
        if self.download_cover and not self._stop:
            cover_url = self.find_cover_url(soup, rsc_text, clip_api_data)
            if cover_url:
                covers_dir = os.path.join(self.save_dir, "Covers")
                ext = ".jpeg" if ".jpeg" in cover_url.lower() else ".jpg"
                cover_path = os.path.join(covers_dir, f"{file_stem}{ext}")
                if self.skip_existing and os.path.exists(cover_path) and os.path.getsize(cover_path) > 512:
                    self.log_msg.emit(
                        f"⏭️ Cover exists: Covers/{file_stem}{ext}", "info")
                else:
                    try:
                        os.makedirs(covers_dir, exist_ok=True)
                        self.download_file_with_fallback(
                            session, cover_url, cover_path, idx, total,
                            f"{file_stem} (Cover)", min_bytes=1024
                        )
                        self.log_msg.emit(
                            f"✅ Cover saved: Covers/{file_stem}{ext}", "success")
                    except Exception as e:
                        cover_ok = False
                        self.log_msg.emit(
                            f"⚠️ Cover download failed: {e}", "warning")
            else:
                self.log_msg.emit(f"⚠️ No cover found: {file_stem}", "warning")

        if self.download_audio:
            return audio_ok
        if self.download_lyrics:
            return lyrics_ok
        return cover_ok

    # ------------------------------------------------------------------
    # NETWORK DOWNLOAD WITH FALLBACK + RESUME
    # ------------------------------------------------------------------
    def download_file_with_fallback(self, session, url, path, idx, total, label, min_bytes=10_000):
        strategies = []
        if self.cookie or self.session_token:
            s1 = {"Referer": "https://suno.com/",
                  "Origin": "https://suno.com", "Accept": "*/*"}
            if self.cookie:
                s1["Cookie"] = self.cookie
            if self.session_token:
                s1["Authorization"] = f"Bearer {self.session_token}"
            strategies.append(s1)

        strategies.append({"Referer": "https://suno.com/", "Accept": "*/*"})
        strategies.append({"Accept": "*/*"})

        last_err = None
        for hdrs in strategies:
            try:
                self._stream_to_disk(session, url, path,
                                     hdrs, idx, total, label, min_bytes)
                return
            except InterruptedError:
                raise
            except Exception as e:
                last_err = e
                continue
        raise last_err

    def _stream_to_disk(self, session, url, path, headers, idx, total, label, min_bytes):
        temp_path = f"{path}.part"

        # Resume support: if .part exists, try Range
        resume_from = 0
        if os.path.exists(temp_path):
            try:
                resume_from = os.path.getsize(temp_path)
            except Exception:
                resume_from = 0

        req_headers = dict(headers)
        if resume_from > 0:
            req_headers["Range"] = f"bytes={resume_from}-"

        try:
            with session.get(url, stream=True, timeout=60, headers=req_headers) as resp:
                if resp.status_code == 416:
                    # Range not satisfiable → file already complete
                    os.replace(temp_path, path)
                    return

                if resp.status_code == 403:
                    raise Exception("403 Forbidden")

                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "").lower()
                if "text/html" in ctype or "application/json" in ctype:
                    raise Exception(f"Invalid Content-Type ({ctype})")

                total_len = int(resp.headers.get("Content-Length", 0))

                if resume_from > 0 and resp.status_code == 206:
                    mode = "ab"
                    downloaded = resume_from
                    full_total = resume_from + total_len
                else:
                    mode = "wb"
                    downloaded = 0
                    full_total = total_len

                with open(temp_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=32768):
                        if self._stop:
                            raise InterruptedError()
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            if full_total > 0:
                                file_pct = downloaded / full_total
                                overall_pct = int(
                                    ((idx + file_pct) / total) * 100)
                                self.progress.emit(
                                    overall_pct,
                                    f"Downloading {label}: {int(file_pct * 100)}% "
                                    f"({human_size(downloaded)} / {human_size(full_total)})"
                                )

                if downloaded < min_bytes:
                    raise Exception(f"File too small ({downloaded} bytes)")

                os.replace(temp_path, path)
        except InterruptedError:
            # Keep .part for resume next time
            raise
        except Exception:
            # Remove .part on hard errors
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            raise


# ==============================================================================
# MAIN WINDOW WITH TOUCH SCROLLER
# ==============================================================================
class SunoDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Suno Downloader Pro")
        self.resize(440, 780)
        self.worker = None

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.setCentralWidget(self.scroll)

        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroller = QScroller.scroller(self.scroll.viewport())
        scroller.grabGesture(self.scroll.viewport(),
                             QScroller.LeftMouseButtonGesture)
        scroller.grabGesture(self.scroll.viewport(), QScroller.TouchGesture)

        props = scroller.scrollerProperties()
        props.setScrollMetric(
            QScrollerProperties.DragVelocitySmoothingFactor, 0.6)
        props.setScrollMetric(QScrollerProperties.MinimumVelocity, 0.1)
        props.setScrollMetric(QScrollerProperties.MaximumVelocity, 1.5)
        scroller.setScrollerProperties(props)

        container = QWidget()
        self.scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.main_mem_label = QLabel("💾 Free Space: Calculating...")
        self.main_mem_label.setStyleSheet(
            "color: #56D364; font-weight: bold; font-size: 12px;")
        layout.addWidget(self.main_mem_label)

        url_group = QGroupBox("🎵 Suno Links or UUIDs")
        url_layout = QVBoxLayout()
        url_layout.setSpacing(6)
        self.url_text = QTextEdit()
        self.url_text.setPlaceholderText(
            "https://suno.com/s/XXXXXXXXXXXXXXXX\n"
            "https://suno.com/song/xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx\n"
            "or a bare UUID (deduplication by UUID)"
        )
        self.url_text.setMinimumHeight(85)
        self.url_text.setMaximumHeight(120)
        url_layout.addWidget(self.url_text)

        url_btn_layout = QHBoxLayout()
        btn_paste = QPushButton("📋 Paste")
        btn_paste.clicked.connect(self.paste_clipboard)
        btn_clear_urls = QPushButton("🧹 Clear")
        btn_clear_urls.clicked.connect(self.url_text.clear)
        url_btn_layout.addWidget(btn_paste)
        url_btn_layout.addWidget(btn_clear_urls)
        url_layout.addLayout(url_btn_layout)

        url_group.setLayout(url_layout)
        layout.addWidget(url_group)

        dir_group = QGroupBox("📁 Save Directory")
        dir_layout = QVBoxLayout()
        dir_layout.setSpacing(6)
        self.dir_edit = QLineEdit()
        self.dir_edit.setText(get_default_save_dir())
        self.dir_edit.textChanged.connect(self.update_main_memory_label)
        dir_layout.addWidget(self.dir_edit)

        dir_btn_layout = QHBoxLayout()
        btn_browse = QPushButton("📂 Choose Folder")
        btn_browse.clicked.connect(self.open_custom_folder_dialog)
        if is_android():
            btn_dl_quick = QPushButton("📥 Set to /Download/Suno")
            btn_dl_quick.clicked.connect(
                lambda: self.dir_edit.setText(get_default_save_dir()))
            dir_btn_layout.addWidget(btn_dl_quick)
        dir_btn_layout.addWidget(btn_browse)
        dir_layout.addLayout(dir_btn_layout)

        dir_group.setLayout(dir_layout)
        layout.addWidget(dir_group)

        cookie_group = QGroupBox(
            "🍪 Cookie File (optional — for authorized MP3)")
        cookie_layout = QVBoxLayout()
        cookie_layout.setSpacing(6)
        self.cookie_edit = QLineEdit()
        self.cookie_edit.setText(find_default_cookie_path())
        self.cookie_edit.setPlaceholderText("Path to cookie.txt (optional)")
        cookie_layout.addWidget(self.cookie_edit)

        cookie_btn_layout = QHBoxLayout()
        btn_cookie_browse = QPushButton("📂 Select cookie.txt")
        btn_cookie_browse.clicked.connect(self.browse_cookie_file)
        btn_cookie_check = QPushButton("🔍 Test Cookie")
        btn_cookie_check.clicked.connect(self.verify_cookie_now)
        cookie_btn_layout.addWidget(btn_cookie_browse)
        cookie_btn_layout.addWidget(btn_cookie_check)
        cookie_layout.addLayout(cookie_btn_layout)

        cookie_group.setLayout(cookie_layout)
        layout.addWidget(cookie_group)

        opt_group = QGroupBox("⚙️ Options")
        opt_outer = QVBoxLayout()
        opt_outer.setSpacing(4)

        opt_row1 = QHBoxLayout()
        self.cb_audio = QCheckBox("Audio")
        self.cb_audio.setChecked(True)
        self.cb_lyrics = QCheckBox("Lyrics")
        self.cb_lyrics.setChecked(True)
        self.cb_cover = QCheckBox("Cover")
        self.cb_cover.setChecked(False)
        opt_row1.addWidget(self.cb_audio)
        opt_row1.addWidget(self.cb_lyrics)
        opt_row1.addWidget(self.cb_cover)

        opt_row2 = QHBoxLayout()
        self.cb_skip = QCheckBox("Skip Existing")
        self.cb_skip.setChecked(True)
        self.cb_skip.setToolTip(
            "Skip files already present in the save directory")
        self.cb_convert = QCheckBox("Convert to MP3")
        self.cb_convert.setChecked(True)
        self.cb_convert.setToolTip(
            "Convert m4a/mp4/opus to MP3\nRequires: pip install imageio-ffmpeg"
        )
        opt_row2.addWidget(self.cb_skip)
        opt_row2.addWidget(self.cb_convert)

        opt_outer.addLayout(opt_row1)
        opt_outer.addLayout(opt_row2)
        opt_group.setLayout(opt_outer)
        layout.addWidget(opt_group)

        self.progress = QProgressBar()
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #79C0FF; font-weight: bold;")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        log_group = QGroupBox("📜 Activity Log")
        log_layout = QVBoxLayout()
        log_layout.setSpacing(6)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(130)
        log_layout.addWidget(self.log_text)

        btn_clear_log = QPushButton("🗑️ Clear Log")
        btn_clear_log.clicked.connect(self.log_text.clear)
        log_layout.addWidget(btn_clear_log)

        log_group.setLayout(log_layout)
        layout.addWidget(log_group)

        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("🚀 Start Download")
        self.btn_start.setStyleSheet(
            "QPushButton { background-color: #238636; color: #FFFFFF; padding: 11px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #2EA043; }"
            "QPushButton:disabled { background-color: #161B22; color: #6E7681; }"
        )
        self.btn_start.clicked.connect(self.start_download)

        self.btn_stop = QPushButton("🛑 Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setStyleSheet(
            "QPushButton { background-color: #DA3633; color: #FFFFFF; padding: 11px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #F85149; }"
            "QPushButton:disabled { background-color: #161B22; color: #6E7681; }"
        )
        self.btn_stop.clicked.connect(self.stop_download)

        btn_layout.addWidget(self.btn_start, stretch=2)
        btn_layout.addWidget(self.btn_stop, stretch=1)
        layout.addLayout(btn_layout)

        self.update_main_memory_label()

        # Detect ffmpeg at startup
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            self.log(f"🎬 ffmpeg ready: {ffmpeg}", "success")
        else:
            self.log(
                "ℹ️ ffmpeg not found. For MP3 conversion run: pip install imageio-ffmpeg",
                "info"
            )

        self.verify_cookie_now(silent_if_missing=True)

    def update_main_memory_label(self):
        path = self.dir_edit.text().strip() or get_default_save_dir()
        total, used, free, pct = get_storage_info(path)
        if total > 0:
            self.main_mem_label.setText(
                f"💾 Device Memory: {format_bytes_gb(free)} Free  (Used: {pct}% of {format_bytes_gb(total)})"
            )

    def paste_clipboard(self):
        clip = QApplication.clipboard().text().strip()
        if clip:
            current = self.url_text.toPlainText().strip()
            self.url_text.setPlainText(
                f"{current}\n{clip}".strip() if current else clip)

    def open_custom_folder_dialog(self):
        dialog = FolderDialog(self.dir_edit.text(), mode="folder", parent=self)
        if dialog.exec() == QDialog.Accepted:
            self.dir_edit.setText(dialog.get_selected_path())
            self.update_main_memory_label()

    def browse_cookie_file(self):
        start_dir = os.path.dirname(
            self.cookie_edit.text().strip()) or get_default_save_dir()
        dialog = FolderDialog(start_dir, mode="file", parent=self)
        if dialog.exec() == QDialog.Accepted:
            chosen = dialog.get_selected_path()
            if os.path.isdir(chosen):
                candidate = os.path.join(chosen, "cookie.txt")
                self.cookie_edit.setText(candidate)
            else:
                self.cookie_edit.setText(chosen)
            self.verify_cookie_now()

    def verify_cookie_now(self, silent_if_missing=False):
        c_path = self.cookie_edit.text().strip()
        cookie_str, s_token, c_token, is_expired = load_suno_cookie_from_file(
            c_path)
        if not cookie_str:
            if not silent_if_missing:
                self.log(
                    f"ℹ️ No cookie found at:\n{c_path}\n"
                    f"   Cookie is optional — public media_urls will be used.",
                    "info"
                )
        elif is_expired:
            if c_token:
                self.log(
                    "ℹ️ Cookie found (__session expired, will auto-refresh via __client).", "info")
            else:
                self.log(
                    "⚠️ Cookie '__session' expired. Export a new cookie.txt.", "warning")
        else:
            self.log(
                f"✅ Active cookie loaded ({os.path.basename(c_path)}).", "success")

    def log(self, msg, level="info"):
        color_map = {
            "info": "#E6EDF3",
            "success": "#56D364",
            "warning": "#E3B341",
            "error": "#FF7B72",
        }
        color = color_map.get(level, "#E6EDF3")
        escaped = (
            msg.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;")
               .replace("\n", "<br>")
        )
        self.log_text.append(f'<span style="color:{color};">{escaped}</span>')
        sb = self.log_text.verticalScrollBar()
        sb.setValue(sb.maximum())

    @staticmethod
    def parse_input_urls(raw_text):
        """Dedup by UUID: short URL + full URL + bare UUID all collapse to one entry."""
        seen_keys = set()
        valid_urls = []
        for line in raw_text.splitlines():
            u = line.strip()
            if not u:
                continue
            key = None
            if UUID_RE.fullmatch(u):
                key = u.lower()
                u = f"https://suno.com/song/{u}"
            elif u.startswith("http"):
                parsed = urlparse(u)
                if not parsed.netloc:
                    continue
                m = UUID_RE.search(u)
                key = m.group(1).lower() if m else u
            else:
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)
            valid_urls.append(u)
        return valid_urls

    def start_download(self):
        if self.worker and self.worker.isRunning():
            return

        if not (self.cb_audio.isChecked() or self.cb_lyrics.isChecked() or self.cb_cover.isChecked()):
            QMessageBox.warning(
                self, "Error", "Select at least one option (Audio, Lyrics, or Cover).")
            return

        urls = self.parse_input_urls(self.url_text.toPlainText())
        if not urls:
            QMessageBox.warning(
                self, "Error", "Please enter a valid Suno link.")
            return

        save_dir = self.dir_edit.text().strip()
        if not save_dir:
            QMessageBox.warning(
                self, "Error", "Please specify a save directory.")
            return

        cookie_path = self.cookie_edit.text().strip()

        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.log_text.clear()
        self.progress.setValue(0)
        self.status_label.setText(f"Starting download ({len(urls)} item)...")

        self.worker = DownloadWorker(
            urls,
            save_dir,
            self.cb_audio.isChecked(),
            self.cb_lyrics.isChecked(),
            self.cb_cover.isChecked(),
            cookie_path,
            skip_existing=self.cb_skip.isChecked(),
            convert_to_mp3=self.cb_convert.isChecked(),
        )
        self.worker.progress.connect(self.update_progress)
        self.worker.log_msg.connect(self.log)
        self.worker.all_done.connect(self.on_finished)
        self.worker.start()

    def stop_download(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.btn_stop.setEnabled(False)
            self.status_label.setText("Stopping...")
            self.log("🛑 Stopping...", "warning")

    def update_progress(self, value, msg):
        if value >= 0:
            self.progress.setValue(value)
        self.status_label.setText(msg)

    def on_finished(self, success_count, fail_count):
        self.btn_start.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.update_main_memory_label()
        summary = f"Finished! ✅ Success: {success_count} | ❌ Failed: {fail_count}"
        self.status_label.setText(summary)
        self.log(f"🏁 {summary}", "success" if fail_count == 0 else "error")
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(2000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    win = SunoDownloader()
    win.show()
    sys.exit(app.exec())
