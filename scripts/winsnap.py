"""
窗口截图工具 - pywin32 + Pillow，使用物理像素窗口边界
用法:
  python winsnap.py 计算器              # 截图并输出坐标
  python winsnap.py --list               # 列出所有窗口
  python winsnap.py 计算器 --foreground  # 先把窗口拉到前台再截图
输出: 保存PNG + 打印 WINDOW_POS=x,y,w,h
"""
import sys, os, subprocess, json
import win32gui, win32con
import ctypes
from pathlib import Path
from PIL import ImageGrab
ctypes.windll.user32.SetProcessDPIAware()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("WVC_OUTPUT_DIR", str(Path(__file__).resolve().parent.parent / "runtime"))
os.makedirs(OUT_DIR, exist_ok=True)

# DPI-aware fallback uses physical pixels.
COORD_SCALE = 1.0  # GetWindowRect 坐标 → 物理像素的缩放因子

def get_window_rect_physical(hwnd):
    """获取窗口的物理像素边界（排除阴影），不需要缩放换算"""
    # 优先用 DwmGetWindowAttribute 获取精确物理像素
    import ctypes
    dwmapi = ctypes.windll.dwmapi
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    rect = RECT()
    # 9 = DWMWA_EXTENDED_FRAME_BOUNDS
    result = dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    if result == 0:  # S_OK
        return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
    # 回退：GetWindowRect × 缩放
    gr = win32gui.GetWindowRect(hwnd)
    return int(gr[0]*COORD_SCALE), int(gr[1]*COORD_SCALE), int((gr[2]-gr[0])*COORD_SCALE), int((gr[3]-gr[1])*COORD_SCALE)

def enum_windows():
    wins = []
    def cb(hwnd, results):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if t and len(t.strip()) > 0:
                rect = win32gui.GetWindowRect(hwnd)
                w, h = rect[2]-rect[0], rect[3]-rect[1]
                if w > 30 and h > 20:
                    results.append((hwnd, t.strip(), rect[0], rect[1], w, h))
        return True
    win32gui.EnumWindows(cb, wins)
    wins.sort(key=lambda x: x[1].lower())
    return wins

def find_window(title_substr):
    wins = enum_windows()
    matches = [w for w in wins if title_substr.lower() in w[1].lower()]
    return matches

def foreground(hwnd):
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
    win32gui.SetForegroundWindow(hwnd)

def snap(hwnd, title, x, y, w, h):
    """截取窗口区域，保存JPEG q=80"""
    import time
    out = os.path.join(OUT_DIR, f"snap_{int(time.time())}.jpg")
    ImageGrab.grab(bbox=(x, y, x+w, y+h)).convert("RGB").save(out, quality=80)
    return out

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding='utf-8')
    args = sys.argv[1:]

    if "--list" in args:
        for hwnd, t, x, y, w, h in enum_windows():
            print(f"  {t[:55]:55s} ({x:>5},{y:>5}) {w:>5}x{h}")
        sys.exit(0)

    foreground_flag = "--foreground" in args
    args = [a for a in args if a != "--foreground"]

    if not args:
        print("用法: python winsnap.py <窗口名> [--foreground]")
        print("      python winsnap.py --list")
        sys.exit(1)

    query = " ".join(args)
    matches = find_window(query)

    if not matches:
        print(f"[NOT FOUND] '{query}'")
        print("可用窗口:")
        for hwnd, t, x, y, w, h in enum_windows():
            print(f"  {t[:55]:55s} ({x:>5},{y:>5}) {w:>5}x{h}")
        sys.exit(1)

    if len(matches) > 1:
        print(f"匹配 {len(matches)} 个窗口:")
        for i, (hwnd, t, x, y, w, h) in enumerate(matches):
            print(f"  [{i}] {t} ({x},{y}) {w}x{h}")

        sys.exit("[AMBIGUOUS] Use a unique window title")

    hwnd, title, logical_x, logical_y, logical_w, logical_h = matches[0]
    print(f"[Window] {title}")

    if foreground_flag:
        foreground(hwnd)
        import time; time.sleep(0.3)

    x, y, w, h = get_window_rect_physical(hwnd)
    print(f"  物理像素: ({x}, {y}) {w}x{h}")
    print(f"  逻辑坐标: ({logical_x}, {logical_y}) {logical_w}x{logical_h}")

    path = snap(hwnd, title, x, y, w, h)
    print(f"  Screenshot: {path}")

    print(f"\nWINDOW_POS={x},{y},{w},{h}")
    print(f"SNAPSHOT={path}")
