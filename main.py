#!/usr/bin/env python3
"""
Roblox Transaction & Robux Monitor – GUI Edition
Author: MrAndiGamesDev (Enhanced with GUI)
Secure, real-time monitoring with beautiful Tkinter interface.
"""

import json
import time
import signal
import ctypes
import threading
import logging
import requests
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
from getpass import getpass
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path
import webbrowser

# ─────────────────────────────────────────────────────────────────────────────
# Configuration & Paths
# ─────────────────────────────────────────────────────────────────────────────
class Paths:
    APP_DIR = Path.home() / ".roblox_transaction_monitor"
    CONFIG_FILE = APP_DIR / "config.json"
    STORAGE_DIR = APP_DIR / "data"
    VERSION_FILE = Path(__file__).parent / "VERSION"

    @classmethod
    def ensure_dirs(cls):
        cls.APP_DIR.mkdir(mode=0o700, exist_ok=True)
        cls.STORAGE_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Logging Setup (GUI + Console)
# ─────────────────────────────────────────────────────────────────────────────
class GUILogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.formatter = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s", "%H:%M:%S")

    def emit(self, record):
        msg = self.formatter.format(record)
        self.text_widget.insert(tk.END, msg + "\n")
        self.text_widget.see(tk.END)


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def abbreviate_number(num: int) -> str:
    abs_num = abs(num)
    for limit, suffix in [(1e15, "Q"), (1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]:
        if abs_num >= limit:
            return f"{num/limit:.2f}{suffix}"
    return str(num)


def safe_write(path: Path, data: Dict):
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception as e:
        log.error(f"Failed to write {path}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Secure Input & Censoring
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limiter
# ─────────────────────────────────────────────────────────────────────────────
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


def rate_limited_request(*args, **kwargs):
    rate_limiter.wait()
    return requests.request(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Update Checker
# ─────────────────────────────────────────────────────────────────────────────
class UpdateChecker:
    REPO = "MrAndiGamesDev/Roblox-Transaction-Monitor-CTL-Edition"
    URL = f"https://api.github.com/repos/{REPO}/releases/latest"

    @staticmethod
    def get_current_version() -> str:
        try:
            return Paths.VERSION_FILE.read_text().strip()
        except Exception:
            return "v1.0.0"

    @staticmethod
    def check() -> Optional[str]:
        try:
            r = requests.get(UpdateChecker.URL, timeout=5)
            if r.status_code != 200:
                return None
            latest = r.json().get("tag_name", "")
            current = UpdateChecker.get_current_version()
            if latest and latest != current:
                return latest, r.json().get('html_url')
            return None
        except Exception:
            return None


# ─────────────────────────────────────────────────────────────────────────────
# Config & Storage
# ─────────────────────────────────────────────────────────────────────────────
class Config:
    DEFAULTS = {
        "DISCORD_WEBHOOK_URL": "",
        "ROBLOSECURITY": "",
        "DISCORD_EMOJI_ID": "",
        "DISCORD_EMOJI_NAME": "",
        "CHECK_INTERVAL": "60",
        "TOTAL_CHECKS_TYPE": "Day"
    }

    def __init__(self):
        Paths.ensure_dirs()
        self.data = self.DEFAULTS.copy()
        self.load()

    def load(self):
        if Paths.CONFIG_FILE.exists():
            try:
                loaded = json.loads(Paths.CONFIG_FILE.read_text())
                for k, v in self.DEFAULTS.items():
                    self.data[k] = loaded.get(k, v)
            except Exception:
                log.warning("Invalid config file. Using defaults.")
        self.save()

    def save(self):
        safe_write(Paths.CONFIG_FILE, self.data)

    def __getitem__(self, key): return self.data[key]
    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()


class Storage:
    TRANS_FILE = Paths.STORAGE_DIR / "transactions.json"
    ROBUX_FILE = Paths.STORAGE_DIR / "robux.json"

    @staticmethod
    def default_transactions() -> Dict:
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

    def load_transactions(self) -> Dict:
        if not self.TRANS_FILE.exists():
            data = self.default_transactions()
            self.save_transactions(data)
            return data
        try:
            return json.loads(self.TRANS_FILE.read_text())
        except:
            return self.default_transactions()

    def save_transactions(self, data: Dict):
        safe_write(self.TRANS_FILE, data)

    def load_robux(self) -> int:
        if not self.ROBUX_FILE.exists():
            return 0
        try:
            return json.loads(self.ROBUX_FILE.read_text()).get("robux", 0)
        except:
            return 0

    def save_robux(self, robux: int):
        safe_write(self.ROBUX_FILE, {"robux": robux})


# ─────────────────────────────────────────────────────────────────────────────
# Roblox API
# ─────────────────────────────────────────────────────────────────────────────
class RobloxAPI:
    def __init__(self, cookie: str):
        self.cookies = {".ROBLOSECURITY": cookie}
        self.user_id: Optional[int] = None

    def _get(self, url: str) -> Optional[Dict]:
        try:
            r = rate_limited_request("GET", url, cookies=self.cookies, timeout=10)
            return r.json() if r.status_code == 200 else None
        except Exception as e:
            log.debug(f"API request failed: {e}")
            return None

    def authenticate(self) -> bool:
        data = self._get("https://users.roblox.com/v1/users/authenticated")
        if data and (uid := data.get("id")):
            self.user_id = uid
            return True
        return False

    def get_transaction_totals(self, timeframe: str) -> Optional[Dict]:
        if not self.user_id: return None
        url = f"https://economy.roblox.com/v2/users/{self.user_id}/transaction-totals"
        params = {"timeFrame": timeframe, "transactionType": "summary"}
        r = rate_limited_request("GET", url, cookies=self.cookies, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None

    def get_robux(self) -> Optional[int]:
        if not self.user_id: return None
        data = self._get(f"https://economy.roblox.com/v1/users/{self.user_id}/currency")
        return data.get("robux") if data else None

    def get_account_status(self) -> Optional[Dict]:
        if not self.user_id: return None
        data = self._get(f"https://users.roblox.com/v1/users/{self.user_id}")
        if not data: return None
        return {
            "is_banned": data.get("isBanned", False),
            "username": data.get("name", "Unknown"),
            "created": data.get("created", "Unknown")
        }


# ─────────────────────────────────────────────────────────────────────────────
# Discord Notifier
# ─────────────────────────────────────────────────────────────────────────────
class DiscordNotifier:
    def __init__(self, webhook_url: str, emoji_name: str, emoji_id: str):
        self.url = webhook_url
        self.emoji = f"<:{emoji_name}:{emoji_id}>" if emoji_id else ""

    def _send(self, payload: Dict):
        if not self.url or "discord.com" not in self.url:
            return
        try:
            rate_limited_request("POST", self.url, json=payload, timeout=10)
        except Exception:
            pass

    def embed(self, title: str, color: int, fields: list):
        embed = {"title": title, "color": color, "fields": fields}
        embed["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._send({"embeds": [embed]})

    def transaction_change(self, changes: Dict[str, tuple]):
        fields = [
            {"name": k, "value": f"From {self.emoji} {abbreviate_number(old)} → {self.emoji} {abbreviate_number(new)}", "inline": False}
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
        if previous == status: return
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


# ─────────────────────────────────────────────────────────────────────────────
# GUI Monitor
# ─────────────────────────────────────────────────────────────────────────────
class GUIMonitor:
    def __init__(self, root):
        self.root = root
        self.config = Config()
        self.storage = Storage()
        self.api = RobloxAPI(self.config["ROBLOSECURITY"])
        self.notifier = DiscordNotifier(
            self.config["DISCORD_WEBHOOK_URL"],
            self.config["DISCORD_EMOJI_NAME"],
            self.config["DISCORD_EMOJI_ID"]
        )
        self.monitoring = False
        self.thread = None
        self.stop_event = threading.Event()
        self.downtime_start = None
        self.last_status = None

        self.setup_ui()
        self.check_update()
        self.validate_and_start()

    def setup_ui(self):
        self.root.title("Roblox Transaction & Robux Monitor (GUI)")
        self.root.geometry("800x600")
        self.root.configure(bg="#1e1e1e")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=6, font=("Segoe UI", 10))
        style.configure("TLabel", background="#1e1e1e", foreground="#ffffff", font=("Segoe UI", 9))

        # Header
        header = tk.Frame(self.root, bg="#2d2d2d", height=50)
        header.pack(fill=tk.X, padx=10, pady=5)
        header.pack_propagate(False)

        tk.Label(header, text="Roblox Monitor", font=("Segoe UI", 14, "bold"), bg="#2d2d2d", fg="#00ff00").pack(side=tk.LEFT, padx=10)
        self.update_label = tk.Label(header, text="", bg="#2d2d2d", fg="#ffff00", font=("Segoe UI", 9))
        self.update_label.pack(side=tk.RIGHT, padx=10)

        # Status Bar
        status_frame = tk.Frame(self.root, bg="#252525")
        status_frame.pack(fill=tk.X, padx=10, pady=5)

        self.status_var = tk.StringVar(value="Status: Idle")
        self.api_var = tk.StringVar(value="API: —")
        self.timer_var = tk.StringVar(value="Next check: —")

        tk.Label(status_frame, textvariable=self.status_var, bg="#252525", fg="#00ff00").pack(side=tk.LEFT, padx=10)
        tk.Label(status_frame, textvariable=self.api_var, bg="#252525", fg="#00ff00").pack(side=tk.LEFT, padx=10)
        tk.Label(status_frame, textvariable=self.timer_var, bg="#252525", fg="#00bfff").pack(side=tk.RIGHT, padx=10)

        # Stats
        stats_frame = tk.Frame(self.root, bg="#1e1e1e")
        stats_frame.pack(pady=10)

        self.robux_label = tk.Label(stats_frame, text="Robux: —", font=("Segoe UI", 12, "bold"), bg="#1e1e1e", fg="#00ff00")
        self.sales_label = tk.Label(stats_frame, text="Sales: —", font=("Segoe UI", 12, "bold"), bg="#1e1e1e", fg="#00ff88")
        self.robux_label.pack(side=tk.LEFT, padx=30)
        self.sales_label.pack(side=tk.LEFT, padx=30)

        # Controls
        control_frame = tk.Frame(self.root, bg="#1e1e1e")
        control_frame.pack(pady=10)

        self.start_btn = ttk.Button(control_frame, text="Start Monitoring", command=self.toggle_monitoring)
        self.config_btn = ttk.Button(control_frame, text="Edit Config", command=self.edit_config)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        self.config_btn.pack(side=tk.LEFT, padx=5)

        # Log
        log_frame = tk.LabelFrame(self.root, text="Live Log", bg="#1e1e1e", fg="#ffffff")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, bg="#0f0f0f", fg="#00ff00", font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Setup logging
        global log
        log = logging.getLogger()
        log.setLevel(logging.INFO)
        handler = GUILogHandler(self.log_text)
        log.addHandler(handler)

    def check_update(self):
        update = UpdateChecker.check()
        if update:
            latest, url = update
            self.update_label.config(text=f"Update: {latest} → Download")
            self.update_label.bind("<Button-1>", lambda e: webbrowser.open(url))

    def validate_and_start(self):
        if not self.config["ROBLOSECURITY"]:
            self.edit_config(first_run=True)
        elif not self.config["ROBLOSECURITY"].startswith("_|WARNING"):
            messagebox.showerror("Invalid Cookie", "Cookie must start with '_|WARNING'")
            self.edit_config()

    def toggle_monitoring(self):
        if not self.monitoring:
            if not self.api.authenticate():
                messagebox.showerror("Auth Failed", "Invalid or expired .ROBLOSECURITY cookie.")
                return
            self.monitoring = True
            self.stop_event.clear()
            self.thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.thread.start()
            self.start_btn.config(text="Stop Monitoring")
            self.status_var.set("Status: Monitoring")
            log.info("Monitoring started.")
        else:
            self.stop_event.set()
            self.monitoring = False
            self.start_btn.config(text="Start Monitoring")
            self.status_var.set("Status: Stopped")
            log.info("Monitoring stopped.")

    def monitor_loop(self):
        while not self.stop_event.is_set():
            try:
                if not self._check_api_health():
                    self._wait()
                    continue
                self._check_transactions()
                self._check_robux()
                self._check_account_status()
            except Exception as e:
                log.error(f"Error: {e}")
            self._wait()

    def _check_api_health(self) -> bool:
        try:
            r = rate_limited_request("GET", "https://users.roblox.com/v1/users/authenticated", cookies=self.api.cookies, timeout=10)
            if r.status_code == 200:
                if self.downtime_start:
                    duration = time.time() - self.downtime_start
                    self.notifier.api_downtime("RECOVERED", duration)
                    log.info(f"API recovered after {duration:.1f}s")
                    self.root.after(0, lambda: self.api_var.set("API: OK"))
                    self.downtime_start = None
                return True
        except:
            pass
        if not self.downtime_start:
            self.downtime_start = time.time()
            self.notifier.api_downtime("DOWN")
            log.warning("Roblox API unreachable.")
            self.root.after(0, lambda: self.api_var.set("API: DOWN"))
        return False

    def _check_transactions(self):
        data = self.api.get_transaction_totals(self.config["TOTAL_CHECKS_TYPE"])
        if not data: return
        last = self.storage.load_transactions()
        changes = {k: (last.get(k, 0), v) for k, v in data.items() if v != last.get(k, 0)}
        if changes:
            log.info("Transaction changes:")
            for k, (o, n) in changes.items():
                log.info(f"  {k}: {abbreviate_number(o)} → {abbreviate_number(n)}")
            self.notifier.transaction_change(changes)
            self.storage.save_transactions(data)
            self.root.after(0, lambda: self.sales_label.config(text=f"Sales: {abbreviate_number(data.get('salesTotal', 0))}"))

    def _check_robux(self):
        robux = self.api.get_robux()
        if robux is None: return
        last = self.storage.load_robux()
        if robux != last:
            change = "Increased" if robux > last else "Decreased"
            log.info(f"Robux {change}: {abbreviate_number(last)} → {abbreviate_number(robux)}")
            self.notifier.robux_change(last, robux)
            self.storage.save_robux(robux)
            self.root.after(0, lambda: self.robux_label.config(text=f"Robux: {abbreviate_number(robux)}"))

    def _check_account_status(self):
        status = self.api.get_account_status()
        if not status: return
        if self.last_status != status:
            banned = status["is_banned"]
            log.info(f"Account {'BANNED' if banned else 'ACTIVE'}: {status['username']}")
            self.notifier.account_status(status, self.last_status)
            self.last_status = status

    def _wait(self):
        interval = max(10, int(self.config["CHECK_INTERVAL"] or 60))
        for i in range(interval, 0, -1):
            if self.stop_event.is_set(): break
            mins, secs = divmod(i, 60)
            self.root.after(0, lambda m=mins, s=secs: self.timer_var.set(f"Next check: {m:02d}:{s:02d}"))
            time.sleep(1)
        self.root.after(0, lambda: self.timer_var.set("Next check: —"))

    def edit_config(self, first_run=False):
        ConfigEditor(self.root, self.config, callback=lambda: self.validate_and_start() if first_run else None)


# ─────────────────────────────────────────────────────────────────────────────
# Config Editor Window
# ─────────────────────────────────────────────────────────────────────────────
class ConfigEditor:
    def __init__(self, parent, config: Config, callback=None):
        self.config = config
        self.callback = callback
        self.window = tk.Toplevel(parent)
        self.window.title("Edit Configuration")
        self.window.geometry("500x400")
        self.window.configure(bg="#1e1e1e")
        self.window.transient(parent)
        self.window.grab_set()

        self.entries = {}
        fields = [
            ("Discord Webhook URL", "DISCORD_WEBHOOK_URL", True),
            (".ROBLOSECURITY Cookie", "ROBLOSECURITY", True),
            ("Emoji ID", "DISCORD_EMOJI_ID", False),
            ("Emoji Name", "DISCORD_EMOJI_NAME", False),
            ("Check Interval (seconds)", "CHECK_INTERVAL", False),
            ("Timeframe", "TOTAL_CHECKS_TYPE", False),
        ]

        for i, (label, key, hidden) in enumerate(fields):
            tk.Label(self.window, text=label + ":", bg="#1e1e1e", fg="#ffffff").grid(row=i, column=0, sticky="w", padx=10, pady=5)
            var = tk.StringVar(value=config[key])
            entry = tk.Entry(self.window, textvariable=var, show="*" if hidden else "", width=50)
            entry.grid(row=i, column=1, padx=10, pady=5)
            self.entries[key] = var

        btn_frame = tk.Frame(self.window, bg="#1e1e1e")
        btn_frame.grid(row=len(fields), column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="Save", command=self.save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.window.destroy).pack(side=tk.LEFT, padx=5)

    def save(self):
        for key, var in self.entries.items():
            self.config[key] = var.get().strip()
        log.info("Configuration saved.")
        self.window.destroy()
        if self.callback:
            self.callback()


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    Paths.ensure_dirs()
    # High-DPI scaling
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    app = GUIMonitor(root)
    root.mainloop()


if __name__ == "__main__":
    main()