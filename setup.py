import shutil
import sys
import subprocess
import argparse
import psutil
from time import sleep
from typing import Optional, List
from dataclasses import dataclass
from pathlib import Path

# --- custom colored message helper (scratch-built) -----------------
def _color_print(level: str, message: str) -> None:
    """Print a colored message based on level."""
    colors = {
        "debug": "\033[37m",      # light grey (more readable than dark grey)
        "info": "\033[94m",       # blue
        "warning": "\033[93m",    # yellow
        "success": "\033[92m",    # green
        "error": "\033[91m",      # red
        "critical": "\033[95m",  # magenta
        "trace": "\033[96m",      # cyan
        "notice": "\033[97m",     # bright white
    }
    reset = "\033[0m"
    color = colors.get(level.lower(), "")
    print(f"{color}[{level.upper()}] {message}{reset}")

@dataclass
class Config:
    optimization_lvl: int = 2
    app_name: str = "main"
    app_title: str = "Roblox Transaction Monitor (CTL Edition)"
    debug_mode: bool = False

class _FallbackLogger:
    @staticmethod
    def Log(level: str, message: str) -> str:
        _color_print(level, message)
        return message

class _DebugLogger:
    def __init__(self, base_logger):
        self.base_logger = base_logger
        self.debug_enabled = False

    def enable_debug(self, can_debug: bool) -> None:
        self.debug_enabled = can_debug

    def Log(self, level: str, message: str) -> str:
        if self.debug_enabled or level.lower() != "debug":
            return self.base_logger(level, message)
        return ""

try:
    from src.Packages.CustomLogging import Logging
    logger = _DebugLogger(Logging.Log)
except Exception:
    logger = _DebugLogger(_FallbackLogger.Log)

