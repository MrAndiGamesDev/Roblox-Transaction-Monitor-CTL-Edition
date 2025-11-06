#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Roblox Transaction & Robux Monitor – Native Windows UI (WinUI 3 via pythonnet)
Author: MrAndiGamesDev (2025 WinUI 3 edition)
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

class AutoUpdater:
    def __init__(self, log_func):
        self.log = log_func
        self.current_version = self._get_current_version()
        self.download_url = None
        self.asset_name = None
        self.temp_path = None

    def _get_current_version(self) -> str:
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
                    self.log("Checking for updates...")

                r = requests.get(GITHUB_API, timeout=10)
                if r.status_code != 200:
                    if manual:
                        self.log("GitHub API unreachable.", "red")
                    return

                data = r.json()
                latest = data["tag_name"].lstrip("v")

                if self._compare_versions(latest, self.current_version) <= 0:
                    if manual:
                        self.log("You are up to date.", "green")
                    return

                asset = next((a for a in data["assets"] if a["name"] == ASSET_WINDOWS), None)
                if not asset:
                    self.log("No Windows update found.", "red")
                    return

                self.download_url = asset["browser_download_url"]
                self.asset_name = asset["name"]
                self.log(f"Update found: v{latest} ({self.asset_name})")
                self._download_and_install()
            except Exception as e:
                if manual:
                    self.log(f"Update check failed: {e}", "red")

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
            fd, self.temp_path = tempfile.mkstemp(suffix=".exe")
            os.close(fd)

            self.log("Downloading update...")
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
                        if total:
                            percent = int(100 * downloaded / total)
                            self.log(f"Downloading: {percent}%")

            self.log("Download complete. Installing...")

            current_exe = sys.executable
            backup_exe = current_exe + ".backup"

            if os.path.exists(backup_exe):
                os.remove(backup_exe)
            shutil.move(current_exe, backup_exe)
            shutil.move(self.temp_path, current_exe)
            os.chmod(current_exe, 0o755)

            self.log("Update installed. Restarting...")
            time.sleep(1.5)
            subprocess.Popen([current_exe])
            os._exit(0)

        except Exception as e:
            self.log(f"Update failed: {e}", "red")
            backup_exe = sys.executable + ".backup"
            if os.path.exists(backup_exe):
                shutil.move(backup_exe, sys.executable)


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
            {
                "name": k,
                "value": f"From {self.emoji} {abbreviate_number(old)} to {self.emoji} {abbreviate_number(new)}",
                "inline": False
            }
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
        self._send({"title": title, "description": desc, "color": color,
                    "timestamp": datetime.now(timezone.utc).isoformat()})


# --------------------------------------------------------------------------- #
# ──────────────────────── WINUI 3 + pythonnet (2025) ───────────────────── #
# --------------------------------------------------------------------------- #
try:
    import clr
    clr.AddReference("System.Runtime")
    clr.AddReference("System.Collections")
    clr.AddReference("Microsoft.UI.Xaml")
    clr.AddReference("Microsoft.UI.Xaml.Hosting")
    clr.AddReference("Microsoft.UI.Xaml.Controls")
    clr.AddReference("Microsoft.UI.Dispatching")
    from Microsoft.UI.Xaml import Application, Window, Thickness
    from Microsoft.UI.Xaml.Controls import (
        StackPanel, TextBlock, TextBox, Button, ComboBox, ComboBoxItem,
        ScrollViewer, ListView, ListViewItem, Flyout, MenuFlyout, MenuFlyoutItem
    )
    from Microsoft.UI.Xaml.Hosting import WindowsXamlManager
    from Microsoft.UI.Dispatching import DispatcherQueueController
    from Microsoft.UI import Colors
    WINUI_AVAILABLE = True
except Exception as e:
    WINUI_AVAILABLE = False
    print(f"WinUI 3 not available: {e}")
    sys.exit(1)

