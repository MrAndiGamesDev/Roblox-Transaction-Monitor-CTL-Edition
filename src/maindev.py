#!/usr/bin/env python3
"""
Roblox Transaction & Robux Monitor – PyQt + SQLite Edition
Author: MrAndiGamesDev (Refactored)
Secure, real-time monitoring with SQLite persistence.
"""
import json
import time
import ctypes
import threading
import logging
import requests
import sys
import webbrowser
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QTextEdit, QLineEdit, QDialog, QDialogButtonBox,
    QFormLayout, QMessageBox, QFrame
)
from PyQt5.QtCore import QThread, pyqtSignal, QObject, pyqtSlot
from PyQt5.QtGui import QFont, QTextCursor
from Core.Icon_manager import GetAppIcon

# -------------------------------------------------------------------------
# Paths & SQLite DB
# -------------------------------------------------------------------------
class Paths:
    APP_DIR = Path.home() / ".roblox_transaction_monitor"
    CONFIG_FILE = APP_DIR / "config.json"  # Legacy fallback
    DB_FILE = APP_DIR / "monitor.db"

    @classmethod
    def ensure_dirs(cls):
        cls.APP_DIR.mkdir(mode=0o700, exist_ok=True)

class Database:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def init_db(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                CREATE TABLE IF NOT EXISTS robux_log (
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    robux INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transactions (
                    type TEXT PRIMARY KEY,
                    amount INTEGER NOT NULL,
                    updated DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()

    # --- Config ---
    def get_config(self, key: str, default: str = "") -> str:
        with self._connect() as conn:
            cur = conn.execute("SELECT value FROM config WHERE key = ?", (key,))
            row = cur.fetchone()
            return row[0] if row else default

    def set_config(self, key: str, value: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO config (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value)
            )

    # --- Robux ---
    def log_robux(self, robux: int):
        with self._connect() as conn:
            conn.execute("INSERT INTO robux_log (robux) VALUES (?)", (robux,))

    def get_latest_robux(self) -> Optional[int]:
        with self._connect() as conn:
            cur = conn.execute("SELECT robux FROM robux_log ORDER BY timestamp DESC LIMIT 1")
            row = cur.fetchone()
            return row[0] if row else None

    # --- Transactions ---
    def upsert_transaction(self, type_: str, amount: int):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO transactions (type, amount) VALUES (?, ?) "
                "ON CONFLICT(type) DO UPDATE SET amount = excluded.amount, updated = CURRENT_TIMESTAMP",
                (type_, amount)
            )

    def get_all_transactions(self) -> Dict[str, int]:
        with self._connect() as conn:
            cur = conn.execute("SELECT type, amount FROM transactions")
            return {row[0]: row[1] for row in cur.fetchall()}

    def get_transaction_changes(self, new_data: Dict[str, int]) -> Dict[str, Tuple[int, int]]:
        old = self.get_all_transactions()
        changes = {}
        for k, v in new_data.items():
            old_v = old.get(k, 0)
            if v != old_v:
                changes[k] = (old_v, v)
                self.upsert_transaction(k, v)
        return changes

# -------------------------------------------------------------------------
# Logging
# -------------------------------------------------------------------------
class GUILogHandler(logging.Handler, QObject):
    new_record = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        QObject.__init__(self)
        self.formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S"
        )

    def emit(self, record):
        msg = self.formatter.format(record)
        self.new_record.emit(msg + "\n")

# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------
def abbreviate_number(num: int) -> str:
    abs_num = abs(num)
    for limit, suffix in [(1e15, "Q"), (1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]:
        if abs_num >= limit:
            return f"{num/limit:.2f}{suffix}"
    return str(num)

class SecureInput:
    @staticmethod
    def censor(text: str, show_start: int = 20, show_end: int = 10) -> str:
        if not text or len(text) <= show_start + show_end:
            return "*" * len(text)
        return f"{text[:show_start]}{'*' * (len(text) - show_start - show_end)}{text[-show_end:]}"

    @staticmethod
    def webhook(url: str) -> str:
        return SecureInput.censor(url, show_start=25, show_end=0) if url else ""

    @staticmethod
    def cookie(cookie: str) -> str:
        return SecureInput.censor(cookie, show_start=35, show_end=8) if cookie else ""

# -------------------------------------------------------------------------
# Rate Limiter + Safe API
# -------------------------------------------------------------------------
class RateLimiter:
    def __init__(self, min_interval: float = 1.0):
        self.min_interval = min_interval
        self.last_call = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = time.time()
            sleep_time = self.min_interval - (now - self.last_call)
            if sleep_time > 0:
                time.sleep(sleep_time)
            self.last_call = time.time()

rate_limiter = RateLimiter()

def safe_api_get(url: str, cookies: Dict[str, str], params: Optional[Dict] = None, timeout: int = 10, max_retries: int = 3) -> Optional[Dict]:
    for attempt in range(1, max_retries + 1):
        try:
            rate_limiter.wait()
            response = requests.get(url, cookies=cookies, params=params, timeout=timeout)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:
                log.warning("Rate limited (429). Waiting...")
                time.sleep(2 ** attempt)
            elif 500 <= response.status_code < 600:
                log.warning(f"Server error {response.status_code}. Retrying...")
            else:
                log.error(f"HTTP {response.status_code}: {response.text[:200]}")
                return None
        except (requests.Timeout, requests.ConnectionError) as e:
            log.warning(f"Network error ({type(e).__name__}). Retry {attempt}/{max_retries}")
        except json.JSONDecodeError:
            log.error("Invalid JSON from API")
            return None
        if attempt < max_retries:
            time.sleep(1.5 ** attempt)
    log.error(f"API call failed after {max_retries} retries: {url}")
    return None

# -------------------------------------------------------------------------
# Update Checker
# -------------------------------------------------------------------------
class UpdateChecker:
    REPO = "MrAndiGamesDev/Roblox-Transaction-Monitor-CTL-Edition"
    URL = f"https://api.github.com/repos/{REPO}/releases/latest"

    @staticmethod
    def get_current_version() -> str:
        try:
            return (Path(__file__).parent / "VERSION").read_text().strip()
        except Exception:
            return "v1.0.0"

    @staticmethod
    def check() -> Optional[Tuple[str, str]]:
        try:
            r = requests.get(UpdateChecker.URL, timeout=5)
            if r.status_code != 200:
                return None
            latest = r.json().get("tag_name", "")
            current = UpdateChecker.get_current_version()
            if latest and latest != current:
                return latest, r.json().get("html_url")
            return None
        except Exception:
            return None

# -------------------------------------------------------------------------
# Config Manager (uses DB)
# -------------------------------------------------------------------------
class Config:
    DEFAULTS = {
        "DISCORD_WEBHOOK_URL": "",
        "ROBLOSECURITY": "",
        "DISCORD_EMOJI_ID": "",
        "DISCORD_EMOJI_NAME": "",
        "CHECK_INTERVAL": "60",
        "TOTAL_CHECKS_TYPE": "Day",
    }

    def __init__(self, db: Database):
        self.db = db
        self._load_defaults()

    def _load_defaults(self):
        for k, v in self.DEFAULTS.items():
            if not self.db.get_config(k):
                self.db.set_config(k, v)

    def __getitem__(self, key):
        return self.db.get_config(key, self.DEFAULTS.get(key, ""))

    def __setitem__(self, key, value):
        self.db.set_config(key, str(value))

# -------------------------------------------------------------------------
# Roblox API
# -------------------------------------------------------------------------
class RobloxAPI:
    def __init__(self, cookie: str):
        self.cookies = {".ROBLOSECURITY": cookie}
        self.user_id: Optional[int] = None

    def authenticate(self) -> bool:
        data = safe_api_get("https://users.roblox.com/v1/users/authenticated", self.cookies)
        if data and (uid := data.get("id")):
            self.user_id = uid
            log.info(f"Authenticated as user ID: {uid}")
            return True
        log.error("Authentication failed.")
        return False

    def get_transaction_totals(self, timeframe: str) -> Optional[Dict]:
        if not self.user_id:
            return None
        url = f"https://economy.roblox.com/v2/users/{self.user_id}/transaction-totals"
        params = {"timeFrame": timeframe, "transactionType": "summary"}
        return safe_api_get(url, self.cookies, params=params)

    def get_robux(self) -> Optional[int]:
        if not self.user_id:
            return None
        data = safe_api_get(f"https://economy.roblox.com/v1/users/{self.user_id}/currency", self.cookies)
        return data.get("robux") if data else None

    def get_account_status(self) -> Optional[Dict]:
        if not self.user_id:
            return None
        data = safe_api_get(f"https://users.roblox.com/v1/users/{self.user_id}", self.cookies)
        if not data:
            return None
        return {
            "is_banned": data.get("isBanned", False),
            "username": data.get("name", "Unknown"),
            "created": data.get("created", "Unknown")
        }

# -------------------------------------------------------------------------
# Discord Notifier
# -------------------------------------------------------------------------
class DiscordNotifier:
    def __init__(self, webhook_url: str, emoji_name: str, emoji_id: str):
        self.url = webhook_url
        self.emoji = f"<:{emoji_name}:{emoji_id}>" if emoji_id else ""

    def _send(self, payload: Dict):
        if not self.url or "discord.com" not in self.url:
            return
        try:
            rate_limiter.wait()
            requests.post(self.url, json=payload, timeout=10)
        except Exception as e:
            log.debug(f"Discord send failed: {e}")

    def embed(self, title: str, color: int, fields: list):
        embed = {"title": title, "color": color, "fields": fields}
        embed["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._send({"embeds": [embed]})

    def transaction_change(self, changes: Dict[str, tuple]):
        fields = [
            {"name": k, "value": f"From {self.emoji} {abbreviate_number(old)} to {self.emoji} {abbreviate_number(new)}", "inline": False}
            for k, (old, new) in changes.items()
        ]
        self.embed("Transaction Updated", 0x00ff00, fields)

    def robux_change(self, old: int, new: int):
        color = 0x00ff00 if new > old else 0xff0000
        self.embed("Robux Balance Changed", color, [
            {"name": "Before", "value": f"{self.emoji} {abbreviate_number(old)}", "inline": True},
            {"name": "After", "value": f"{self.emoji} {abbreviate_number(new)}", "inline": True}
        ])

    def account_status(self, status: Dict, previous: Optional[Dict]):
        if previous == status:
            return
        color = 0xff0000 if status.get("is_banned") else 0x00ff00
        self.embed(
            "ACCOUNT BANNED" if status.get("is_banned") else "ACCOUNT ACTIVE",
            color,
            [
                {"name": "User", "value": status["username"], "inline": True},
                {"name": "Created", "value": status["created"], "inline": True}
            ]
        )

    def api_downtime(self, status: str, duration: Optional[float] = None):
        color = 0xff0000 if status == "DOWN" else 0x00ff00
        fields = [{"name": "Duration", "value": f"{duration:.1f}s", "inline": False}] if duration else []
        self.embed(f"Roblox API {status}", color, fields)

# -------------------------------------------------------------------------
# Worker Thread
# -------------------------------------------------------------------------
class MonitorWorker(QThread):
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    api_signal = pyqtSignal(str)
    timer_signal = pyqtSignal(str)
    robux_signal = pyqtSignal(str)
    sales_signal = pyqtSignal(str)

    def __init__(self, config: Config, api: RobloxAPI, notifier: DiscordNotifier, db: Database):
        super().__init__()
        self.config = config
        self.api = api
        self.notifier = notifier
        self.db = db
        self.stop_event = threading.Event()
        self.downtime_start = None
        self.last_status = None

    def run(self):
        while not self.stop_event.is_set():
            try:
                if not self._check_api_health():
                    self._wait()
                    continue
                self._check_transactions()
                self._check_robux()
                self._check_account_status()
            except Exception as e:
                self.log_signal.emit(f"Unexpected error: {e}")
                log.exception("Worker error")
            self._wait()

    def _check_api_health(self) -> bool:
        try:
            r = requests.get("https://users.roblox.com/v1/users/authenticated", cookies=self.api.cookies, timeout=10)
            if r.status_code == 200:
                if self.downtime_start:
                    duration = time.time() - self.downtime_start
                    self.notifier.api_downtime("RECOVERED", duration)
                    self.log_signal.cmit(f"API recovered after {duration:.1f}s")
                    self.api_signal.emit("API: OK")
                    self.downtime_start = None
                return True
        except Exception:
            pass
        if not self.downtime_start:
            self.downtime_start = time.time()
            self.notifier.api_downtime("DOWN")
            self.log_signal.emit("Roblox API unreachable.")
            self.api_signal.emit("API: DOWN")
        return False

    def _check_transactions(self):
        data = self.api.get_transaction_totals(self.config["TOTAL_CHECKS_TYPE"])
        if not data:
            return
        changes = self.db.get_transaction_changes(data)
        if changes:
            self.log_signal.emit("Transaction changes:")
            for k, (o, n) in changes.items():
                self.log_signal.emit(f"  {k}: {abbreviate_number(o)} to {abbreviate_number(n)}")
            self.notifier.transaction_change(changes)
            self.sales_signal.emit(f"Sales: {abbreviate_number(data.get('salesTotal', 0))}")

    def _check_robux(self):
        robux = self.api.get_robux()
        if robux is None:
            return
        last = self.db.get_latest_robux() or 0
        if robux != last:
            change = "Increased" if robux > last else "Decreased"
            self.log_signal.emit(f"Robux {change}: {abbreviate_number(last)} to {abbreviate_number(robux)}")
            self.notifier.robux_change(last, robux)
            self.db.log_robux(robux)
            self.robux_signal.emit(f"Robux: {abbreviate_number(robux)}")

    def _check_account_status(self):
        status = self.api.get_account_status()
        if not status:
            return
        if self.last_status != status:
            banned = status["is_banned"]
            self.log_signal.emit(f"Account {'BANNED' if banned else 'ACTIVE'}: {status['username']}")
            self.notifier.account_status(status, self.last_status)
            self.last_status = status

    def _wait(self):
        interval = max(10, int(self.config["CHECK_INTERVAL"] or 60))
        for i in range(interval, 0, -1):
            if self.stop_event.is_set():
                break
            mins, secs = divmod(i, 60)
            self.timer_signal.emit(f"Next check: {mins:02d}:{secs:02d}")
            time.sleep(1)
        self.timer_signal.emit("Next check: —")

# -------------------------------------------------------------------------
# Config Editor
# -------------------------------------------------------------------------
class ConfigEditor(QDialog):
    def __init__(self, parent, config: Config, callback=None):
        super().__init__(parent)
        self.config = config
        self.callback = callback
        self.setWindowTitle("Edit Configuration")
        self.setFixedSize(520, 420)
        self.setModal(True)
        layout = QFormLayout(self)
        self.entries = {}
        fields = [
            ("Discord Webhook URL", "DISCORD_WEBHOOK_URL", True),
            (".ROBLOSECURITY Cookie", "ROBLOSECURITY", True),
            ("Emoji ID", "DISCORD_EMOJI_ID", False),
            ("Emoji Name", "DISCORD_EMOJI_NAME", False),
            ("Check Interval (seconds)", "CHECK_INTERVAL", False),
            ("Timeframe", "TOTAL_CHECKS_TYPE", False),
        ]
        for label, key, hidden in fields:
            line = QLineEdit(config[key])
            if hidden:
                line.setEchoMode(QLineEdit.Password)
            layout.addRow(label + ":", line)
            self.entries[key] = line
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def save(self):
        for key, line in self.entries.items():
            self.config[key] = line.text().strip()
        log.info("Configuration saved.")
        self.accept()
        if self.callback:
            self.callback()

# -------------------------------------------------------------------------
# UI & Main Window
# -------------------------------------------------------------------------
def _styled_label(text: str, bold: bool = False) -> QLabel:
    lbl = QLabel(text)
    font = lbl.font()
    font.setFamily("Segoe UI")
    font.setPointSize(9)
    if bold:
        font.setBold(True)
    lbl.setFont(font)
    return lbl

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        Paths.ensure_dirs()
        self.db = Database(Paths.DB_FILE)
        self.appicon = GetAppIcon()
        self.config = Config(self.db)
        self.api = RobloxAPI(self.config["ROBLOSECURITY"])
        self.notifier = DiscordNotifier(
            self.config["DISCORD_WEBHOOK_URL"],
            self.config["DISCORD_EMOJI_NAME"],
            self.config["DISCORD_EMOJI_ID"]
        )
        self.worker: Optional[MonitorWorker] = None
        self.log_handler = GUILogHandler()
        self.log_handler.new_record.connect(self.append_log)
        self.appicon.set_app_icon(custom_path="src/", name="Robux.ico")
        self._setup_ui()
        self.check_update()
        self.validate_and_start()

    def _setup_ui(self):
        self.setWindowTitle("Roblox Transaction & Robux Monitor History")
        self.setGeometry(100, 100, 820, 620)
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Header
        header = QFrame()
        header.setFixedHeight(50)
        hlayout = QHBoxLayout(header)
        title = QLabel("Roblox Monitor")
        title.setFont(QFont("Segoe UI", 14, QFont.Bold))
        hlayout.addWidget(title)
        hlayout.addStretch()
        self.update_btn = QPushButton("Check Update")
        self.update_btn.clicked.connect(self.open_update_url)
        hlayout.addWidget(self.update_btn)
        layout.addWidget(header)

        # Status
        status_frame = QFrame()
        slayout = QHBoxLayout(status_frame)
        self.status_label = _styled_label("Status: Idle")
        self.api_label = _styled_label("API: —")
        self.timer_label = _styled_label("Next check: —")
        slayout.addWidget(self.status_label)
        slayout.addWidget(self.api_label)
        slayout.addStretch()
        slayout.addWidget(self.timer_label)
        layout.addWidget(status_frame)

        # Stats
        stats_frame = QFrame()
        stats_layout = QHBoxLayout(stats_frame)
        self.robux_label = _styled_label("Robux: —", bold=True)
        self.robux_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.sales_label = _styled_label("Sales: —", bold=True)
        self.sales_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        stats_layout.addWidget(self.robux_label)
        stats_layout.addWidget(self.sales_label)
        stats_layout.addStretch()
        layout.addWidget(stats_frame)

        # Controls
        control_frame = QFrame()
        clayout = QHBoxLayout(control_frame)
        self.start_btn = QPushButton("Start Monitoring")
        self.start_btn.clicked.connect(self.toggle_monitoring)
        self.config_btn = QPushButton("Edit Config")
        self.config_btn.clicked.connect(self.edit_config)
        clayout.addWidget(self.start_btn)
        clayout.addWidget(self.config_btn)
        clayout.addStretch()
        layout.addWidget(control_frame)

        # Log
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_text)

        # Logging
        global log
        log = logging.getLogger()
        log.setLevel(logging.INFO)
        log.addHandler(self.log_handler)

    def check_update(self):
        update = UpdateChecker.check()
        if update:
            latest, url = update
            self.update_url = url
            self.update_btn.setText(f"Update: {latest}")
        else:
            self.update_btn.setText("Check For Update")
            self.update_url = None

    def open_update_url(self):
        if hasattr(self, 'update_url') and self.update_url:
            webbrowser.open(self.update_url)

    def validate_and_start(self):
        if not self.config["ROBLOSECURITY"]:
            self.edit_config(first_run=True)
        elif not self.config["ROBLOSECURITY"].startswith("*|WARNING"):
            QMessageBox.critical(self, "Invalid Cookie", "Cookie must start with '*|WARNING'")
            self.edit_config()

    def toggle_monitoring(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop_event.set()
            self.worker.quit()
            self.worker.wait()
            self.worker = None
            self.start_btn.setText("Start Monitoring")
            self.status_label.setText("Status: Stopped")
            log.info("Monitoring stopped.")
        else:
            if not self.api.authenticate():
                QMessageBox.critical(self, "Auth Failed", "Invalid or expired .ROBLOSECURITY cookie.")
                return
            self.worker = MonitorWorker(self.config, self.api, self.notifier, self.db)
            self.worker.log_signal.connect(self.append_log)
            self.worker.status_signal.connect(lambda s: self.status_label.setText(s))
            self.worker.api_signal.connect(lambda s: self.api_label.setText(s))
            self.worker.timer_signal.connect(lambda s: self.timer_label.setText(s))
            self.worker.robux_signal.connect(lambda s: self.robux_label.setText(s))
            self.worker.sales_signal.connect(lambda s: self.sales_label.setText(s))
            self.worker.start()
            self.start_btn.setText("Stop Monitoring")
            self.status_label.setText("Status: Monitoring")
            log.info("Monitoring started.")

    def edit_config(self, first_run=False):
        dlg = ConfigEditor(self, self.config, callback=lambda: self.validate_and_start() if first_run else None)
        dlg.exec_()

    @pyqtSlot(str)
    def append_log(self, text: str):
        self.log_text.moveCursor(QTextCursor.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(QTextCursor.End)

# -------------------------------------------------------------------------
# Entry Point
# -------------------------------------------------------------------------
def _enable_high_dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass

if __name__ == "__main__":
    _enable_high_dpi()
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())