#!/usr/bin/env python3
"""
Roblox Transaction & Robux Monitor – CLI Edition
Author: MrAndiGamesDev (Refactored & Enhanced)
Secure, efficient, and user-friendly monitoring tool.
"""

import json
import time
import signal
import threading
import logging
import requests
from getpass import getpass
from datetime import datetime, timezone
from typing import Dict, Any, Optional, Callable
from pathlib import Path

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
# Logging Setup
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Terminal Colors
# ─────────────────────────────────────────────────────────────────────────────
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

    @staticmethod
    def colorize(text: str, color: str) -> str:
        return f"{color}{text}{Colors.RESET}"

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
# Rate Limiter (Thread-Safe)
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
                log.warning(Colors.colorize(f"Update available: {latest} (current: {current})", Colors.YELLOW))
                log.info(f"Download: {r.json().get('html_url')}")
            return current
        except Exception:
            return None

# ─────────────────────────────────────────────────────────────────────────────
# Configuration Manager
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
                log.warning(Colors.colorize("Invalid config file. Using defaults.", Colors.YELLOW))
        self.save()

    def save(self):
        safe_write(Paths.CONFIG_FILE, self.data)

    def __getitem__(self, key):
        return self.data[key]

    def __setitem__(self, key, value):
        self.data[key] = value
        self.save()

    def validate_cookie(self) -> bool:
        cookie = self["ROBLOSECURITY"]
        if not cookie.startswith("_|WARNING"):
            log.error(Colors.colorize("Invalid .ROBLOSECURITY cookie: must start with '_|WARNING'", Colors.RED))
            return False
        return True

    def summary(self):
        log.info(Colors.colorize("Config Summary:", Colors.CYAN))
        log.info(f"  Webhook : {SecureInput.webhook(self['DISCORD_WEBHOOK_URL'])}")
        log.info(f"  Cookie  : {SecureInput.cookie(self['ROBLOSECURITY'])}")
        log.info(f"  Emoji   : {self['DISCORD_EMOJI_NAME']}:{self['DISCORD_EMOJI_ID']}")
        log.info(f"  Interval: {self['CHECK_INTERVAL']}s")
        log.info(f"  Timeframe: {self['TOTAL_CHECKS_TYPE']}")

# ─────────────────────────────────────────────────────────────────────────────
# Storage Manager
# ─────────────────────────────────────────────────────────────────────────────
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
        except Exception:
            return self.default_transactions()

    def save_transactions(self, data: Dict):
        safe_write(self.TRANS_FILE, data)

    def load_robux(self) -> int:
        if not self.ROBUX_FILE.exists():
            return 0
        try:
            return json.loads(self.ROBUX_FILE.read_text()).get("robux", 0)
        except Exception:
            return 0

    def save_robux(self, robux: int):
        safe_write(self.ROBUX_FILE, {"robux": robux})

# ─────────────────────────────────────────────────────────────────────────────
# Roblox API Client
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
            log.info(Colors.colorize(f"Authenticated as user ID: {uid}", Colors.CYAN))
            return True
        log.error(Colors.colorize("Authentication failed.", Colors.RED))
        return False

    def get_transaction_totals(self, timeframe: str) -> Optional[Dict]:
        if not self.user_id:
            return None
        url = f"https://economy.roblox.com/v2/users/{self.user_id}/transaction-totals"
        params = {"timeFrame": timeframe, "transactionType": "summary"}
        r = rate_limited_request("GET", url, cookies=self.cookies, params=params, timeout=10)
        return r.json() if r.status_code == 200 else None

    def get_robux(self) -> Optional[int]:
        if not self.user_id:
            return None
        data = self._get(f"https://economy.roblox.com/v1/users/{self.user_id}/currency")
        return data.get("robux") if data else None

    def get_account_status(self) -> Optional[Dict]:
        if not self.user_id:
            return None
        data = self._get(f"https://users.roblox.com/v1/users/{self.user_id}")
        if not data:
            return None
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

    def embed(self, title: str, color: int, fields: list, timestamp: bool = True):
        embed = {"title": title, "color": color, "fields": fields}
        if timestamp:
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