class MainWindow:
    def __init__(self):
        self.config = Config()
        self.storage = Storage()
        self.api = RobloxAPI(self.config["ROBLOSECURITY"])
        self.notifier = DiscordNotifier(
            self.config["DISCORD_WEBHOOK_URL"],
            self.config["DISCORD_EMOJI_NAME"],
            self.config["DISCORD_EMOJI_ID"]
        )
        self.updater = AutoUpdater(self.log)
        self.stop_event = threading.Event()
        self.monitor_thread: Optional[threading.Thread] = None
        self.last_status: Optional[Dict[str, Any]] = None
        self.downtime_start: Optional[float] = None
        self._start_time = 0.0

        # WinUI setup
        self.dispatcher = DispatcherQueueController.CreateOnCurrentThread()
        WindowsXamlManager.InitializeForCurrentThread()
        self.app = Application.Start(lambda _: None)
        self.window = Window()
        self.window.Title = "Roblox Transaction & Robux Monitor"
        self.window.SetTitleBar(None)

        # Root panel
        root = StackPanel()
        root.Margin = Thickness(16)
        root.Spacing = 12

        # Status labels
        self.lbl_user = TextBlock()
        self.lbl_user.Text = "User: -"
        self.lbl_robux = TextBlock()
        self.lbl_robux.Text = "Robux: -"
        self.lbl_status = TextBlock()
        self.lbl_status.Text = "Status: -"
        self.lbl_next = TextBlock()
        self.lbl_next.Text = "Next check: -"

        for lbl in [self.lbl_user, self.lbl_robux, self.lbl_status, self.lbl_next]:
            lbl.FontSize = 14
            root.Children.Append(lbl)

        # Log viewer
        self.log_list = ListView()
        self.log_list.Height = 400
        scroll = ScrollViewer()
        scroll.Content = self.log_list
        root.Children.Append(scroll)

        # Buttons
        btn_update = Button()
        btn_update.Content = "Check Update"
        btn_update.Click += lambda s, e: self.updater.check_and_update(manual=True)

        btn_config = Button()
        btn_config.Content = "Config"
        btn_config.Click += lambda s, e: self.show_config_flyout(btn_config)

        btn_exit = Button()
        btn_exit.Content = "Exit"
        btn_exit.Click += lambda s, e: self.close()

        btn_panel = StackPanel()
        btn_panel.Orientation = 0  # Horizontal
        btn_panel.Spacing = 8
        btn_panel.Children.Append(btn_update)
        btn_panel.Children.Append(btn_config)
        btn_panel.Children.Append(btn_exit)
        root.Children.Append(btn_panel)

        self.window.Content = root
        self.window.Activate()

        # Start monitoring
        threading.Thread(target=self.check_first_run, daemon=True).start()

    def log(self, msg: str, color: str = ""):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        item = ListViewItem()
        item.Content = line
        self.log_list.Items.Append(item)
        # Auto-scroll
        if self.log_list.Items.Count > 0:
            self.log_list.ScrollIntoView(self.log_list.Items[self.log_list.Items.Count - 1])

    def update_label(self, lbl, text: str):
        lbl.Text = text

    def show_config_flyout(self, button):
        flyout = Flyout()

        panel = StackPanel()
        panel.Spacing = 8
        panel.Margin = Thickness(12)

        # Helper to create field
        def add_field(label_text, key, is_password=False):
            tb = TextBlock()
            tb.Text = label_text
            panel.Children.Append(tb)
            box = TextBox()
            box.Text = self.config[key]
            box.IsPassword = is_password
            box.Tag = key
            panel.Children.Append(box)
            return box

        webhook_box = add_field("Discord Webhook URL:", "DISCORD_WEBHOOK_URL")
        cookie_box = add_field(".ROBLOSECURITY Cookie:", "ROBLOSECURITY", True)
        emoji_id_box = add_field("Emoji ID:", "DISCORD_EMOJI_ID")
        emoji_name_box = add_field("Emoji Name:", "DISCORD_EMOJI_NAME")
        interval_box = add_field("Check Interval (seconds):", "CHECK_INTERVAL")
        
        timeframe_combo = ComboBox()
        timeframe_combo.Header = "Timeframe:"
        for opt in ["Day", "Week", "Month", "Year"]:
            item = ComboBoxItem()
            item.Content = opt
            item.IsSelected = (opt == self.config["TOTAL_CHECKS_TYPE"])
            timeframe_combo.Items.Append(item)
        panel.Children.Append(timeframe_combo)

        save_btn = Button()
        save_btn.Content = "Save"
        save_btn.Click += lambda s, e: self.save_config_from_flyout(
            webhook_box, cookie_box, emoji_id_box, emoji_name_box,
            interval_box, timeframe_combo, flyout
        )
        panel.Children.Append(save_btn)

        flyout.Content = panel
        flyout.ShowAt(button)

    def save_config_from_flyout(self, webhook_box, cookie_box, emoji_id_box, emoji_name_box,
                                interval_box, timeframe_combo, flyout):
        self.config["DISCORD_WEBHOOK_URL"] = webhook_box.Text
        self.config["ROBLOSECURITY"] = cookie_box.Text
        self.config["DISCORD_EMOJI_ID"] = emoji_id_box.Text
        self.config["DISCORD_EMOJI_NAME"] = emoji_name_box.Text
        self.config["CHECK_INTERVAL"] = interval_box.Text or "180"
        self.config["TOTAL_CHECKS_TYPE"] = next(
            (item.Content for item in timeframe_combo.Items if item.IsSelected), "Day"
        )

        self.api = RobloxAPI(self.config["ROBLOSECURITY"])
        self.notifier = DiscordNotifier(
            self.config["DISCORD_WEBHOOK_URL"],
            self.config["DISCORD_EMOJI_NAME"],
            self.config["DISCORD_EMOJI_ID"]
        )
        self.log("Configuration saved.", "green")
        flyout.Hide()

    def check_first_run(self):
        time.sleep(0.5)  # Let UI settle
        if not self.config["ROBLOSECURITY"]:
            self.log("First run – opening setup...", "orange")
            # Reuse config flyout logic
            dummy_btn = Button()
            self.show_config_flyout(dummy_btn)
            self.config = Config()
            self.api = RobloxAPI(self.config["ROBLOSECURITY"])
            self.notifier = DiscordNotifier(
                self.config["DISCORD_WEBHOOK_URL"],
                self.config["DISCORD_EMOJI_NAME"],
                self.config["DISCORD_EMOJI_ID"]
            )

        if not self.config["ROBLOSECURITY"].startswith("_|WARNING"):
            from Microsoft.UI.Xaml.Controls import ContentDialog, ContentDialogButton
            dialog = ContentDialog()
            dialog.Title = "Invalid Cookie"
            dialog.Content = (
                f".ROBLOSECURITY must start with \"_|WARNING\"\n\n"
                f"Current: {self.config['ROBLOSECURITY'][:50]}{'...' if len(self.config['ROBLOSECURITY']) > 50 else ''}\n\n"
                f"Config: {Config.CONFIG_FILE}"
            )
            dialog.CloseButtonText = "Exit"
            dialog.ShowAsync()
            sys.exit(1)

        self.start_monitoring()
        self.updater.check_and_update()

    def start_monitoring(self):
        if not self.api.authenticate():
            self.log("Authentication failed – check cookie.", "red")
            return
        self.update_label(self.lbl_user, f"User: {self.api.user_id}")
        self.log(f"Authenticated as user ID: {self.api.user_id}")
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()

        # Timer via Dispatcher
        from System import TimeSpan
        timer = self.dispatcher.CreateTimer()
        timer.Interval = TimeSpan.FromSeconds(1)
        timer.Tick += lambda s, e: self._timer_tick()
        timer.Start()

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
                cookies=self.api.cookies, timeout=10)
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
                self.log(f"{k}: {abbreviate_number(o)} to {abbreviate_number(n)}")
            self.notifier.transaction_change(changes)
            self.storage.save_transactions(data)

    def _check_robux(self):
        robux = self.api.get_robux()
        if robux is None: return
        last = self.storage.load_robux()
        if robux != last:
            change = "Increased" if robux > last else "Decreased"
            self.log(f"Robux {change}: {abbreviate_number(last)} to {abbreviate_number(robux)}")
            self.update_label(self.lbl_robux, f"Robux: {abbreviate_number(robux)}")
            self.notifier.robux_change(last, robux)
            self.storage.save_robux(robux)

    def _check_account_status(self):
        status = self.api.get_account_status()
        if not status: return
        if self.last_status != status:
            banned = status.get("is_banned", False)
            color = "red" if banned else "green"
            self.log(f"Account {'BANNED' if banned else 'ACTIVE'}: {status['username']}", color)
            self.update_label(self.lbl_status, f"Status: {'BANNED' if banned else 'ACTIVE'}")
            self.notifier.account_status(status, self.last_status)
            self.last_status = status

    def _timer_tick(self):
        interval = max(10, int(self.config.get("CHECK_INTERVAL", 180)))
        remaining = self._remaining_seconds()
        mins, secs = divmod(remaining, 60)
        self.update_label(self.lbl_next, f"Next check in {mins:02d}:{secs:02d}")

    def _wait(self):
        interval = max(10, int(self.config.get("CHECK_INTERVAL", 180)))
        self._start_time = time.time()
        for _ in range(interval):
            if self.stop_event.is_set():
                break
            time.sleep(1)

    def _remaining_seconds(self):
        if not self._start_time:
            return 0
        elapsed = time.time() - self._start_time
        interval = max(10, int(self.config.get("CHECK_INTERVAL", 180)))
        return max(0, interval - int(elapsed))

    def close(self):
        self.stop_event.set()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        self.window.Close()


# --------------------------------------------------------------------------- #
# ────────────────────────────────── ENTRY ────────────────────────────────── #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    if not sys.platform.startswith("win"):
        print("This script requires Windows.")
        sys.exit(1)

    # Ensure WinUI 3 runtime is available (Windows 10 1809+ or Windows 11)
    try:
        app = MainWindow()
        # Keep Python alive while WinUI runs
        import time
        while not app.stop_event.is_set():
            time.sleep(0.1)
    except Exception as e:
        print(f"Failed to start WinUI: {e}")
        sys.exit(1)