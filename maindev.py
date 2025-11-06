#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Roblox Transaction & Robux Monitor – GUI (PyQt5)
Author: MrAndiGamesDev (Refactored by AI + Trae-style Auto-Updater)
"""
import os
import sys
import json
import time
import threading
import requests
import tempfile
import shutil
import subprocess
import re
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from PyQt5 import QtCore, QtGui, QtWidgets

# --------------------------------------------------------------------------- #
# ──────────────────────────────── CONFIG ────────────────────────────────── #
# --------------------------------------------------------------------------- #
class Config:
    APP_DIR = os.path.join(os.path.expanduser("~"), ".roblox_transaction_history")
    CONFIG_FILE = os.path.join(APP_DIR, "config.json")
    STORAGE_DIR = os.path.join(APP_DIR, "transaction_info")
    DEFAULT = {
        "DISCORD_WEBHOOK_URL": "",
        "ROBLOSECURITY": "",
        "DISCORD_EMOJI_ID": "",
        "DISCORD_EMOJI_NAME": "",
        "CHECK_INTERVAL": "180",
        "TOTAL_CHECKS_TYPE": "Day",
        "THEME": "System"
    }

    def __init__(self):
        os.makedirs(self.APP_DIR, exist_ok=True, mode=0o700)
        os.makedirs(self.STORAGE_DIR, exist_ok=True)
        self.data = self.DEFAULT.copy()
        self._load()

    def _load(self):
        if os.path.exists(self.CONFIG_FILE):
            try:
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                for k, v in self.DEFAULT.items():
                    self.data[k] = loaded.get(k, v)
            except Exception:
                pass
        self.save()

    def save(self):
        tmp = self.CONFIG_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
            os.replace(tmp, self.CONFIG_FILE)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()


# --------------------------------------------------------------------------- #
# ──────────────────────────────── UTILITIES ─────────────────────────────── #
# --------------------------------------------------------------------------- #
_last_call = 0
def rate_limited_request(*args, **kwargs):
    global _last_call
    now = time.time()
    sleep = 1.0 - (now - _last_call)
    if sleep > 0:
        time.sleep(sleep)
    _last_call = time.time()
    return requests.request(*args, **kwargs)


def abbreviate_number(num: int) -> str:
    abs_num = abs(num)
    for limit, suffix in [(1e15, "Q"), (1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]:
        if abs_num >= limit:
            return f"{num/limit:.2f}{suffix}"
    return str(num)


# --------------------------------------------------------------------------- #
# ────────────────────────────── AUTO-UPDATER ─────────────────────────────── #
# --------------------------------------------------------------------------- #
CURRENT_VERSION = "1.0.0"
GITHUB_REPO = "MrAndiGamesDev/Roblox-Transaction-Monitor-CTL-Edition"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ASSET_WINDOWS = "Roblox-Transaction-Monitor-CTL-Edition.exe"
ASSET_LINUX = "Roblox-Transaction-Monitor-CTL-Edition"

class AutoUpdater:
    def __init__(self, parent: 'MainWindow'):
        self.parent = parent
        self.current_version = self._get_current_version()
        self.download_url = None
        self.asset_name = None
        self.temp_path = None

    def _get_current_version(self) -> str:
        """Read version from VERSION file or fall back to CURRENT_VERSION."""
        version_file = os.path.join(os.path.dirname(__file__), "VERSION")
        if os.path.exists(version_file):
            try:
                with open(version_file, "r", encoding="utf-8") as f:
                    return f.read().strip().lstrip("v")
            except Exception:
                pass
        return CURRENT_VERSION

    def check_and_update(self, manual: bool = False):
        def run():
            try:
                if manual:
                    self.parent.log("Checking for updates...", "orange")

                r = requests.get(GITHUB_API, timeout=10)
                if r.status_code != 200:
                    if manual:
                        self.parent.log("GitHub API unreachable.", "red")
                    return

                data = r.json()
                latest = data["tag_name"].lstrip("v")

                if self._compare_versions(latest, self.current_version) <= 0:
                    if manual:
                        self.parent.log("You are up to date.", "green")
                    return

                asset = None
                for a in data["assets"]:
                    name = a["name"]
                    if sys.platform.startswith("win") and name == ASSET_WINDOWS:
                        asset = a
                        break
                    elif sys.platform.startswith("linux") and name == ASSET_LINUX:
                        asset = a
                        break

                if not asset:
                    self.parent.log("No compatible update found.", "red")
                    return

                self.download_url = asset["browser_download_url"]
                self.asset_name = asset["name"]
                self.parent.log(f"Update found: v{latest} ({self.asset_name})", "orange")
                self._download_and_install()
            except Exception as e:
                if manual:
                    self.parent.log(f"Update check failed: {e}", "red")

        threading.Thread(target=run, daemon=True).start()

    @staticmethod
    def _compare_versions(v1: str, v2: str) -> int:
        v1p = [int(x) for x in re.findall(r'\d+', v1)]
        v2p = [int(x) for x in re.findall(r'\d+', v2)]
        for a, b in zip(v1p, v2p):
            if a > b: return 1
            if a < b: return -1
        return 0

    def _download_and_install(self):
        try:
            fd, self.temp_path = tempfile.mkstemp(suffix=os.path.splitext(self.asset_name)[1])
            os.close(fd)

            self.parent.log("Downloading update...", "cyan")
            r = requests.get(self.download_url, stream=True, timeout=60)
            r.raise_for_status()
            total = int(r.headers.get('content-length', 0))
            downloaded = 0
            chunk_size = 1024 * 1024

            with open(self.temp_path, 'wb') as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0:
                            percent = int(100 * downloaded / total)
                            self.parent.log(f"Downloading: {percent}%", "cyan")

            self.parent.log("Download complete. Installing...", "green")

            current_exe = sys.executable
            backup_exe = current_exe + ".backup"

            if os.path.exists(backup_exe):
                try:
                    os.remove(backup_exe)
                except:
                    pass

            shutil.move(current_exe, backup_exe)
            shutil.move(self.temp_path, current_exe)
            os.chmod(current_exe, 0o755)

            self.parent.log("Update installed. Restarting...", "green")
            time.sleep(1.5)
            self.parent.close()
            subprocess.Popen([current_exe])
            sys.exit(0)

        except Exception as e:
            self.parent.log(f"Update failed: {e}", "red")
            backup_exe = sys.executable + ".backup"
            if os.path.exists(backup_exe):
                try:
                    shutil.move(backup_exe, sys.executable)
                except:
                    pass

# --------------------------------------------------------------------------- #
# ──────────────────────────────── STORAGE ────────────────────────────────── #
# --------------------------------------------------------------------------- #
class Storage:
    def __init__(self):
        self.trans_file = os.path.join(Config.STORAGE_DIR, "last_transaction_data.json")
        self.robux_file = os.path.join(Config.STORAGE_DIR, "last_robux.json")

    def _default_transactions(self) -> Dict[str, int]:
        keys = [
            "salesTotal", "purchasesTotal", "affiliateSalesTotal", "groupPayoutsTotal",
            "currencyPurchasesTotal", "premiumStipendsTotal", "tradeSystemEarningsTotal",
            "tradeSystemCostsTotal", "premiumPayoutsTotal", "groupPremiumPayoutsTotal",
            "adSpendTotal", "developerExchangeTotal", "pendingRobuxTotal", "incomingRobuxTotal",
            "outgoingRobuxTotal", "individualToGroupTotal", "csAdjustmentTotal",
            "adsRevsharePayoutsTotal", "groupAdsRevsharePayoutsTotal", "subscriptionsRevshareTotal",
            "groupSubscriptionsRevshareTotal", "subscriptionsRevshareOutgoingTotal",
            "groupSubscriptionsRevshareOutgoingTotal", "publishingAdvanceRebatesTotal",
            "affiliatePayoutTotal"
        ]
        return {k: 0 for k in keys}

    def load_transactions(self) -> Dict[str, int]:
        if not os.path.exists(self.trans_file):
            default = self._default_transactions()
            self.save_transactions(default)
            return default
        try:
            with open(self.trans_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return self._default_transactions()

    def save_transactions(self, data: Dict[str, int]):
        tmp = self.trans_file + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, self.trans_file)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)

    def load_robux(self) -> int:
        if not os.path.exists(self.robux_file):
            return 0
        try:
            with open(self.robux_file, "r", encoding="utf-8") as f:
                return json.load(f).get("robux", 0)
        except Exception:
            return 0

    def save_robux(self, robux: int):
        tmp = self.robux_file + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"robux": robux}, f, indent=2)
            os.replace(tmp, self.robux_file)
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)


# --------------------------------------------------------------------------- #
# ────────────────────────────── ROBLOX API ─────────────────────────────── #
# --------------------------------------------------------------------------- #
class RobloxAPI:
    def __init__(self, cookie: str):
        self.cookies = {".ROBLOSECURITY": cookie}
        self.user_id: Optional[int] = None

    def authenticate(self) -> bool:
        try:
            r = rate_limited_request("GET", "https://users.roblox.com/v1/users/authenticated",
                                     cookies=self.cookies, timeout=10)
            if r.status_code == 200:
                self.user_id = r.json().get("id")
                return True
        except Exception:
            pass
        return False

    def get_transaction_totals(self, timeframe: str) -> Optional[Dict[str, int]]:
        if not self.user_id: return None
        url = f"https://economy.roblox.com/v2/users/{self.user_id}/transaction-totals"
        params = {"timeFrame": timeframe, "transactionType": "summary"}
        r = rate_limited_request("GET", url, cookies=self.cookies, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None

    def get_robux(self) -> Optional[int]:
        if not self.user_id: return None
        r = rate_limited_request("GET",
                                 f"https://economy.roblox.com/v1/users/{self.user_id}/currency",
                                 cookies=self.cookies, timeout=10)
        return r.json().get("robux") if r.status_code == 200 else None

    def get_account_status(self) -> Optional[Dict[str, Any]]:
        if not self.user_id: return None
        r = rate_limited_request("GET",
                                 f"https://users.roblox.com/v1/users/{self.user_id}",
                                 cookies=self.cookies, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return {
                "is_banned": data.get("isBanned", False),
                "username": data.get("name", "Unknown"),
                "created": data.get("created", "Unknown")
            }
        return None

# --------------------------------------------------------------------------- #
# ─────────────────────────── DISCORD NOTIFIER ──────────────────────────── #
# --------------------------------------------------------------------------- #
class DiscordNotifier:
    def __init__(self, url: str, emoji_name: str, emoji_id: str):
        self.url = url
        self.emoji = f"<:{emoji_name}:{emoji_id}>" if emoji_name and emoji_id else "Robux"

    def _send(self, embed: dict):
        if not self.url or "discord.com" not in self.url:
            return
        try:
            r = rate_limited_request("POST", self.url, json={"embeds": [embed]}, timeout=10)
            r.raise_for_status()
        except Exception:
            pass

    def transaction_change(self, changes: Dict[str, tuple]):
        fields = [
            {"name": k,
             "value": f"From {self.emoji} {abbreviate_number(old)} to {self.emoji} {abbreviate_number(new)}",
             "inline": False}
            for k, (old, new) in changes.items()
        ]
        self._send({
            "title": "Transaction Updated",
            "color": 0x00ff00,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def robux_change(self, old: int, new: int):
        self._send({
            "title": "Robux Balance Changed",
            "color": 0x00ff00 if new > old else 0xff0000,
            "fields": [
                {"name": "Before", "value": f"{self.emoji} {abbreviate_number(old)}", "inline": True},
                {"name": "After", "value": f"{self.emoji} {abbreviate_number(new)}", "inline": True}
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def account_status(self, status: dict, previous: Optional[dict] = None):
        if previous and previous == status:
            return
        color = 0xff0000 if status.get("is_banned") else 0x00ff00
        self._send({
            "title": f"Account {'BANNED' if status.get('is_banned') else 'ACTIVE'}",
            "description": "Status changed!",
            "color": color,
            "fields": [
                {"name": "User", "value": status.get("username", "Unknown"), "inline": True},
                {"name": "Created", "value": status.get("created", "Unknown"), "inline": True}
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def api_downtime(self, status: str, duration: Optional[float] = None):
        color = 0x00ff00 if status == "RECOVERED" else 0xff0000
        title = "API Recovered" if status == "RECOVERED" else "API Down"
        desc = f"Recovered after {duration:.1f}s" if duration else "Monitoring paused"
        self._send({"title": title, "description": desc, "color": color, "timestamp": datetime.now(timezone.utc).isoformat()})

# --------------------------------------------------------------------------- #
# ────────────────────────────── SETUP WIZARD ────────────────────────────── #
# --------------------------------------------------------------------------- #
class SetupWizard(QtWidgets.QDialog):
    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle("First Time Setup")
        self.setModal(True)
        self.config = Config()
        self._build_ui()

    def _build_ui(self):
        layout = QtWidgets.QFormLayout(self)
        self.webhook = QtWidgets.QLineEdit()
        self.webhook.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addRow("Discord Webhook URL:", self.webhook)

        self.cookie = QtWidgets.QLineEdit()
        self.cookie.setEchoMode(QtWidgets.QLineEdit.Password)
        layout.addRow(".ROBLOSECURITY Cookie:", self.cookie)

        self.emoji_id = QtWidgets.QLineEdit()
        layout.addRow("Emoji ID:", self.emoji_id)

        self.emoji_name = QtWidgets.QLineEdit()
        layout.addRow("Emoji Name:", self.emoji_name)

        self.interval = QtWidgets.QLineEdit("180")
        layout.addRow("Check Interval (s):", self.interval)

        self.timeframe = QtWidgets.QComboBox()
        self.timeframe.addItems(["Day", "Week", "Month", "Year"])
        layout.addRow("Timeframe:", self.timeframe)

        btn_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addRow(btn_box)

    def accept(self):
        try:
            webhook = self.webhook.text().strip()
            cookie = self.cookie.text().strip()
            if webhook:
                self.config["DISCORD_WEBHOOK_URL"] = webhook
            if cookie:
                self.config["ROBLOSECURITY"] = cookie
            self.config["DISCORD_EMOJI_ID"] = self.emoji_id.text().strip()
            self.config["DISCORD_EMOJI_NAME"] = self.emoji_name.text().strip()
            self.config["CHECK_INTERVAL"] = self.interval.text().strip() or "60"
            self.config["TOTAL_CHECKS_TYPE"] = self.timeframe.currentText()
            super().accept()
        except Exception as exc:
            QtWidgets.QMessageBox.critical(self, "Error", f"Failed to save configuration:\n{exc}")

# --------------------------------------------------------------------------- #
# ────────────────────────────── MAIN WINDOW ─────────────────────────────── #
# --------------------------------------------------------------------------- #
class MainWindow(QtWidgets.QMainWindow):
    log_signal = QtCore.pyqtSignal(str, str)
    update_label_signal = QtCore.pyqtSignal(object, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Roblox Transaction & Robux Monitor")
        self.resize(850, 620)
        self.config = Config()
        self.storage = Storage()
        self.api = RobloxAPI(self.config["ROBLOSECURITY"])
        self.notifier = DiscordNotifier(
            self.config["DISCORD_WEBHOOK_URL"],
            self.config["DISCORD_EMOJI_NAME"],
            self.config["DISCORD_EMOJI_ID"]
        )
        self.updater = AutoUpdater(self)
        self.stop_event = threading.Event()
        self.monitor_thread: Optional[threading.Thread] = None
        self.last_status: Optional[Dict[str, Any]] = None
        self.downtime_start: Optional[float] = None

        self.theme_group = QtWidgets.QActionGroup(self)
        self.dark_action = QtWidgets.QAction("Dark", self, checkable=True)
        self.light_action = QtWidgets.QAction("Light", self, checkable=True)
        for act in (self.dark_action, self.light_action):
            self.theme_group.addAction(act)
        self.theme_group.triggered.connect(self.on_theme_changed)

        self._build_ui()
        self._connect_signals()
        self.load_theme()
        self.check_first_run()

    def _connect_signals(self):
        self.log_signal.connect(self._append_log)
        self.update_label_signal.connect(lambda w, t: w.setText(t))

    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        tabs = QtWidgets.QTabWidget()
        layout.addWidget(tabs)

        # Dashboard
        dash = QtWidgets.QWidget()
        dash_layout = QtWidgets.QGridLayout(dash)
        self.lbl_user = QtWidgets.QLabel("User: -")
        self.lbl_robux = QtWidgets.QLabel("Robux: -")
        self.lbl_status = QtWidgets.QLabel("Status: -")
        self.lbl_next = QtWidgets.QLabel("Next check: -")
        for i, (label, widget) in enumerate([
            ("<b>User:</b>", self.lbl_user),
            ("<b>Robux:</b>", self.lbl_robux),
            ("<b>Account:</b>", self.lbl_status),
            ("<b>Next check:</b>", self.lbl_next)
        ]):
            dash_layout.addWidget(QtWidgets.QLabel(label), i, 0)
            dash_layout.addWidget(widget, i, 1)
        self.log_view = QtWidgets.QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet("font-family: Consolas; font-size: 10pt;")
        dash_layout.addWidget(self.log_view, 4, 0, 1, 2)
        tabs.addTab(dash, "Dashboard")

        # Config
        cfg = QtWidgets.QWidget()
        cfg_layout = QtWidgets.QFormLayout(cfg)
        self.cfg_webhook = QtWidgets.QLineEdit()
        self.cfg_webhook.setEchoMode(QtWidgets.QLineEdit.Password)
        cfg_layout.addRow("Webhook URL:", self.cfg_webhook)
        self.cfg_cookie = QtWidgets.QLineEdit()
        self.cfg_cookie.setEchoMode(QtWidgets.QLineEdit.Password)
        cfg_layout.addRow(".ROBLOSECURITY:", self.cfg_cookie)
        self.cfg_emoji_id = QtWidgets.QLineEdit()
        cfg_layout.addRow("Emoji ID:", self.cfg_emoji_id)
        self.cfg_emoji_name = QtWidgets.QLineEdit()
        cfg_layout.addRow("Emoji Name:", self.cfg_emoji_name)
        self.cfg_interval = QtWidgets.QLineEdit()
        cfg_layout.addRow("Interval (s):", self.cfg_interval)
        self.cfg_timeframe = QtWidgets.QComboBox()
        self.cfg_timeframe.addItems(["Day", "Week", "Month", "Year"])
        cfg_layout.addRow("Timeframe:", self.cfg_timeframe)
        save_btn = QtWidgets.QPushButton("Save Config")
        save_btn.clicked.connect(self.save_config)
        cfg_layout.addRow(save_btn)
        tabs.addTab(cfg, "Config")

        # Menu
        menu = self.menuBar()
        file_menu = menu.addMenu("File")
        file_menu.addAction("Check for Updates", lambda: self.updater.check_and_update(manual=True))
        file_menu.addSeparator()
        file_menu.addAction("Exit", self.close)
        view_menu = menu.addMenu("View")
        theme_menu = view_menu.addMenu("Theme")
        theme_menu.addAction(self.dark_action)
        theme_menu.addAction(self.light_action)

    def _append_log(self, msg: str, color: str = ""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        html = f'<span style="color:{color}">[{timestamp}]: {msg}</span>'
        self.log_view.appendHtml(html)

    def log(self, msg: str, color: str = ""):
        self.log_signal.emit(msg, color)

    def update_label(self, widget, text: str):
        self.update_label_signal.emit(widget, text)

    def load_theme(self):
        theme = self.config.data.get("THEME", "System")
        if theme == "Dark":
            self.dark_action.setChecked(True)
            self.apply_dark()
        elif theme == "Light":
            self.light_action.setChecked(True)
            self.apply_light()

    def on_theme_changed(self, action: QtWidgets.QAction):
        if action == self.dark_action:
            self.config["THEME"] = "Dark"
            self.apply_dark()
        elif action == self.light_action:
            self.config["THEME"] = "Light"
            self.apply_light()

    def apply_dark(self):
        self.setStyleSheet("""
            QMainWindow, QDialog, QWidget { background-color: #1e1e1e; color: #ffffff; }
            QLineEdit, QComboBox, QPlainTextEdit, QTabWidget::pane {
                background-color: #2d2d2d; color: #ffffff;
                border: 1px solid #444; border-radius: 4px; padding: 4px;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #0078d7; }
            QPushButton {
                background-color: #0078d7; color: white; border: none;
                padding: 6px 12px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #106ebe; }
            QPushButton:pressed { background-color: #005a9e; }
            QTabBar::tab { background: #2d2d2d; color: #ccc; padding: 8px 16px; margin-right: 2px; }
            QTabBar::tab:selected { background: #0078d7; color: white; }
            QTabWidget::pane { border-top: 2px solid #0078d7; }
        """)

    def apply_light(self):
        self.setStyleSheet("""
            QMainWindow, QDialog, QWidget { background-color: #f3f3f3; color: #000000; }
            QLineEdit, QComboBox, QPlainTextEdit, QTabWidget::pane {
                background-color: #ffffff; color: #000000;
                border: 1px solid #ccc; border-radius: 4px; padding: 4px;
            }
            QLineEdit:focus, QComboBox:focus { border: 1px solid #0078d7; }
            QPushButton {
                background-color: #0078d7; color: white; border: none;
                padding: 6px 12px; border-radius: 4px;
            }
            QPushButton:hover { background-color: #106ebe; }
            QTabBar::tab { background: #e0e0e0; color: #333; padding: 8px 16px; margin-right: 2px; }
            QTabBar::tab:selected { background: #0078d7; color: white; }
            QTabWidget::pane { border-top: 2px solid #0078d7; }
        """)

    def check_first_run(self):
        if not self.config["ROBLOSECURITY"]:
            wizard = SetupWizard(self)
            if wizard.exec_() != QtWidgets.QDialog.Accepted:
                QtWidgets.QMessageBox.information(self, "Info", "Setup cancelled – closing.")
                sys.exit(0)
            self.config = Config()
            self.api = RobloxAPI(self.config["ROBLOSECURITY"])
            self.notifier = DiscordNotifier(
                self.config["DISCORD_WEBHOOK_URL"],
                self.config["DISCORD_EMOJI_NAME"],
                self.config["DISCORD_EMOJI_ID"]
            )

        if not self.config["ROBLOSECURITY"].startswith("_|WARNING"):
            config_path = Config.CONFIG_FILE
            QtWidgets.QMessageBox.critical(
                self, "Invalid Cookie Format",
                f"<b>.ROBLOSECURITY cookie is invalid!</b><br><br>"
                f"It must start with <code>_&#124;WARNING</code><br><br>"
                f"<b>Current value:</b><br><code>{self.config['ROBLOSECURITY'][:50]}{'...' if len(self.config['ROBLOSECURITY']) > 50 else ''}</code><br><br>"
                f"<b>Config file location:</b><br><code>{config_path}</code>"
            )
            sys.exit(1)

        self.cfg_webhook.setText(self.config["DISCORD_WEBHOOK_URL"])
        self.cfg_cookie.setText(self.config["ROBLOSECURITY"])
        self.cfg_emoji_id.setText(self.config["DISCORD_EMOJI_ID"])
        self.cfg_emoji_name.setText(self.config["DISCORD_EMOJI_NAME"])
        self.cfg_interval.setText(self.config["CHECK_INTERVAL"])
        self.cfg_timeframe.setCurrentText(self.config["TOTAL_CHECKS_TYPE"])

        self.start_monitoring()
        self.updater.check_and_update()  # Silent background check

    def save_config(self):
        try:
            self.config["DISCORD_WEBHOOK_URL"] = self.cfg_webhook.text().strip()
            self.config["ROBLOSECURITY"] = self.cfg_cookie.text().strip()
            self.config["DISCORD_EMOJI_ID"] = self.cfg_emoji_id.text().strip()
            self.config["DISCORD_EMOJI_NAME"] = self.cfg_emoji_name.text().strip()
            self.config["CHECK_INTERVAL"] = self.cfg_interval.text().strip() or "60"
            self.config["TOTAL_CHECKS_TYPE"] = self.cfg_timeframe.currentText()
            self.api = RobloxAPI(self.config["ROBLOSECURITY"])
            self.notifier = DiscordNotifier(
                self.config["DISCORD_WEBHOOK_URL"],
                self.config["DISCORD_EMOJI_NAME"],
                self.config["DISCORD_EMOJI_ID"]
            )
            self.log("Configuration saved.", "green")
        except Exception as e:
            self.log(f"Config save error: {e}", "red")

    def start_monitoring(self):
        if not self.api.authenticate():
            self.log("Authentication failed – check cookie.", "red")
            return
        self.update_label(self.lbl_user, f"<b>{self.api.user_id}</b>")
        self.log(f"Authenticated as user ID: {self.api.user_id}", "cyan")
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

    def monitor_loop(self):
        while not self.stop_event.is_set():
            try:
                if not self._check_api():
                    self._wait()
                    continue
                self._check_transactions()
                self._check_robux()
                self._check_account_status()
            except Exception as e:
                self.log(f"Unexpected error: {e}", "red")
            self._wait()

    def _check_api(self) -> bool:
        try:
            r = rate_limited_request(
                "GET", "https://users.roblox.com/v1/users/authenticated",
                cookies=self.api.cookies, timeout=10
            )
            if r.status_code == 200:
                if self.downtime_start:
                    duration = time.time() - self.downtime_start
                    self.notifier.api_downtime("RECOVERED", duration)
                    self.log(f"API recovered after {duration:.1f}s", "green")
                    self.downtime_start = None
                return True
        except Exception:
            pass
        if not self.downtime_start:
            self.downtime_start = time.time()
            self.notifier.api_downtime("STARTED")
            self.log("Roblox API unreachable – retrying...", "red")
        return False

    def _check_transactions(self):
        data = self.api.get_transaction_totals(self.config["TOTAL_CHECKS_TYPE"])
        if not data: return
        last = self.storage.load_transactions()
        changes = {k: (last.get(k, 0), v) for k, v in data.items() if v != last.get(k, 0)}
        if changes:
            for k, (o, n) in changes.items():
                self.log(f"{k}: {abbreviate_number(o)} to {abbreviate_number(n)}", "yellow")
            self.notifier.transaction_change(changes)
            self.storage.save_transactions(data)

    def _check_robux(self):
        robux = self.api.get_robux()
        if robux is None: return
        last = self.storage.load_robux()
        if robux != last:
            change = "Increased" if robux > last else "Decreased"
            self.log(f"Robux {change}: {abbreviate_number(last)} to {abbreviate_number(robux)}", "magenta")
            self.update_label(self.lbl_robux, f"<b>{abbreviate_number(robux)}</b>")
            self.notifier.robux_change(last, robux)
            self.storage.save_robux(robux)

    def _check_account_status(self):
        status = self.api.get_account_status()
        if not status: return
        if self.last_status != status:
            banned = status.get("is_banned", False)
            color = "red" if banned else "green"
            self.log(f"Account {'BANNED' if banned else 'ACTIVE'}: {status['username']}", color)
            self.update_label(self.lbl_status, f"<b>{'BANNED' if banned else 'ACTIVE'}</b>")
            self.notifier.account_status(status, self.last_status)
            self.last_status = status

    def _wait(self):
        interval = max(10, int(self.config["CHECK_INTERVAL"] or 180))
        for i in range(interval):
            if self.stop_event.is_set():
                break
            mins, secs = divmod(interval - i, 60)
            txt = f"Next check in {mins:02d}:{secs:02d}"
            self.update_label(self.lbl_next, txt)
            time.sleep(1)

    def closeEvent(self, event: QtGui.QCloseEvent):
        self.stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        event.accept()

# --------------------------------------------------------------------------- #
# ────────────────────────────────── ENTRY ────────────────────────────────── #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())