# ─────────────────────────────────────────────────────────────────────────────
# Monitor Core
# ─────────────────────────────────────────────────────────────────────────────
class Monitor:
    def __init__(self):
        self.config = Config()
        self.storage = Storage()
        self.api = RobloxAPI(self.config["ROBLOSECURITY"])
        self.notifier = DiscordNotifier(
            self.config["DISCORD_WEBHOOK_URL"],
            self.config["DISCORD_EMOJI_NAME"],
            self.config["DISCORD_EMOJI_ID"]
        )
        self.stop_event = threading.Event()
        self.last_status: Optional[Dict] = None
        self.downtime_start: Optional[float] = None

    def start(self):
        log.info(Colors.colorize("Roblox Transaction & Robux Monitor (CLI)", Colors.BOLD + Colors.MAGENTA))
        self.config.summary()

        if not self.api.authenticate():
            log.error(Colors.colorize("Cannot start: Invalid or expired .ROBLOSECURITY cookie.", Colors.RED))
            return

        if not self.config.validate_cookie():
            return

        log.info(Colors.colorize("Monitoring started. Press Ctrl+C to stop.", Colors.GREEN))
        signal.signal(signal.SIGINT, self._signal_handler)

        while not self.stop_event.is_set():
            try:
                if not self._check_api_health():
                    self._wait()
                    continue
                self._check_transactions()
                self._check_robux()
                self._check_account_status()
            except Exception as e:
                log.error(f"Unexpected error: {e}")
            self._wait()

    # --------------------------------------------------------------------- #
    # API Health
    # --------------------------------------------------------------------- #
    def _check_api_health(self) -> bool:
        try:
            r = rate_limited_request("GET", "https://users.roblox.com/v1/users/authenticated", cookies=self.api.cookies, timeout=10)
            if r.status_code == 200:
                if self.downtime_start:
                    duration = time.time() - self.downtime_start
                    self.notifier.api_downtime("RECOVERED", duration)
                    log.info(Colors.colorize(f"API recovered after {duration:.1f}s", Colors.GREEN))
                    self.downtime_start = None
                return True
        except Exception:
            pass

        if not self.downtime_start:
            self.downtime_start = time.time()
            self.notifier.api_downtime("DOWN")
            log.warning(Colors.colorize("Roblox API unreachable. Retrying...", Colors.RED))
        return False

    # --------------------------------------------------------------------- #
    # Transactions
    # --------------------------------------------------------------------- #
    def _check_transactions(self):
        data = self.api.get_transaction_totals(self.config["TOTAL_CHECKS_TYPE"])
        if not data:
            return
        last = self.storage.load_transactions()
        changes = {k: (last.get(k, 0), v) for k, v in data.items() if v != last.get(k, 0)}
        if changes:
            log.info(Colors.colorize("Transaction changes detected:", Colors.YELLOW))
            for k, (o, n) in changes.items():
                log.info(f"{Colors.CYAN}{k}: {abbreviate_number(o)} → {abbreviate_number(n)}{Colors.RESET}")
            self.notifier.transaction_change(changes)
            self.storage.save_transactions(data)

    # --------------------------------------------------------------------- #
    # Robux
    # --------------------------------------------------------------------- #
    def _check_robux(self):
        robux = self.api.get_robux()
        if robux is None:
            return
        last = self.storage.load_robux()
        if robux != last:
            change = "Increased" if robux > last else "Decreased"
            log.info(Colors.colorize(f"Robux {change}: {abbreviate_number(last)} → {abbreviate_number(robux)}", Colors.MAGENTA))
            self.notifier.robux_change(last, robux)
            self.storage.save_robux(robux)

    # --------------------------------------------------------------------- #
    # Account Status
    # --------------------------------------------------------------------- #
    def _check_account_status(self):
        status = self.api.get_account_status()
        if not status:
            return
        if self.last_status != status:
            banned = status["is_banned"]
            colour = Colors.RED if banned else Colors.GREEN
            log.info(Colors.colorize(f"Account {'BANNED' if banned else 'ACTIVE'}: {status['username']}", colour))
            self.notifier.account_status(status, self.last_status)
            self.last_status = status

    # --------------------------------------------------------------------- #
    # Wait Loop
    # --------------------------------------------------------------------- #
    def _wait(self):
        interval = max(10, int(self.config["CHECK_INTERVAL"] or 60))
        log.info(f"Waiting {interval}s until next check...")
        for remaining in range(interval, 0, -1):
            if self.stop_event.is_set():
                break
            mins, secs = divmod(remaining, 60)
            # Use carriage-return to overwrite the line (same UX as before)
            print(f"\r{Colors.BLUE}Next check in {mins:02d}:{secs:02d}{Colors.RESET}", end="", flush=True)
            time.sleep(1)
        print()  # final newline after countdown

    # --------------------------------------------------------------------- #
    # Signal Handler
    # --------------------------------------------------------------------- #
    def _signal_handler(self, signum, frame):
        log.warning(Colors.colorize(f"Shutting down... (signal {signum} | frame {frame})", Colors.YELLOW))
        self.stop_event.set()

