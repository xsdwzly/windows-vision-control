"""移动鼠标到指定坐标 — Win32 SetCursorPos (DPI-aware)"""
import ctypes
import sys

# 必须在任何操作前声明 DPI 无关
ctypes.windll.user32.SetProcessDPIAware()

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

def move_to(x: int, y: int):
    ctypes.windll.user32.SetCursorPos(x, y)

def click(x: int = None, y: int = None, button: str = "left"):
    import time
    if x is not None and y is not None:
        move_to(x, y)
        time.sleep(0.1)  # 2026-08-25: 光标移动后稍等，确保 hit-test 完成
    if button == "left":
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
        time.sleep(0.05)  # 2026-08-25: 按下保持，防止极短点击被 WinUI 判为抖动忽略
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
    elif button == "right":
        ctypes.windll.user32.mouse_event(0x0008, 0, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.mouse_event(0x0010, 0, 0, 0, 0)

def get_pos():
    pt = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "click":
        x, y = int(sys.argv[2]), int(sys.argv[3])
        click(x, y)
        print(f"clicked ({x}, {y})")
    elif len(sys.argv) >= 3:
        x, y = int(sys.argv[1]), int(sys.argv[2])
        move_to(x, y)
        print(f"-> ({x}, {y})")
    elif len(sys.argv) == 2 and sys.argv[1] == "pos":
        print(get_pos())
    else:
        print("Usage: python mouse.py <x> <y>")
        print("       python mouse.py pos")
        print("       python mouse.py click <x> <y>")
