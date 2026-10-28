import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import win_control as v1


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

OPENCLAW_SCRIPTS = Path(__file__).resolve().parent
QWEN_LOCATE = OPENCLAW_SCRIPTS / "qwen_locate.py"
WINSNAP = OPENCLAW_SCRIPTS / "winsnap.py"

LOG_DIR = Path(os.environ.get("WVC_OUTPUT_DIR", Path(__file__).resolve().parent.parent / "runtime")) / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LOG = LOG_DIR / "v2_trajectory.jsonl"

ALLOWED_ACTIONS = {
    "locate",
    "click",
    "click_sequence",
    "click_target",
    "type",
    "type_target",
    "paste",
    "paste_target",
    "press",
    "hotkey",
    "wait",
    "screenshot",
    "done",
    "fail",
}


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def append_log(entry, log_path=DEFAULT_LOG):
    entry = {"time": now_iso(), **entry}
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def run_capture(cmd):
    proc = subprocess.run(
        cmd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_locate_output(output):
    results = []
    current_name = None
    run_points = []

    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        name_match = re.match(r"\s{2}(.+?)\s*$", line)
        if name_match and not line.lstrip().startswith(("runs:", "->")):
            current_name = name_match.group(1).strip()
            run_points = []
            continue

        runs_match = re.search(r"runs:\s*(.+)$", line)
        if runs_match:
            run_points = [
                [int(x), int(y)]
                for x, y in re.findall(r"\((\d+),\s*(\d+)\)", runs_match.group(1))
            ]
            continue

        point_match = re.search(r"->\s*\((\d+),\s*(\d+)\)", line)
        if point_match and current_name:
            x = int(point_match.group(1))
            y = int(point_match.group(2))
            max_deviation = 0
            if run_points:
                max_deviation = max(
                    max(abs(px - x), abs(py - y)) for px, py in run_points
                )
            results.append(
                {
                    "name": current_name,
                    "x": x,
                    "y": y,
                    "runs": run_points,
                    "max_deviation": max_deviation,
                }
            )

    return results


def locate_target(target, win=None, single=False, log=True):
    cmd = [sys.executable, str(QWEN_LOCATE)]
    if win:
        v1.activate_window(win)
        cmd.extend(["--win", win])
    if single:
        cmd.append("--1")
    cmd.append(target)

    code, stdout, stderr = run_capture(cmd)
    if stdout:
        print(stdout, end="")
    if stderr:
        print(stderr, file=sys.stderr, end="")
    if code != 0:
        raise SystemExit(code)

    if "[WARN] UNSTABLE" in stdout:
        raise SystemExit("[V2] Unstable localization; inspect a fresh screenshot before retrying.")
    results = parse_locate_output(stdout)
    if log:
        append_log(
            {
                "action": "locate",
                "target": target,
                "window": win,
                "single": single,
                "results": results,
            }
        )
    return results


def choose_point(results, prefer_name=None):
    if not results:
        raise SystemExit("[V2] locate returned no parseable coordinates.")
    if prefer_name:
        needle = prefer_name.lower()
        for item in results:
            if needle in item["name"].lower():
                return item
    return sorted(results, key=lambda item: item.get("max_deviation", 0))[0]


def screenshot(win=None):
    if win:
        code, stdout, stderr = run_capture([sys.executable, str(WINSNAP), win, "--foreground"])
        if stdout:
            print(stdout, end="")
        if stderr:
            print(stderr, file=sys.stderr, end="")
        match = re.search(r"SNAPSHOT=(.+)", stdout)
        path = match.group(1).strip() if match else ""
    else:
        # Reuse qwen_locate's full-screen screenshot path by doing a cheap no-op locate is not safe.
        # For V2, full-screen verification remains visual/manual unless a window is specified.
        path = ""
        print("[V2] Full-screen screenshot export is not implemented; use --win for saved verification snapshots.")
    append_log({"action": "screenshot", "window": win, "snapshot": path})
    return path


def click_point(x, y, dry_run=False):
    if dry_run:
        print(f"[V2 dry-run] would click ({x}, {y})")
        return
    v1.click_xy(x, y)
    print(f"[V2] clicked ({x}, {y})")


def click_sequence(points, delay=0.16, dry_run=False):
    normalized = []
    for point in points:
        if isinstance(point, dict):
            x, y = int(point["x"]), int(point["y"])
        else:
            x, y = int(point[0]), int(point[1])
        normalized.append({"x": x, "y": y})

    for point in normalized:
        click_point(point["x"], point["y"], dry_run=dry_run)
        if not dry_run and delay > 0:
            time.sleep(delay)

    append_log(
        {
            "action": "click_sequence",
            "points": normalized,
            "delay": delay,
            "dry_run": dry_run,
        }
    )


def click_target(args):
    results = locate_target(args.target, win=args.win, single=args.single)
    point = choose_point(results, args.prefer_name)
    print(f"[V2] selected: {point['name']} -> ({point['x']}, {point['y']})")
    click_point(point["x"], point["y"], dry_run=args.dry_run)
    snap = screenshot(args.win) if args.verify and not args.dry_run else ""
    append_log(
        {
            "action": "click_target",
            "target": args.target,
            "selected": point,
            "dry_run": args.dry_run,
            "verification_snapshot": snap,
        }
    )


def paste_at(x, y, text, win=None, replace=False, dry_run=False):
    if win:
        v1.activate_window(win)
    if dry_run:
        print(f"[V2 dry-run] would paste {len(text)} chars at ({x}, {y}); replace={replace}")
        return
    v1.click_xy(x, y)
    time.sleep(0.25)
    if replace:
        v1.send_ctrl_a_backspace()
    set_clipboard_text(text)
    time.sleep(0.15)
    v1.send_ctrl_v()
    print("[V2] pasted with clipboard; no Enter was pressed.")


def set_clipboard_text(text):
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
        ],
        input=text,
        text=True,
        encoding="utf-8",
        check=True,
    )


