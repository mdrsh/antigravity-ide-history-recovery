# Antigravity IDE History Recovery

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Platform: Windows | macOS | Linux](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green.svg)]()
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-brightgreen.svg)]()

> **Automated disaster recovery, repair, and synchronization utility for lost Antigravity IDE chat sessions.**

A standalone, dependency-free tool that scans raw conversation databases on disk, repairs Protobuf index corruption, eliminates ghost sessions, and restores your missing chat history in **Antigravity IDE** after unexpected crashes or resets.

Supports **Windows**, **macOS**, and **Linux**.

---

## The Problem

Antigravity IDE stores raw conversation transcripts (`transcript.jsonl`) and execution SQLite databases (`<UUID>.db`) safely under your user profile:
- **Transcripts**: `~/.gemini/antigravity-ide/brain/<UUID>/.../transcript.jsonl`
- **Databases**: `~/.gemini/antigravity-ide/conversations/<UUID>.db`

However, the IDE chat dropdown index is maintained separately inside a global SQLite database (`state.vscdb`) under key `antigravityUnifiedStateSync.trajectorySummaries` using Base64-encoded Protobuf wire format.

When an unexpected IDE crash or sudden reboot occurs:
1. `state.vscdb` may reset or lose references to recent conversation threads.
2. Chats from the last 24-48 hours disappear from the dropdown, even though all conversation files remain 100% intact on disk.
3. Empty or corrupted ghost sessions (with 0 steps or corrupted token metadata) may clutter the UI.

---

## Features

- 🔍 **Automatic Multi-Platform Discovery**: Detects standard Antigravity IDE profile locations on Windows, macOS, and Linux out of the box.
- ⚡ **Zero External Dependencies**: Built entirely with the Python 3 standard library (`sqlite3`, `json`, `base64`, `pathlib`, `re`). No `pip install` required.
- 🛠️ **Wire-Compatible Protobuf Synthesis**: Correctly constructs native `TrajectorySummary` Protobuf entries with exact timestamps, titles, and workspace descriptors.
- 🧹 **Ghost Shell Purging**: Automatically detects and eliminates empty 0-step phantom sessions.
- 🏷️ **Prompt Title Sanitization**: Strips internal XML/metadata tags (such as `<USER_REQUEST>`) to display clean, readable conversation titles in the dropdown.
- ⏱️ **Chronological Sorting (Newest First)**: Orders all sessions descending by timestamp, ensuring your recent conversations appear right at the top and stay within the IDE's 100-item limit.
- 🔒 **Automatic Safety Backup**: Always generates a timestamped backup copy (`state.vscdb.backup_YYYYMMDD_HHMMSS`) before modifying the database.
- 📝 **Markdown Archiver**: Optionally exports full recovered conversation dialogues into human-readable Markdown files.

---

## Quick Start

### 📦 Download Pre-packaged ZIP
Download the latest ready-to-use archive from [**GitHub Releases**](https://github.com/mdrsh/antigravity-ide-history-recovery/releases/latest/download/antigravity-ide-history-recovery.zip).

### Prerequisites
- Python 3.8 or newer.
- **IMPORTANT**: **Completely close Antigravity IDE** before running the tool to release SQLite locks.

### Windows
1. Download or clone this repository.
2. Double-click `recover_history.bat` (or run in PowerShell / Command Prompt):
   ```cmd
   recover_history.bat
   ```
3. Launch Antigravity IDE. All recovered sessions will be restored in the chat history dropdown!

### macOS & Linux
1. Open Terminal in the repository folder.
2. Make the launcher executable and run:
   ```bash
   chmod +x recover_history.sh
   ./recover_history.sh
   ```
3. Launch Antigravity IDE.

---

## Advanced CLI Options

Run the script directly with custom arguments:

```bash
# Preview what would be restored without modifying state.vscdb
python3 antigravity_ide_history_recovery.py --dry-run

# Specify custom paths
python3 antigravity_ide_history_recovery.py --state-db "/path/to/state.vscdb" --gemini-dir "/path/to/.gemini/antigravity-ide"

# Skip Markdown export prompt
python3 antigravity_ide_history_recovery.py --no-export

# Bypass running IDE process check (use with caution)
python3 antigravity_ide_history_recovery.py --force
```

---

## Default Storage Paths

| Operating System | Global State Database (`state.vscdb`) | Conversations & Brain Data |
|---|---|---|
| **Windows** | `%APPDATA%\Antigravity IDE\User\globalStorage\state.vscdb` | `%USERPROFILE%\.gemini\antigravity-ide` |
| **macOS** | `~/Library/Application Support/Antigravity IDE/User/globalStorage/state.vscdb` | `~/.gemini/antigravity-ide` |
| **Linux** | `~/.config/Antigravity IDE/User/globalStorage/state.vscdb` | `~/.gemini/antigravity-ide` |

---

## Contributing

Pull requests, bug reports, and suggestions are welcome! Feel free to open an issue if you encounter unexpected schema variations or path layouts on your system.

## License

This project is licensed under the [MIT License](LICENSE).