# ─────────────────────────────────────────────────────────────────────────────
# Setup Wizard
# ─────────────────────────────────────────────────────────────────────────────
class SetupWizard:
    def __init__(self):
        self.config = Config()
        self.monitor = Monitor()
        self.update = UpdateChecker()

    def run(self):
        self.update.check()

        if not self.config["ROBLOSECURITY"]:
            self._first_time_setup()
            log.info(Colors.colorize(f"Edit config later: {Paths.CONFIG_FILE}", Colors.CYAN))
            return

        if not self.config.validate_cookie():
            return

        self.monitor.start()

    def _first_time_setup(self):
        log.info(Colors.colorize("Roblox Monitor CLI - First Time Setup", Colors.BOLD + Colors.CYAN))
        log.info("Enter the following details (some input is hidden for security):")

        prompts = [
            ("Discord Webhook URL (Hidden)", getpass),
            (".ROBLOSECURITY Cookie (Hidden)", getpass),
            ("Emoji ID", input),
            ("Emoji Name", input),
            ("Check Interval (seconds, default: 60)", input),
            ("Timeframe (Day/Week/Month/Year, default: Day)", input)
        ]
        defaults = ["", "", "", "", "60", "Day"]

        values = []
        for prompt, reader in prompts:
            try:
                val = reader(f"{Colors.YELLOW}{prompt}:{Colors.RESET}").strip()
                values.append(val)
            except (KeyboardInterrupt, EOFError):
                reader(f"\n{Colors.YELLOW}Setup interrupted by user (Press Ctrl+C Again).{Colors.RESET}\n").strip()

        keys = [
            "DISCORD_WEBHOOK_URL", "ROBLOSECURITY", "DISCORD_EMOJI_ID",
            "DISCORD_EMOJI_NAME", "CHECK_INTERVAL", "TOTAL_CHECKS_TYPE"
        ]

        for k, v, d in zip(keys, values, defaults):
            self.config[k] = v or d

        log.info(Colors.colorize(f"Config saved securely to {Paths.CONFIG_FILE}", Colors.GREEN))

# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        Setup = SetupWizard()
        Setup.run()
    except KeyboardInterrupt:
        log.warning(Colors.colorize("Aborted by user.", Colors.YELLOW))
        raise SystemExit(1)
    except Exception as e:
        log.critical(Colors.colorize(f"Fatal error: {e}", Colors.RED))
        raise SystemExit(1)