def type_at(x, y, text, win=None, dry_run=False, interval=0.02):
    if any(ord(ch) > 127 for ch in text):
        raise SystemExit("[V2] type supports ASCII only; use paste only when explicitly allowed.")
    if win:
        v1.activate_window(win)
    if dry_run:
        print(f"[V2 dry-run] would type {text!r} at ({x}, {y})")
        return
    v1.click_xy(x, y)
    time.sleep(0.2)
    import pyautogui

    pyautogui.write(text, interval=interval)
    print(f"[V2] typed {len(text)} ASCII chars at ({x}, {y})")


def type_target(args):
    results = locate_target(args.target, win=args.win, single=args.single)
    point = choose_point(results, args.prefer_name)
    print(f"[V2] selected: {point['name']} -> ({point['x']}, {point['y']})")
    type_at(
        point["x"],
        point["y"],
        args.text,
        win=args.win,
        dry_run=args.dry_run,
        interval=args.interval,
    )
    snap = screenshot(args.win) if args.verify and not args.dry_run else ""
    append_log(
        {
            "action": "type_target",
            "target": args.target,
            "selected": point,
            "text": args.text,
            "dry_run": args.dry_run,
            "verification_snapshot": snap,
        }
    )


def paste_target(args):
    results = locate_target(args.target, win=args.win, single=args.single)
    point = choose_point(results, args.prefer_name)
    print(f"[V2] selected: {point['name']} -> ({point['x']}, {point['y']})")
    paste_at(
        point["x"],
        point["y"],
        args.text,
        win=args.win,
        replace=args.replace,
        dry_run=args.dry_run,
    )
    snap = screenshot(args.win) if args.verify and not args.dry_run else ""
    append_log(
        {
            "action": "paste_target",
            "target": args.target,
            "selected": point,
            "text_len": len(args.text),
            "replace": args.replace,
            "dry_run": args.dry_run,
            "verification_snapshot": snap,
        }
    )


