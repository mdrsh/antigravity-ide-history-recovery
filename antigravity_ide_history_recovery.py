#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Antigravity IDE History Recovery
Automated recovery, repair, and synchronization utility for Antigravity IDE chat sessions.
Supports Windows, macOS, and Linux.
"""

import os
import sys
import json
import sqlite3
import shutil
import base64
import datetime
import argparse
import subprocess
import re
from pathlib import Path

# Force UTF-8 console output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


# --- Pure Python Protobuf Encoders & Parsers (Zero External Dependencies) ---

def encode_varint(val):
    out = bytearray()
    while val >= 0x80:
        out.append((val & 0x7f) | 0x80)
        val >>= 7
    out.append(val & 0x7f)
    return bytes(out)

def encode_field(field_num, wire_type, data):
    tag = encode_varint((field_num << 3) | wire_type)
    if wire_type == 0:  # varint
        return tag + encode_varint(data)
    elif wire_type == 2:  # length-delimited
        return tag + encode_varint(len(data)) + data
    return tag + data

def encode_timestamp(dt):
    sec = int(dt.timestamp())
    nano = dt.microsecond * 1000
    b = bytearray()
    b += encode_field(1, 0, sec)
    if nano:
        b += encode_field(2, 0, nano)
    return bytes(b)

def parse_proto(b):
    i = 0
    items = []
    while i < len(b):
        try:
            key = 0
            shift = 0
            while True:
                byte = b[i]
                i += 1
                key |= (byte & 0x7f) << shift
                shift += 7
                if not (byte & 0x80):
                    break
            field_num = key >> 3
            wire_type = key & 0x7
            if wire_type == 0:  # varint
                val = 0
                shift = 0
                while True:
                    byte = b[i]
                    i += 1
                    val |= (byte & 0x7f) << shift
                    shift += 7
                    if not (byte & 0x80):
                        break
                items.append((field_num, 'varint', val))
            elif wire_type == 2:  # length-delimited
                length = 0
                shift = 0
                while True:
                    byte = b[i]
                    i += 1
                    length |= (byte & 0x7f) << shift
                    shift += 7
                    if not (byte & 0x80):
                        break
                val = b[i:i+length]
                i += length
                items.append((field_num, 'bytes', val))
            elif wire_type == 1:  # 64-bit
                val = b[i:i+8]
                i += 8
                items.append((field_num, '64bit', val))
            elif wire_type == 5:  # 32-bit
                val = b[i:i+4]
                i += 4
                items.append((field_num, '32bit', val))
            else:
                break
        except Exception:
            break
    return items


# --- Cross-Platform Environment & Paths ---

def is_ide_running():
    system = sys.platform
    try:
        if system.startswith('win'):
            output = subprocess.check_output('tasklist /FI "IMAGENAME eq Antigravity*" /NH', shell=True, text=True)
            for line in output.strip().splitlines():
                if "Antigravity" in line and ".exe" in line:
                    return True
        else:
            # macOS / Linux
            output = subprocess.check_output(['pgrep', '-f', '-i', 'antigravity'], text=True)
            if output.strip():
                return True
    except Exception:
        pass
    return False

def discover_standard_locations():
    """
    Auto-detects Antigravity IDE globalStorage and data paths across Windows, macOS, and Linux.
    """
    home = Path.home()
    system = sys.platform
    candidates = []

    if system.startswith('win'):
        appdata = os.environ.get("APPDATA")
        if appdata:
            # Standard Windows Paths
            candidates.append({
                'label': 'Windows Standard (Antigravity IDE)',
                'state_db': Path(appdata) / "Antigravity IDE" / "User" / "globalStorage" / "state.vscdb",
                'gemini_dir': home / ".gemini" / "antigravity-ide"
            })
            candidates.append({
                'label': 'Windows Standard (Antigravity)',
                'state_db': Path(appdata) / "Antigravity" / "User" / "globalStorage" / "state.vscdb",
                'gemini_dir': home / ".gemini" / "antigravity"
            })
    elif system == 'darwin':
        # macOS Paths
        app_support = home / "Library" / "Application Support"
        candidates.append({
            'label': 'macOS Standard (Antigravity IDE)',
            'state_db': app_support / "Antigravity IDE" / "User" / "globalStorage" / "state.vscdb",
            'gemini_dir': home / ".gemini" / "antigravity-ide"
        })
        candidates.append({
            'label': 'macOS Standard (Antigravity)',
            'state_db': app_support / "Antigravity" / "User" / "globalStorage" / "state.vscdb",
            'gemini_dir': home / ".gemini" / "antigravity"
        })
    else:
        # Linux / Unix Paths
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        config_dir = Path(xdg_config) if xdg_config else home / ".config"
        candidates.append({
            'label': 'Linux Standard (Antigravity IDE)',
            'state_db': config_dir / "Antigravity IDE" / "User" / "globalStorage" / "state.vscdb",
            'gemini_dir': home / ".gemini" / "antigravity-ide"
        })
        candidates.append({
            'label': 'Linux Standard (antigravity)',
            'state_db': config_dir / "antigravity" / "User" / "globalStorage" / "state.vscdb",
            'gemini_dir': home / ".gemini" / "antigravity"
        })

    valid = []
    for c in candidates:
        s_db = c['state_db']
        g_dir = c['gemini_dir']
        conv_dir = g_dir / "conversations"
        brain_dir = g_dir / "brain"
        # At least state.vscdb or conversations should exist
        if s_db.exists() or conv_dir.exists():
            valid.append({
                'label': c['label'],
                'state_db': s_db,
                'conversations': conv_dir,
                'brain': brain_dir,
                'exports': Path(__file__).resolve().parent / "exports"
            })
    return valid


# --- Session Extraction & Parsing ---

def clean_chat_title(raw_content):
    if not raw_content:
        return ""
    # Strip metadata XML tags
    t = re.sub(r'<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>', '', raw_content, flags=re.DOTALL)
    t = re.sub(r'<[^>]+>', '', t)
    t = " ".join(t.split())
    return t[:80].strip()

def extract_session_info(cid, conv_db_path, brain_dir):
    title = f"Chat {cid[:8]}"
    last_mod = datetime.datetime.fromtimestamp(os.path.getmtime(conv_db_path))
    turn_count = 1
    step_count = 0
    ws_proto = None

    # 1. Read SQLite metadata
    try:
        conn = sqlite3.connect(conv_db_path)
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM steps")
        step_count = cur.fetchone()[0]

        # Extract workspace proto from trajectory_metadata_blob if available
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trajectory_metadata_blob'")
        if cur.fetchone():
            cur.execute("SELECT data FROM trajectory_metadata_blob WHERE id='main'")
            row = cur.fetchone()
            if row and row[0]:
                blob_items = parse_proto(row[0])
                meta_dict = {num: (wt, d) for num, wt, d in blob_items}
                if 1 in meta_dict and meta_dict[1][0] == 'bytes':
                    ws_proto = meta_dict[1][1]
        conn.close()
    except Exception:
        step_count = 0

    # 2. Extract title from transcript.jsonl
    transcript_file = brain_dir / cid / ".system_generated" / "logs" / "transcript.jsonl"
    has_transcript = transcript_file.exists()
    if has_transcript:
        try:
            with open(transcript_file, 'r', encoding='utf-8', errors='ignore') as f:
                user_turns = 0
                for line in f:
                    data = json.loads(line)
                    if data.get('type') == 'USER_INPUT':
                        user_turns += 1
                        if user_turns == 1:
                            cleaned = clean_chat_title(data.get('content', ''))
                            if cleaned:
                                title = cleaned
                if user_turns > 0:
                    turn_count = user_turns
        except Exception:
            pass

    return {
        'id': cid,
        'title': title,
        'mtime': last_mod,
        'turn_count': max(turn_count, step_count // 2 if step_count else 1),
        'step_count': step_count,
        'has_transcript': has_transcript,
        'ws_proto': ws_proto
    }


# --- Wire-Compatible Protobuf Synthesis ---

def build_complete_summary_proto_entry(session_info):
    cid_str = session_info['id']
    cid_bytes = cid_str.encode('utf-8')
    title_bytes = session_info['title'].encode('utf-8')
    mtime = session_info['mtime']

    # Timestamps (Field 3, 7, 10)
    ts_proto = encode_timestamp(mtime)

    # Workspace Proto (Field 9)
    ws_proto = session_info.get('ws_proto')
    if not ws_proto:
        # Generic empty workspace descriptor
        ws_proto = encode_field(1, 2, b"") + encode_field(3, 2, b"")

    # Native TrajectorySummary Schema:
    # Field 1: Title (string)
    # Field 2: Turn count (varint)
    # Field 3: Timestamp (TimestampProto)
    # Field 4: Conversation UUID (string)
    # Field 5: Status (varint 1)
    # Field 7: Last modified (TimestampProto)
    # Field 9: Workspace (WorkspaceProto)
    # Field 10: Created (TimestampProto)
    # Field 15: Empty string (b"")
    # Field 16: Status code (varint 1)
    inner = bytearray()
    inner += encode_field(1, 2, title_bytes)
    inner += encode_field(2, 0, max(1, session_info['turn_count']))
    inner += encode_field(3, 2, ts_proto)
    inner += encode_field(4, 2, cid_bytes)
    inner += encode_field(5, 0, 1)
    inner += encode_field(7, 2, ts_proto)
    inner += encode_field(9, 2, ws_proto)
    inner += encode_field(10, 2, ts_proto)
    inner += encode_field(15, 2, b'')
    inner += encode_field(16, 0, 1)

    inner_b64 = base64.b64encode(bytes(inner))
    sub2 = encode_field(1, 2, inner_b64)

    entry_payload = bytearray()
    entry_payload += encode_field(1, 2, cid_bytes)
    entry_payload += encode_field(2, 2, sub2)

    return encode_field(1, 2, bytes(entry_payload))


# --- Markdown Exporter ---

def export_sessions_to_markdown(sessions, brain_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for s in sessions:
        cid = s['id']
        t_file = brain_dir / cid / ".system_generated" / "logs" / "transcript.jsonl"
        if not t_file.exists():
            continue
        safe_title = re.sub(r'[\\/*?:"<>|]', "", s['title'])[:40].strip()
        date_prefix = s['mtime'].strftime("%Y-%m-%d_%H%M")
        md_name = f"{date_prefix}_{safe_title}_{cid[:8]}.md"
        out_p = output_dir / md_name

        try:
            with open(t_file, 'r', encoding='utf-8', errors='ignore') as in_f, open(out_p, 'w', encoding='utf-8') as out_f:
                out_f.write(f"# {s['title']}\n\n")
                out_f.write(f"- **ID**: `{cid}`\n")
                out_f.write(f"- **Date**: {s['mtime'].strftime('%Y-%m-%d %H:%M:%S')}\n\n---\n\n")
                
                step_idx = 1
                for line in in_f:
                    data = json.loads(line)
                    mtype = data.get('type')
                    content = data.get('content', '')
                    if mtype == 'USER_INPUT':
                        cleaned_prompt = clean_chat_title(content)
                        out_f.write(f"### 👤 User (Step {step_idx})\n\n{cleaned_prompt}\n\n")
                        step_idx += 1
                    elif mtype == 'PLANNER_RESPONSE' and content:
                        out_f.write(f"### 🤖 Assistant (Step {step_idx})\n\n{content}\n\n---\n\n")
                        step_idx += 1
            count += 1
        except Exception:
            pass
    return count


# --- Main Execution ---

def main():
    parser = argparse.ArgumentParser(description="Antigravity IDE History Recovery - Automated Recovery & Sync Utility")
    parser.add_argument("--state-db", help="Explicit path to state.vscdb")
    parser.add_argument("--gemini-dir", help="Explicit path to .gemini/antigravity-ide data directory")
    parser.add_argument("--dry-run", action="store_true", help="Inspect and audit history without writing changes")
    parser.add_argument("--force", action="store_true", help="Bypass running IDE process warning")
    parser.add_argument("--no-export", action="store_true", help="Skip Markdown transcript archive generation")
    args = parser.parse_args()

    print("===============================================================")
    print("  Antigravity IDE History Recovery (Cross-Platform Recovery)")
    print("===============================================================")

    # 1. Safety Check: Verify IDE is not running
    if is_ide_running():
        print("\n[WARNING]: Antigravity IDE processes are currently running!")
        print("Please completely close Antigravity IDE before synchronizing")
        print("to avoid SQLite database locks and potential data loss.\n")
        if not args.force:
            input("Press Enter to exit...")
            sys.exit(1)

    # 2. Resolve Paths
    target_state_db = None
    target_conv_dir = None
    target_brain_dir = None
    target_exports = Path(__file__).resolve().parent / "exports"

    if args.state_db and args.gemini_dir:
        target_state_db = Path(args.state_db)
        g_dir = Path(args.gemini_dir)
        target_conv_dir = g_dir / "conversations"
        target_brain_dir = g_dir / "brain"
    else:
        print("\nDiscovering Antigravity IDE installation...")
        locations = discover_standard_locations()
        if not locations:
            print("[ERROR]: Could not automatically detect Antigravity IDE paths.")
            print("Please specify --state-db and --gemini-dir manually.")
            sys.exit(1)
        elif len(locations) == 1:
            loc = locations[0]
            print(f"Detected: {loc['label']}")
            target_state_db = loc['state_db']
            target_conv_dir = loc['conversations']
            target_brain_dir = loc['brain']
        else:
            print("Multiple configurations found. Please select one:")
            for idx, loc in enumerate(locations, start=1):
                print(f"  [{idx}] {loc['label']}")
                print(f"      DB: {loc['state_db']}")
            while True:
                c = input("Selection (or 'q' to quit): ").strip()
                if c.lower() == 'q':
                    sys.exit(0)
                if c.isdigit() and 1 <= int(c) <= len(locations):
                    chosen = locations[int(c) - 1]
                    target_state_db = chosen['state_db']
                    target_conv_dir = chosen['conversations']
                    target_brain_dir = chosen['brain']
                    break
                print("Invalid selection. Try again.")

    if not target_state_db.exists():
        print(f"[ERROR]: state.vscdb not found at:\n{target_state_db}")
        sys.exit(1)
    if not target_conv_dir.exists():
        print(f"[ERROR]: conversations directory not found at:\n{target_conv_dir}")
        sys.exit(1)

    print(f"\nTarget Database : {target_state_db}")
    print(f"Target Data Dir : {target_conv_dir.parent}\n")

    # 3. Scan Valid Sessions on Disk
    print("Scanning conversation files on disk (*.db & transcript.jsonl)...")
    raw_conv_files = {f.stem: f for f in target_conv_dir.glob("*.db")}
    
    # Filter out empty 0-step sessions with no transcript
    conv_files = {}
    for cid, fpath in raw_conv_files.items():
        info = extract_session_info(cid, fpath, target_brain_dir)
        if info['step_count'] > 0 or info['has_transcript']:
            conv_files[cid] = (fpath, info)

    print(f"Found {len(conv_files)} valid conversation sessions (empty ghost shells ignored).")

    # 4. Audit Existing Index in state.vscdb
    print("Auditing existing index from state.vscdb...")
    conn = sqlite3.connect(target_state_db)
    cur = conn.cursor()
    cur.execute("SELECT value FROM ItemTable WHERE key='antigravityUnifiedStateSync.trajectorySummaries'")
    row = cur.fetchone()

    healthy_sessions = {}
    purged_ghost_count = 0

    if row and row[0]:
        try:
            raw = base64.b64decode(row[0])
            top_items = parse_proto(raw)
            for item in top_items:
                if item[0] == 1 and item[1] == 'bytes':
                    sub = parse_proto(item[2])
                    if sub and sub[0][0] == 1 and sub[0][1] == 'bytes':
                        cid = sub[0][2].decode('utf-8', errors='ignore')
                        
                        # Purge ghost items not on disk or with 0 steps
                        if cid not in conv_files:
                            purged_ghost_count += 1
                            continue

                        is_valid_native = False
                        entry_mtime = conv_files[cid][1]['mtime']

                        if len(sub) > 1 and sub[1][0] == 2 and sub[1][1] == 'bytes':
                            sub2 = parse_proto(sub[1][2])
                            if sub2 and sub2[0][0] == 1 and sub2[0][1] == 'bytes':
                                try:
                                    inner = parse_proto(base64.b64decode(sub2[0][2]))
                                    inner_map = {x[0]: x for x in inner}
                                    has_f17 = 17 in inner_map
                                    f15_corrupt = (15 in inner_map and inner_map[15][1] == 'bytes' and len(inner_map[15][2]) > 100)
                                    if 1 in inner_map and 7 in inner_map and 10 in inner_map and not has_f17 and not f15_corrupt:
                                        is_valid_native = True
                                except Exception:
                                    pass

                        if is_valid_native:
                            healthy_sessions[cid] = (entry_mtime, encode_field(1, 2, item[2]))
        except Exception as e:
            print(f"Notice: Failed to parse some existing summaries: {e}")

    # 5. Determine sessions needing repair / restoration
    all_valid_cids = set(conv_files.keys())
    healthy_cids = set(healthy_sessions.keys())
    to_process_cids = all_valid_cids - healthy_cids

    print(f"Valid & complete sessions in index : {len(healthy_cids)}")
    print(f"Purged invalid/ghost sessions      : {purged_ghost_count}")
    print(f"Missing / damaged sessions to sync : {len(to_process_cids)}")

    all_final_entries = []

    # Preserve all existing healthy entries
    for cid, (mtime, raw_proto) in healthy_sessions.items():
        all_final_entries.append((mtime, raw_proto))

    # Repair & synthesize missing entries
    repaired_sessions_list = []
    if to_process_cids:
        for cid in to_process_cids:
            fpath, info = conv_files[cid]
            entry_bytes = build_complete_summary_proto_entry(info)
            all_final_entries.append((info['mtime'], entry_bytes))
            repaired_sessions_list.append(info)

        repaired_sessions_list.sort(key=lambda x: x['mtime'], reverse=True)
        print("\nSessions to be restored/repaired:")
        for s in repaired_sessions_list:
            print(f"  + [{s['mtime'].strftime('%Y-%m-%d %H:%M')}] {s['id'][:8]} :: {s['title']}")

    # 6. Sort ALL entries newest-first
    # This guarantees the most recent chats appear at the top of the UI dropdown and within the 100-item cutoff
    all_final_entries.sort(key=lambda x: x[0], reverse=True)

    if not to_process_cids and purged_ghost_count == 0:
        print("\nAll sessions are already present in DB with complete metadata! Nothing to sync.")
    else:
        if args.dry_run:
            print("\n[DRY-RUN MODE]: No changes written to database.")
        else:
            # Backup
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = target_state_db.with_name(f"state.vscdb.backup_{ts}")
            shutil.copy2(target_state_db, backup_file)
            print(f"\n[BACKUP]: Created safety backup -> {backup_file}")

            # Write updated Protobuf Map to SQLite
            print("Writing updated sessions into state.vscdb...")
            new_payload = bytearray()
            for mtime, entry_bytes in all_final_entries:
                new_payload.extend(entry_bytes)

            new_b64 = base64.b64encode(bytes(new_payload)).decode('ascii')
            cur.execute("UPDATE ItemTable SET value=? WHERE key='antigravityUnifiedStateSync.trajectorySummaries'", (new_b64,))
            conn.commit()
            print(f"[SUCCESS]: Database updated successfully! Total {len(all_final_entries)} sessions ordered and saved.")

    conn.close()

    # 7. Optional Markdown Export
    if not args.no_export and repaired_sessions_list:
        do_export = True
        if not args.dry_run:
            ans = input("\nDo you want to export restored sessions as Markdown? [Y/n]: ").strip().lower()
            if ans in ['n', 'no']:
                do_export = False
        if do_export:
            print("Exporting conversation transcripts to Markdown...")
            count = export_sessions_to_markdown(repaired_sessions_list, target_brain_dir, target_exports)
            print(f"Exported {count} sessions to: {target_exports}")

    print("\nOperation completed! You can now launch Antigravity IDE.\n")
    if sys.platform.startswith('win'):
        input("Press Enter to exit...")

if __name__ == '__main__':
    main()