class PyInstallerBuilder:
    """Manages the build process for creating executables using PyInstaller."""

    def __init__(self, script_file: Optional[str] = None, enable_debug: bool = False):
        self.logger = logger
        self.config = Config()
        self.script_file = Path(script_file or (sys.argv[1] if len(sys.argv) > 1 else "main.py"))
        self.logger.enable_debug(self.config.debug_mode or enable_debug)
        self.optimization_lvl = self.config.optimization_lvl

        self._validate_script_file()
        self.pyinstaller_args = self._build_pyinstaller_args()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _validate_script_file(self) -> None:
        self.logger.Log("debug", f"Validating script file: {self.script_file}")
        if not self.script_file.exists():
            self.logger.Log("error", f"Script file '{self.script_file}' not found.")
            self._exit_script()

    def _get_executable_name(self) -> str:
        name = f"{self.config.app_title}"
        self.logger.Log("debug", f"Executable name determined: {name}")
        return name

    def _get_source_path(self) -> str:
        return "src/"

    def _get_icon_path(self) -> str:
        return f"{self._get_source_path()}Icons/Robux.ico"

    def _get_version_path(self) -> str:
        return f"{self._get_source_path()}VERSION"

    def _get_app_type(self) -> str:
        return "--onefile"

    def _collect_submodules(self) -> str:
        return "Roblox-Transaction-Monitor/"

    def _build_pyinstaller_args(self) -> List[str]:
        return [
            str(self.script_file),
            "--noconfirm",
            "--noconsole",
            f"{self._get_app_type()}",
            "--clean",
            f"--icon={self._get_icon_path()}",
            f"--name={self._get_executable_name()}",
            f"--optimize={self.config.optimization_lvl}",
            f"--add-data={self._get_icon_path()};.",
            f"--add-data={self._get_version_path()};.",
            f"--add-data={self._get_source_path()};.",
            f"--collect-submodules={self._collect_submodules()}",
            "--log-level=WARN",
        ]

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def _kill_locking_processes(self, path: Path) -> None:
        """Attempt to terminate processes that have open handles to the given path."""
        try:
            for proc in psutil.process_iter(["pid", "name", "open_files"]):
                try:
                    for file in proc.info["open_files"] or []:
                        if file and path.resolve() in Path(file.path).resolve().parents:
                            self.logger.Log(
                                "warning",
                                f"Killing process {proc.info['name']} (PID {proc.info['pid']}) locking {path}",
                            )
                            proc.kill()
                            proc.wait(timeout=3)
                            break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as exc:
            self.logger.Log("warning", f"Could not inspect locking processes: {exc}")

    def _remove_directory(self, path: Path) -> None:
        self.logger.Log("debug", f"Attempting to remove directory: {path}")
        if not path.exists():
            self.logger.Log("info", f"'{path}' directory not found — skipping.")
            return

        for attempt in range(1, 4):
            try:
                self._kill_locking_processes(path)
                shutil.rmtree(path, ignore_errors=False)
                self.logger.Log("success", f"'{path}' directory removed successfully.")
                return
            except PermissionError as exc:
                self.logger.Log(
                    "warning",
                    f"Attempt {attempt}/3: Permission denied removing '{path}': {exc}",
                )
                sleep(attempt * 1.5)
            except Exception as exc:
                self.logger.Log("warning", f"Failed to remove '{path}': {exc}")
                return
                
        self.logger.Log("error", f"Could not remove '{path}' after 3 attempts.")

    def _remove_file(self, file_path: Path) -> bool:
        self.logger.Log("debug", f"Attempting to remove file: {file_path}")
        if not file_path.exists():
            return False
        self.logger.Log("info", f"Removing '{file_path}'...")
        try:
            file_path.unlink()
            self.logger.Log("success", f"'{file_path}' removed successfully.")
            return True
        except Exception as exc:
            self.logger.Log("warning", f"Failed to remove '{file_path}': {exc}")
            return False

    def cleanup_dirs(self) -> None:
        self.logger.Log("debug", "Starting cleanup of directories and spec files")
        for folder in (Path("build"), Path("dist")):
            self._remove_directory(folder)

        base_name = self.script_file.stem
        possible_specs = [
            Path(f"{base_name}.spec"),
            Path(
                self._get_executable_name()
                .replace(" ", "_")
                .replace("(", "")
                .replace(")", "")
                + ".spec"
            ),
        ]

        removed = 0
        for spec in possible_specs:
            if self._remove_file(spec):
                removed += 1

        for entry in Path(".").glob("*.spec"):
            if entry not in possible_specs:
                if self._remove_file(entry):
                    removed += 1

        if not removed:
            self.logger.Log("info", "No .spec files found to remove.")

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------
    def build_executable(self) -> None:
        self.logger.Log("info", f"Building executable for '{self.script_file}'...")
        try:
            self.logger.Log(
                "info", "Running PyInstaller with arguments: " + " ".join(self.pyinstaller_args)
            )
            cmd = [sys.executable, "-m", "PyInstaller"] + self.pyinstaller_args
            self.logger.Log("debug", f"Executing command: {cmd}")
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                self.logger.Log("error", f"PyInstaller build failed:\n{result.stderr}")
                self._exit_script(2)
            self.logger.Log(
                "success",
                f"Executable '{self._get_executable_name()}' built successfully in 'dist' folder.",
            )
        except Exception as exc:
            self.logger.Log("error", f"PyInstaller build failed: {exc}")
            self._exit_script(2)

    # ------------------------------------------------------------------
    # Flow control
    # ------------------------------------------------------------------
    def _exit_script(self, duration: float = 1.0, exit_code: int = 1) -> None:
        self.logger.Log("info", "Exiting script.")
        sleep(duration)
        sys.exit(exit_code)

    def run(self, cleanup_delay: float = 0.5) -> None:
        self.logger.Log("info", f"Starting build process for '{self.script_file}'...")
        try:
            self.cleanup_dirs()
            sleep(cleanup_delay)
            self.build_executable()
            self.logger.Log("success", "Build process completed successfully.")
        except Exception as exc:
            self.logger.Log("error", f"Build process failed: {exc}")
            self._exit_script(cleanup_delay)

class Launcher:
    def _parse_cli(self) -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description="Build an executable from a Python script using PyInstaller."
        )
        args = [
            {
                "name": "--target-script",
                "kwargs": {
                    "nargs": "?",
                    "default": "src/main.py",
                    "help": "Python script to build (default: main.py)",
                },
            },
            {
                "name": "--debug",
                "kwargs": {
                    "action": "store_true",
                    "help": "Enable debug logging",
                },
            },
        ]
        for arg in args:
            parser.add_argument(arg["name"], **arg["kwargs"])
        return parser.parse_args()

    def build_executable(self) -> None:
        args = self._parse_cli()
        builder = PyInstallerBuilder(
            script_file=args.target_script, enable_debug=args.debug
        )
        builder.run()

if __name__ == "__main__":
    AddArgs = Launcher()
    AddArgs.build_executable()