def send_hotkey(keys, dry_run=False):
    keys = [k.strip().lower() for k in keys if k.strip()]
    if dry_run:
        print(f"[V2 dry-run] would press hotkey: {keys}")
        return
    user32 = v1._user32()
    keyup = 0x0002
    vk = {
        "ctrl": 0x11,
        "control": 0x11,
        "shift": 0x10,
        "alt": 0x12,
        "win": 0x5B,
        "enter": 0x0D,
        "esc": 0x1B,
        "escape": 0x1B,
        "tab": 0x09,
        "a": 0x41,
        "c": 0x43,
        "v": 0x56,
        "x": 0x58,
        "z": 0x5A,
    }
    missing = [key for key in keys if key not in vk]
    if missing:
        raise SystemExit(f"[V2] unsupported hotkey key(s): {missing}")
    for key in keys:
        user32.keybd_event(vk[key], 0, 0, 0)
        time.sleep(0.03)
    for key in reversed(keys):
        user32.keybd_event(vk[key], 0, keyup, 0)
        time.sleep(0.03)
    print(f"[V2] hotkey sent: {keys}")


def press_key(key, dry_run=False):
    key = key.strip().lower()
    allowed = {
        "enter": 0x0D,
        "esc": 0x1B,
        "escape": 0x1B,
        "tab": 0x09,
        "backspace": 0x08,
        "delete": 0x2E,
        "space": 0x20,
    }
    if key not in allowed:
        raise SystemExit(f"[V2] unsupported press key: {key}")
    if dry_run:
        print(f"[V2 dry-run] would press key: {key}")
        return
    user32 = v1._user32()
    keyup = 0x0002
    user32.keybd_event(allowed[key], 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(allowed[key], 0, keyup, 0)
    print(f"[V2] pressed key: {key}")


def load_action(action_text):
    if os.path.exists(action_text):
        with open(action_text, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    return json.loads(action_text)


def execute_action(action, args):
    kind = action.get("action")
    if kind not in ALLOWED_ACTIONS:
        raise SystemExit(f"[V2] action is not allowed: {kind}")

    dry_run = bool(action.get("dry_run", args.dry_run))
    win = action.get("win") or action.get("window")
    append_log({"action": "run_action", "input": action, "dry_run": dry_run})

    if kind == "locate":
        results = locate_target(action["target"], win=win, single=bool(action.get("single", False)))
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))
    elif kind == "click":
        click_point(int(action["x"]), int(action["y"]), dry_run=dry_run)
    elif kind == "click_sequence":
        click_sequence(
            action["points"],
            delay=float(action.get("delay", 0.16)),
            dry_run=dry_run,
        )
    elif kind == "click_target":
        ns = argparse.Namespace(
            target=action["target"],
            win=win,
            single=bool(action.get("single", False)),
            prefer_name=action.get("prefer_name"),
            dry_run=dry_run,
            verify=bool(action.get("verify", args.verify)),
        )
        click_target(ns)
    elif kind == "type":
        type_at(
            int(action["x"]),
            int(action["y"]),
            action["text"],
            win=win,
            dry_run=dry_run,
            interval=float(action.get("interval", 0.02)),
        )
    elif kind == "type_target":
        ns = argparse.Namespace(
            target=action["target"],
            text=action["text"],
            win=win,
            single=bool(action.get("single", False)),
            prefer_name=action.get("prefer_name"),
            dry_run=dry_run,
            verify=bool(action.get("verify", args.verify)),
            interval=float(action.get("interval", 0.02)),
        )
        type_target(ns)
    elif kind == "paste":
        paste_at(
            int(action["x"]),
            int(action["y"]),
            action["text"],
            win=win,
            replace=bool(action.get("replace", False)),
            dry_run=dry_run,
        )
    elif kind == "paste_target":
        ns = argparse.Namespace(
            target=action["target"],
            text=action["text"],
            win=win,
            single=bool(action.get("single", False)),
            prefer_name=action.get("prefer_name"),
            replace=bool(action.get("replace", False)),
            dry_run=dry_run,
            verify=bool(action.get("verify", args.verify)),
        )
        paste_target(ns)
    elif kind == "press":
        press_key(action["key"], dry_run=dry_run)
    elif kind == "hotkey":
        send_hotkey(action["keys"], dry_run=dry_run)
    elif kind == "wait":
        seconds = float(action.get("seconds", 1.0))
        print(f"[V2] waiting {seconds}s")
        if not dry_run:
            time.sleep(seconds)
    elif kind == "screenshot":
        screenshot(win)
    elif kind in {"done", "fail"}:
        print(kind.upper())


