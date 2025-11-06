#!/usr/bin/env python3
"""
Roblox Transaction & Robux Monitor – Windows 11 Edition
Author: MrAndiGamesDev (Win11 UI by AI)
"""

import os
import json
import time
import signal
import threading
import requests
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path
import ctypes

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
class Configuration:
    APP_DIR = os.path.join(os.path.expanduser("~"), ".roblox_transaction_history")
    CONFIG_FILE = os.path.join(APP_DIR, "config.json")
    STORAGE_DIR = os.path.join(APP_DIR, "transaction_info")
    _LAST_CALL = 0
    DEFAULT_CONFIG = {
        "DISCORD_WEBHOOK_URL": "",
        "ROBLOSECURITY": "",
        "DISCORD_EMOJI_ID": "",
        "DISCORD_EMOJI_NAME": "",
        "CHECK_INTERVAL": "60",
        "TOTAL_CHECKS_TYPE": "Day"
    }

APP_DIR = Configuration.APP_DIR
CONFIG_FILE = Configuration.CONFIG_FILE
STORAGE_DIR = Configuration.STORAGE_DIR
DEFAULT_CONFIG = Configuration.DEFAULT_CONFIG
_last_call = Configuration._LAST_CALL

# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def rate_limited_request(*args, **kwargs):
    global _last_call
    now = time.time()
    sleep = max(0.0, 1.0 - (now - _last_call))
    if sleep:
        time.sleep(sleep)
    _last_call = time.time()
    return requests.request(*args, **kwargs)

def abbreviate_number(num: int) -> str:
    abs_num = abs(num)
    for limit, suffix in [(1e15, "Q"), (1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]:
        if abs_num >= limit:
            return f"{num/limit:.2f}{suffix}"
    return str(num)

def safe_write(path: str, data: Dict):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)

# ─────────────────────────────────────────────────────────────────────────────
# Censoring
# ─────────────────────────────────────────────────────────────────────────────
class hide_info:
    @staticmethod
    def censor(text: str, *, show_start: int = 20, show_end: int = 10) -> str:
        if not text:
            return ""
        if len(text) <= show_start + show_end:
            return "*" * len(text)
        hidden = len(text) - show_start - show_end
        return f"{text[:show_start]}{'*' * hidden}{text[-show_end:]}"

    @staticmethod
    def censor_webhook(url: str) -> str:
        return hide_info.censor(url, show_start=20, show_end=10) if url else ""

    @staticmethod
    def censor_cookie(cookie: str) -> str:
        return hide_info.censor(cookie, show_start=30, show_end=10) if cookie else ""

# ─────────────────────────────────────────────────────────────────────────────
# Update Manager
# ─────────────────────────────────────────────────────────────────────────────
class UpdateManager:
    def __init__(self):
        self.repo = "MrAndiGamesDev/Roblox-Transaction-Monitor-CTL-Edition"
        self.url = f"https://api.github.com/repos/{self.repo}/releases/latest"

    def check_for_update(self):
        try:
            r = requests.get(self.url, timeout=5)
            if r.status_code != 200:
                return None, None
            latest = r.json()
            latest_tag = latest.get("tag_name", "")
            version_file = Path(__file__).parent / "VERSION"
            current_tag = version_file.read_text().strip() if version_file.exists() else "v1.0.0"
            if latest_tag and latest_tag != current_tag:
                return latest_tag, latest.get("html_url")
        except Exception:
            pass
        return None, None

