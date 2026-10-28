import argparse
import ctypes
import subprocess
import sys
import time
from pathlib import Path
from ctypes import wintypes

OPENCLAW_SCRIPTS = str(Path(__file__).resolve().parent)
QWEN_LOCATE = OPENCLAW_SCRIPTS + r"\qwen_locate.py"
MOUSE = OPENCLAW_SCRIPTS + r"\mouse.py"


def _user32():
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32


def find_window(title_part: str):
    user32 = _user32()
    enum_proc_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    matches = []

    def enum_proc(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value
        if title_part.lower() in title.lower():
            matches.append((hwnd, title))
        return True

    user32.EnumWindows(enum_proc_type(enum_proc), 0)
    return matches


def activate_window(title_part: str):
    user32 = _user32()
    matches = find_window(title_part)
    if not matches:
        raise SystemExit(f"[NOT FOUND] window containing: {title_part}")
    hwnd, title = matches[0]
    user32.ShowWindow(hwnd, 5)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    print(f"[Window] {title}")
    return hwnd, title


def click_xy(x: int, y: int):
    subprocess.run([sys.executable, MOUSE, "click", str(x), str(y)], check=True)


def set_clipboard_text(text: str):
    # PowerShell handles Unicode clipboard text more reliably in this environment.
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
        input=text, text=True, encoding="utf-8", check=True,
    )


def send_ctrl_v():
    user32 = _user32()
    keyup = 0x0002
    vk_control, vk_v = 0x11, 0x56
    user32.keybd_event(vk_control, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk_v, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk_v, 0, keyup, 0)
    user32.keybd_event(vk_control, 0, keyup, 0)


def send_ctrl_a_backspace():
    user32 = _user32()
    keyup = 0x0002
    vk_control, vk_a, vk_back = 0x11, 0x41, 0x08
    user32.keybd_event(vk_control, 0, 0, 0)
    user32.keybd_event(vk_a, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk_a, 0, keyup, 0)
    user32.keybd_event(vk_control, 0, keyup, 0)
    time.sleep(0.1)
    user32.keybd_event(vk_back, 0, 0, 0)
    time.sleep(0.05)
    user32.keybd_event(vk_back, 0, keyup, 0)


def locate(args):
    cmd = [sys.executable, QWEN_LOCATE]
    if args.win:
        activate_window(args.win)
        cmd.extend(["--win", args.win])
    if args.single:
        cmd.append("--1")
    cmd.append(args.target)
    subprocess.run(cmd, check=True)


def click(args):
    click_xy(args.x, args.y)


def paste(args):
    if args.win:
        activate_window(args.win)
    click_xy(args.x, args.y)
    time.sleep(0.25)
    if args.replace:
        send_ctrl_a_backspace()
    set_clipboard_text(args.text)
    time.sleep(0.15)
    send_ctrl_v()
    print("[Pasted] text placed on clipboard and Ctrl+V sent; no Enter was pressed.")


def main():
    parser = argparse.ArgumentParser(description="Windows physical-pixel visual control helper.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_loc = sub.add_parser("locate")
    p_loc.add_argument("--win", help="Window title substring for window screenshot mode.")
    p_loc.add_argument("--target", required=True, help="Visual target description.")
    p_loc.add_argument("--single", action="store_true", help="Use one Qwen run.")
    p_loc.set_defaults(func=locate)

    p_click = sub.add_parser("click")
    p_click.add_argument("--x", type=int, required=True)
    p_click.add_argument("--y", type=int, required=True)
    p_click.set_defaults(func=click)

    p_paste = sub.add_parser("paste")
    p_paste.add_argument("--win", help="Window title substring to activate first.")
    p_paste.add_argument("--x", type=int, required=True)
    p_paste.add_argument("--y", type=int, required=True)
    p_paste.add_argument("--text", required=True)
    p_paste.add_argument("--replace", action="store_true", help="Ctrl+A and Backspace before paste.")
    p_paste.set_defaults(func=paste)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