def run_action(args):
    action_or_sequence = load_action(args.action_json)
    if isinstance(action_or_sequence, list):
        for index, action in enumerate(action_or_sequence, start=1):
            print(f"[V2] sequence step {index}/{len(action_or_sequence)}: {action.get('action')}")
            execute_action(action, args)
    else:
        execute_action(action_or_sequence, args)


def list_windows(_args):
    for _hwnd, title in v1.find_window(""):
        print(title)


def locate_cmd(args):
    results = locate_target(args.target, win=args.win, single=args.single)
    if args.json:
        print(json.dumps({"results": results}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="Windows vision-control V2: structured, logged, whitelist desktop actions."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list-windows")
    p_list.set_defaults(func=list_windows)

    p_loc = sub.add_parser("locate")
    p_loc.add_argument("--win")
    p_loc.add_argument("--target", required=True)
    p_loc.add_argument("--single", action="store_true")
    p_loc.add_argument("--json", action="store_true")
    p_loc.set_defaults(func=locate_cmd)

    p_click_t = sub.add_parser("click-target")
    p_click_t.add_argument("--win")
    p_click_t.add_argument("--target", required=True)
    p_click_t.add_argument("--single", action="store_true")
    p_click_t.add_argument("--prefer-name")
    p_click_t.add_argument("--dry-run", action="store_true")
    p_click_t.add_argument("--verify", action="store_true")
    p_click_t.set_defaults(func=click_target)

    p_paste_t = sub.add_parser("paste-target")
    p_paste_t.add_argument("--win")
    p_paste_t.add_argument("--target", required=True)
    p_paste_t.add_argument("--text", required=True)
    p_paste_t.add_argument("--single", action="store_true")
    p_paste_t.add_argument("--prefer-name")
    p_paste_t.add_argument("--replace", action="store_true")
    p_paste_t.add_argument("--dry-run", action="store_true")
    p_paste_t.add_argument("--verify", action="store_true")
    p_paste_t.set_defaults(func=paste_target)

    p_type_t = sub.add_parser("type-target")
    p_type_t.add_argument("--win")
    p_type_t.add_argument("--target", required=True)
    p_type_t.add_argument("--text", required=True)
    p_type_t.add_argument("--single", action="store_true")
    p_type_t.add_argument("--prefer-name")
    p_type_t.add_argument("--dry-run", action="store_true")
    p_type_t.add_argument("--verify", action="store_true")
    p_type_t.add_argument("--interval", type=float, default=0.02)
    p_type_t.set_defaults(func=type_target)

    p_action = sub.add_parser("run-action")
    p_action.add_argument("action_json", help="JSON string or path to a JSON action file.")
    p_action.add_argument("--dry-run", action="store_true")
    p_action.add_argument("--verify", action="store_true")
    p_action.set_defaults(func=run_action)

    p_snap = sub.add_parser("screenshot")
    p_snap.add_argument("--win")
    p_snap.set_defaults(func=lambda args: screenshot(args.win))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