# ─────────────────────────────────────────────────────────────────────────────
# Config Manager
# ─────────────────────────────────────────────────────────────────────────────
class Config:
    def __init__(self):
        self._make_dirs()
        self.data = DEFAULT_CONFIG.copy()
        self._load()

    def _make_dirs(self):
        os.makedirs(APP_DIR, exist_ok=True, mode=0o700)
        os.makedirs(STORAGE_DIR, exist_ok=True)

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    self.data[k] = loaded.get(k, v)
            except Exception:
                pass
        self.save()

    def save(self):
        safe_write(CONFIG_FILE, self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

# ─────────────────────────────────────────────────────────────────────────────
# Storage
# ─────────────────────────────────────────────────────────────────────────────
class Storage:
    def __init__(self):
        self.trans_file = os.path.join(STORAGE_DIR, "last_transaction_data.json")
        self.robux_file = os.path.join(STORAGE_DIR, "last_robux.json")

    def load_transactions(self) -> dict:
        if not os.path.exists(self.trans_file):
            default = {k: 0 for k in [
                "salesTotal", "purchasesTotal", "affiliateSalesTotal", "groupPayoutsTotal",
                "currencyPurchasesTotal", "premiumStipendsTotal", "tradeSystemEarningsTotal",
                "tradeSystemCostsTotal", "premiumPayoutsTotal", "groupPremiumPayoutsTotal",
                "adSpendTotal", "developerExchangeTotal", "pendingRobuxTotal", "incomingRobuxTotal",
                "outgoingRobuxTotal", "individualToGroupTotal", "csAdjustmentTotal",
                "adsRevsharePayoutsTotal", "groupAdsRevsharePayoutsTotal", "subscriptionsRevshareTotal",
                "groupSubscriptionsRevshareOutgoingTotal", "publishingAdvanceRebatesTotal",
                "affiliatePayoutTotal"
            ]}
            self.save_transactions(default)
            return default
        with open(self.trans_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def save_transactions(self, data: dict):
        safe_write(self.trans_file, data)

    def load_robux(self) -> int:
        if not os.path.exists(self.robux_file):
            return 0
        try:
            with open(self.robux_file, "r", encoding="utf-8") as f:
                return json.load(f).get("robux", 0)
        except Exception:
            return 0

    def save_robux(self, robux: int):
        safe_write(self.robux_file, {"robux": robux})

# ─────────────────────────────────────────────────────────────────────────────
# Roblox API
# ─────────────────────────────────────────────────────────────────────────────
class RobloxAPI:
    def __init__(self, cookie: str):
        self.cookies = {".ROBLOSECURITY": cookie}
        self.user_id = None

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

    def get_transaction_totals(self, timeframe: str) -> Optional[dict]:
        if not self.user_id:
            return None
        url = f"https://economy.roblox.com/v2/users/{self.user_id}/transaction-totals"
        params = {"timeFrame": timeframe, "transactionType": "summary"}
        r = rate_limited_request("GET", url, cookies=self.cookies, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None

    def get_robux(self) -> Optional[int]:
        if not self.user_id:
            return None
        r = rate_limited_request("GET",
            f"https://economy.roblox.com/v1/users/{self.user_id}/currency",
            cookies=self.cookies, timeout=10)
        return r.json().get("robux") if r.status_code == 200 else None

    def get_account_status(self) -> Optional[dict]:
        if not self.user_id:
            return None
        r = rate_limited_request("GET",
            f"https://users.roblox.com/v1/users/{self.user_id}",
            cookies=self.cookies, timeout=10)
        if r.status_code != 200:
            return None
        data = r.json()
        return {
            "is_banned": data.get("isBanned", False),
            "username": data.get("name", "Unknown"),
            "created": data.get("created", "Unknown")
        }

# ─────────────────────────────────────────────────────────────────────────────
# Discord Notifier
# ─────────────────────────────────────────────────────────────────────────────
class DiscordNotifier:
    def __init__(self, url: str, emoji_name: str, emoji_id: str):
        self.url = url
        self.emoji = f"<:{emoji_name}:{emoji_id}>" if emoji_id and emoji_name else "R$"

    def send(self, embed: dict):
        if not self.url or "discord.com" not in self.url:
            return
        try:
            r = rate_limited_request("POST", self.url, json={"embeds": [embed]})
            r.raise_for_status()
        except Exception:
            pass

    def transaction_change(self, changes: dict):
        fields = [
            {"name": k,
             "value": f"From {self.emoji} {abbreviate_number(old)} to {self.emoji} {abbreviate_number(new)}",
             "inline": False}
            for k, (old, new) in changes.items()
        ]
        self.send({
            "title": "Roblox Transaction Updated",
            "color": 0x00ff00,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def robux_change(self, old: int, new: int):
        self.send({
            "title": "Robux Balance Changed",
            "color": 0x00ff00 if new > old else 0xff0000,
            "fields": [
                {"name": "Before", "value": f"{self.emoji} {abbreviate_number(old)}", "inline": True},
                {"name": "After",  "value": f"{self.emoji} {abbreviate_number(new)}",  "inline": True}
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def account_status(self, status: dict, previous: dict = None):
        if previous and previous == status:
            return
        color = 0xff0000 if status.get("is_banned") else 0x00ff00
        self.send({
            "title": f"Account {'BANNED' if status.get('is_banned') else 'ACTIVE'}",
            "description": "Status changed!",
            "color": color,
            "fields": [
                {"name": "User",    "value": status.get("username", "Unknown"), "inline": True},
                {"name": "Created", "value": status.get("created", "Unknown"),  "inline": True}
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

    def api_downtime(self, status: str, duration: float = None):
        color = 0xff0000 if status == "DOWN" else 0x00ff00
        fields = [{"name": "Duration", "value": f"{duration:.1f}s", "inline": False}] if duration else []
        self.send({
            "title": f"Roblox API {status}",
            "color": color,
            "fields": fields,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

# ─────────────────────────────────────────────────────────────────────────────
# Windows 11 GUI
# ─────────────────────────────────────────────────────────────────────────────
class RobloxMonitorWin11(ttk.Window):
    def __init__(self):
        super().__init__(themename="superhero")  # or "darkly", "cosmo"
        self.title("Roblox Transaction Monitor")
        self.geometry("900x620")
        self.minsize(800, 560)
        # Removed conflicting self.style = Style() line

        # Enable Mica on Windows 11
        try:
            import win32gui, win32con
            hwnd = self.winfo_id()
            win32gui.SetWindowLong(hwnd, win32con.GWL_EXSTYLE,
                                   win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) | win32con.WS_EX_APPWINDOW)
            self.update_idletasks()
            # Apply Mica
            import ctypes
            from ctypes import wintypes
            DWMWA_MICA = 1028
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_MICA, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
        except:
            pass

        self.cfg = Config()
        self.storage = Storage()
        self.api = RobloxAPI(self.cfg["ROBLOSECURITY"])
        self.notifier = DiscordNotifier(
            self.cfg["DISCORD_WEBHOOK_URL"],
            self.cfg["DISCORD_EMOJI_NAME"],
            self.cfg["DISCORD_EMOJI_ID"]
        )

        self.monitor_thread = None
        self.stop_event = threading.Event()
        self.downtime_start = None
        self.last_status = None
        self.user_id = None

        self.setup_ui()
        self.check_first_run()
        self.check_update()

    def setup_ui(self):
        # Header
        header = ttk.Frame(self, bootstyle="primary")
        header.pack(fill=X, padx=20, pady=(20, 10))
        ttk.Label(header, text="Roblox Monitor", font=("-size", 18, "-weight", "bold")).pack(side=LEFT)
        ttk.Label(header, text="v1.0", font=("-size", 10)).pack(side=RIGHT, pady=5)

        # Main container
        container = ttk.Frame(self)
        container.pack(fill=BOTH, expand=True, padx=20, pady=10)

        # Sidebar
        sidebar = ttk.Frame(container, width=220, bootstyle="secondary")
        sidebar.pack(side=LEFT, fill=Y, padx=(0, 15))
        sidebar.pack_propagate(False)

        # Menu buttons
        menu_items = [
            ("Monitor", "home"),
            ("Logs", "list-alt"),
            ("Settings", "gear"),
        ]
        self.menu_vars = {}
        for text, icon in menu_items:
            var = ttk.StringVar(value="Monitor" if text == "Monitor" else "")
            self.menu_vars[text] = var
            btn = ttk.Radiobutton(
                sidebar, text=f"  {text}", variable=var, value=text,
                bootstyle="toolbutton", style="Sidebar.TButton"
            )
            btn.pack(fill=X, pady=2, padx=10)

        # Main content
        self.content = ttk.Frame(container)
        self.content.pack(side=RIGHT, fill=BOTH, expand=True)

        self.pages = {}
        self.create_monitor_page()
        self.create_logs_page()

        # Bind menu
        for name in self.menu_vars:
            self.menu_vars[name].trace_add("write", self.switch_page)

        # Status bar
        self.status_var = ttk.StringVar(value="Ready")
        status = ttk.Label(self, textvariable=self.status_var, bootstyle="inverse-secondary")
        status.pack(side=BOTTOM, fill=X)

    def create_monitor_page(self):
        page = ttk.Frame(self.content)
        self.pages["Monitor"] = page

        # Info cards
        info_frame = ttk.Label(page, text=" Account Info", padding=15)
        info_frame.pack(fill=X, pady=10)

        self.info_labels = {}
        items = [
            ("Username", "N/A"),
            ("User ID", "N/A"),
            ("Robux", "0"),
            ("Status", "Unknown"),
            ("Created", "N/A")
        ]
        for i, (lbl, default) in enumerate(items):
            row = ttk.Frame(info_frame)
            row.pack(fill=X, pady=4)
            ttk.Label(row, text=f"{lbl}:", width=15).pack(side=LEFT)
            val = ttk.StringVar(value=default)
            label = ttk.Label(row, textvariable=val, font=("-weight", "bold"))
            label.pack(side=LEFT, padx=10)
            self.info_labels[lbl] = val

        # Control buttons
        btn_frame = ttk.Frame(page)
        btn_frame.pack(fill=X, pady=15)

        self.start_btn = ttk.Button(btn_frame, text="Start Monitoring", bootstyle="success", command=self.start_monitoring)
        self.start_btn.pack(side=LEFT, padx=5)

        self.stop_btn = ttk.Button(btn_frame, text="Stop", bootstyle="danger", command=self.stop_monitoring, state=DISABLED)
        self.stop_btn.pack(side=LEFT, padx=5)

        # Config summary
        summary = ttk.Label(page, text=" Configuration", padding=15)
        summary.pack(fill=BOTH, expand=True, pady=10)
        self.summary_text = ttk.Text(summary, height=8, font=("Consolas", 9))
        self.summary_text.pack(fill=BOTH, expand=True)
        self.update_summary()

    def create_logs_page(self):
        page = ttk.Frame(self.content)
        self.pages["Logs"] = page

        log_frame = ttk.Frame(page)
        log_frame.pack(fill=BOTH, expand=True, padx=10, pady=10)

        self.log_text = ttk.Text(log_frame, font=("Consolas", 9))
        scroll = ttk.Scrollbar(log_frame, orient=VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)

    def switch_page(self, *args):
        selected = next((k for k, v in self.menu_vars.items() if v.get() == k), "Monitor")
        for name, page in self.pages.items():
            page.pack_forget()
        self.pages[selected].pack(fill=BOTH, expand=True)
        if selected == "Settings":
            self.open_settings()

    def log(self, message: str, color: str = "black"):
        colors = {"green": "#00ff00", "red": "#ff4444", "yellow": "#ffff00", "magenta": "#ff00ff", "orange": "#ff8800", "blue": "#4488ff"}
        self.log_text.insert(END, f"[{datetime.now().strftime('%H:%M:%S')}] {message}\n")
        self.log_text.tag_add(color, "end-2l", "end-1c")
        self.log_text.tag_config(color, foreground=colors.get(color, color))
        self.log_text.see(END)

    def update_summary(self):
        self.summary_text.delete(1.0, END)
        lines = [
            f"Webhook: {hide_info.censor_webhook(self.cfg['DISCORD_WEBHOOK_URL'])}",
            f"Cookie: {hide_info.censor_cookie(self.cfg['ROBLOSECURITY'])}",
            f"Emoji: {self.cfg['DISCORD_EMOJI_NAME']}:{self.cfg['DISCORD_EMOJI_ID']}",
            f"Interval: {self.cfg['CHECK_INTERVAL']}s",
            f"Timeframe: {self.cfg['TOTAL_CHECKS_TYPE']}"
        ]
        self.summary_text.insert(END, "\n".join(lines))

    def check_first_run(self):
        if not self.cfg["ROBLOSECURITY"]:
            self.menu_vars["Settings"].set("Settings")
            self.switch_page()
            self.after(100, self.open_settings)

    def check_update(self):
        mgr = UpdateManager()
        tag, url = mgr.check_for_update()
        if tag:
            self.log(f"Update available: {tag}", "orange")
            self.log(f"Download: {url}", "blue")

    def open_settings(self, first_run=False):
        win = ttk.Toplevel(self)
        win.title("Settings")
        win.geometry("560x460")
        win.transient(self)
        win.grab_set()

        frame = ttk.Frame(win, padding=25)
        frame.pack(fill=BOTH, expand=True)

        entries = {}
        fields = [
            ("Discord Webhook URL", "DISCORD_WEBHOOK_URL", True),
            (".ROBLOSECURITY Cookie", "ROBLOSECURITY", True),
            ("Emoji ID", "DISCORD_EMOJI_ID", False),
            ("Emoji Name", "DISCORD_EMOJI_NAME", False),
            ("Check Interval (seconds)", "CHECK_INTERVAL", False),
            ("Timeframe (Day/Week/Month/Year)", "TOTAL_CHECKS_TYPE", False)
        ]

        for i, (label, key, pwd) in enumerate(fields):
            ttk.Label(frame, text=f"{label}:").grid(row=i, column=0, sticky=W, pady=8)
            var = ttk.StringVar(value=self.cfg[key])
            entry = ttk.Entry(frame, textvariable=var, show="*" if pwd else "", width=40)
            entry.grid(row=i, column=1, pady=8, padx=10)
            entries[key] = var

        def save():
            for k, v in entries.items():
                self.cfg[k] = v.get().strip()
            self.api = RobloxAPI(self.cfg["ROBLOSECURITY"])
            self.notifier = DiscordNotifier(
                self.cfg["DISCORD_WEBHOOK_URL"],
                self.cfg["DISCORD_EMOJI_NAME"],
                self.cfg["DISCORD_EMOJI_ID"]
            )
            self.update_summary()
            if first_run and not self.cfg["ROBLOSECURITY"].startswith("_|WARNING"):
                ctypes.windll.user32.MessageBoxW(0, "Cookie must start with '_|WARNING'", "Invalid Cookie", 0)
                return
            win.destroy()
            self.log("Settings saved.", "green")

        ttk.Button(frame, text="Save", bootstyle="success", command=save).grid(row=len(fields), column=1, pady=20)

    def start_monitoring(self):
        if not self.cfg["ROBLOSECURITY"]:
            ctypes.windll.user32.MessageBoxW(0, "Please set .ROBLOSECURITY cookie.", "Error", 0)
            return
        if not self.cfg["ROBLOSECURITY"].startswith("_|WARNING"):
            ctypes.windll.user32.MessageBoxW(0, "Invalid cookie format.", "Error", 0)
            return

        self.start_btn.config(state=DISABLED)
        self.stop_btn.config(state=NORMAL)
        self.stop_event.clear()
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
        self.log("Monitoring started.", "green")

    def stop_monitoring(self):
        self.stop_event.set()
        self.start_btn.config(state=NORMAL)
        self.stop_btn.config(state=DISABLED)
        self.log("Monitoring stopped.", "red")

    def monitor_loop(self):
        if not self.api.authenticate():
            self.after(0, lambda: ctypes.windll.user32.MessageBoxW(0, "Invalid cookie.", "Auth Failed", 0))
            self.after(0, self.stop_monitoring)
            return

        self.user_id = self.api.user_id
        self.after(0, lambda: self.info_labels["User ID"].set(self.user_id))

        while not self.stop_event.is_set():
            try:
                if not self.check_api():
                    time.sleep(5)
                    continue
                self.check_transactions()
                self.check_robux()
                self.check_account_status()
            except Exception as e:
                self.after(0, lambda: self.log(f"Error: {e}", "red"))

            interval = max(10, int(self.cfg["CHECK_INTERVAL"] or 60))
            for i in range(interval):
                if self.stop_event.is_set():
                    break
                mins, secs = divmod(interval - i, 60)
                self.after(0, lambda m=mins, s=secs: self.status_var.set(f"Next check in {m:02d}:{s:02d}"))
                time.sleep(1)

        self.after(0, lambda: self.status_var.set("Stopped"))

    def check_api(self) -> bool:
        try:
            r = rate_limited_request("GET", "https://users.roblox.com/v1/users/authenticated",
                                    cookies=self.api.cookies, timeout=10)
            if r.status_code == 200:
                if self.downtime_start:
                    dur = time.time() - self.downtime_start
                    self.notifier.api_downtime("UP", dur)
                    self.after(0, lambda: self.log(f"API recovered after {dur:.1f}s", "green"))
                    self.downtime_start = None
                return True
        except:
            pass

        if not self.downtime_start:
            self.downtime_start = time.time()
            self.notifier.api_downtime("DOWN")
            self.after(0, lambda: self.log("API down. Retrying...", "red"))
        return False

    def check_transactions(self):
        data = self.api.get_transaction_totals(self.cfg["TOTAL_CHECKS_TYPE"])
        if not data: return
        last = self.storage.load_transactions()
        changes = {k: (last.get(k, 0), v) for k, v in data.items() if v != last.get(k, 0)}
        if changes:
            msg = "\n".join(f"{k}: {abbreviate_number(o)} to {abbreviate_number(n)}" for k, (o, n) in changes.items())
            self.after(0, lambda: self.log(f"Transactions:\n{msg}", "yellow"))
            self.notifier.transaction_change(changes)
            self.storage.save_transactions(data)

    def check_robux(self):
        robux = self.api.get_robux()
        if robux is None: return
        last = self.storage.load_robux()
        if robux != last:
            change = "Increased" if robux > last else "Decreased"
            self.after(0, lambda: self.log(f"Robux {change}: {abbreviate_number(last)} to {abbreviate_number(robux)}", "magenta"))
            self.after(0, lambda: self.info_labels["Robux"].set(abbreviate_number(robux)))
            self.notifier.robux_change(last, robux)
            self.storage.save_robux(robux)

    def check_account_status(self):
        status = self.api.get_account_status()
        if not status: return
        username = status.get("username")
        banned = status.get("is_banned")
        created = status.get("created", "")[:10]

        self.after(0, lambda: self.info_labels["Username"].set(username))
        self.after(0, lambda: self.info_labels["Created"].set(created))
        self.after(0, lambda: self.info_labels["Status"].set("BANNED" if banned else "ACTIVE"))

        if self.last_status != status:
            col = "red" if banned else "green"
            self.after(0, lambda: self.log(f"Account {'BANNED' if banned else 'ACTIVE'}: {username}", col))
            self.notifier.account_status(status, self.last_status)
            self.last_status = status

if __name__ == "__main__":
    signal.signal(signal.SIGINT, lambda s, f: None)
    app = RobloxMonitorWin11()
    app.mainloop()