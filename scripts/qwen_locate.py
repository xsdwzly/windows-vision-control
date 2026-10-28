"""Qwen3-VL 视觉定位工具 — 全屏/窗口截图 + Qwen3-VL-Plus grounding + 中位数稳健聚合
用法:
  python qwen_locate.py "计算器 数字键1 数字键5"     # 全屏定位
  python qwen_locate.py --win 计算器 "数字键1 数字键5"  # 窗口截图定位（先用winsnap）
  python qwen_locate.py --1 "目标"                  # 单次模式

策略:
- Qwen3-VL-Plus, 归一化0-1000→像素坐标
- vl_high_res=False + 锁分辨率省token
- 多轮结果: 中位数聚类 + 离群剔除; 两两最大偏差>30px 标记 UNSTABLE
- --win 模式: DwmGetWindowAttribute 精确窗口截图→定位→输出屏幕绝对坐标
"""
import base64, json, os, sys, re, urllib.request, math, subprocess, ctypes
import win32gui, win32con
from pathlib import Path
from PIL import ImageGrab
ctypes.windll.user32.SetProcessDPIAware()

DASHSCOPE_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
MAX_DEVIATION = 10
OUTLIER_PX = 25       # 与中位数距离超过此值视为离群点
UNSTABLE_PX = 30      # 全部点两两最大偏差超过此值标记 UNSTABLE
OUTPUT_DIR = Path(os.environ.get("WVC_OUTPUT_DIR", Path(__file__).resolve().parent.parent / "runtime"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
SCREENSHOT_PATH = str(OUTPUT_DIR / "screenshot.jpg")

def get_api_key():
    return os.environ.get("QWEN_API_KEY", "") or os.environ.get("DASHSCOPE_API_KEY", "")

def screenshot_ps(w=None, h=None, quality=80):
    image = ImageGrab.grab()
    image.convert("RGB").save(SCREENSHOT_PATH, quality=quality)
    return image.size

def get_physical_rect(hwnd):
    """用 DwmGetWindowAttribute 获取物理像素窗口边界"""
    dwmapi = ctypes.windll.dwmapi
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]
    r = RECT()
    if dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r)) == 0:
        return r.left, r.top, r.right, r.bottom
    # 回退
    gr = win32gui.GetWindowRect(hwnd)
    return gr[0], gr[1], gr[2], gr[3]

def find_window(title_substr):
    results = []
    def cb(hwnd, r):
        if win32gui.IsWindowVisible(hwnd):
            t = win32gui.GetWindowText(hwnd)
            if title_substr.lower() in t.lower():
                rect = get_physical_rect(hwnd)
                w, h = rect[2]-rect[0], rect[3]-rect[1]
                if w > 30 and h > 20: results.append((hwnd, t, rect))
        return True
    win32gui.EnumWindows(cb, results)
    return results

def screenshot_window(x, y, w, h):
    ImageGrab.grab(bbox=(x, y, x+w, y+h)).convert("RGB").save(SCREENSHOT_PATH, quality=80)

def call_qwen3(targets, screen_w, screen_h):
    api_key = get_api_key()
    if not api_key: raise RuntimeError("未找到 QWEN_API_KEY")
    with open(SCREENSHOT_PATH, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode()
    total_px = screen_w * screen_h
    prompt = f"在这张{screen_w}x{screen_h}截图中找到以下目标，输出归一化坐标(0-1000)的紧密bbox，bbox应仅包裹目标的文字/图标本身：\n\n{targets}\n\n格式：|object_ref_start|名称|object_ref_end| |box_start| (x1,y1),(x2,y2) |box_end|"
    body = {"model": "qwen3-vl-plus", "input": {"messages": [{"role": "user", "content": [{"image": f"data:image/jpeg;base64,{img_b64}"}, {"text": prompt}]}]}, "parameters": {"vl_high_resolution_images": False, "min_pixels": total_px, "max_pixels": total_px}}
    req = urllib.request.Request(DASHSCOPE_URL, data=json.dumps(body).encode(), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
    resp = urllib.request.urlopen(req, timeout=90)
    r = json.loads(resp.read())
    tok = r.get("usage", {}).get("input_tokens", 0)
    content = "".join(part.get("text", "") for part in r["output"]["choices"][0]["message"]["content"]) if isinstance(r["output"]["choices"][0]["message"]["content"], list) else r["output"]["choices"][0]["message"]["content"]
    pattern = r'\|object_ref_start\|\s*(.+?)\s*\|object_ref_end\|\s*\|box_start\|\s*\((\d+),\s*(\d+)\)\s*,\s*\((\d+),\s*(\d+)\)\s*\|box_end\|'
    matches = re.findall(pattern, content)
    if not matches:
        m2 = re.findall(r'\|object_ref_start\|\s*(.+?)\s*\|object_ref_end\|\s*\|box_start\|\s*\((\d+),\s*(\d+)\)\s*\|box_end\|', content)
        matches = [(n,x,y,x,y) for n,x,y in m2]
    if not matches: return None, content[:300], tok
    results = {}
    for name, x1, y1, x2, y2 in matches:
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        name = name.strip()
        px1 = int(x1*screen_w/1000); py1 = int(y1*screen_h/1000)
        px2 = int(x2*screen_w/1000); py2 = int(y2*screen_h/1000)
        results[name] = {"name": name, "cx": (px1+px2)//2, "cy": (py1+py2)//2}
    return results, None, tok

def locate(targets, mode="full", single_pass=False, window_name=None):
    sys.stdout.reconfigure(encoding='utf-8')
    win_x, win_y = 0, 0
    if mode == "win" and window_name:
        wins = find_window(window_name)
        if not wins: print(f"[ERROR] 未找到: {window_name}"); return {}
        hwnd, title, (left, top, right, bottom) = wins[0]
        win_w, win_h = right-left, bottom-top
        win_x, win_y = left, top
        print(f"[Window] {title}  ({left},{top}) {win_w}x{win_h}")
        screenshot_window(left, top, win_w, win_h)
        cap_w, cap_h = win_w, win_h
    else:
        cap_w, cap_h = screenshot_ps()

    screen_w, screen_h = cap_w, cap_h
    print(f"[Screenshot] {screen_w}x{screen_h}")

    max_runs = 1 if single_pass else 3
    all_runs, tok_total = [], 0
    for run in range(1, max_runs + 1):
        label = "Single Pass" if single_pass else f"Run {run}/{max_runs}"
        print(f"\n--- {label} ---")
        if run > 1:
            # 2026-08-25 v2 修复: 每轮重新截图 + 每轮更新窗口偏移。
            # 原 bug: 重截图但偏移不更新 → 窗口移动后 Run2/3 系统性错位(实测移 503px)。
            # v1 方案(共用 Run1 截图)有盲区: Run1 图本身不对(遮挡/截错)时三轮一致地错, UNSTABLE 无法拦截。
            # v2: 重截图保证每轮独立, 某轮截到坏图会与其他轮分歧 → 触发 UNSTABLE; 窗口移动则每轮对准新位置。
            if mode == "win" and window_name:
                wins = find_window(window_name)
                if wins:
                    _, _, (nx, ny, nr, nb) = wins[0]
                    win_x, win_y = nx, ny   # 关键: 偏移随窗口更新
                    screen_w, screen_h = nr-nx, nb-ny
                    screenshot_window(nx, ny, screen_w, screen_h)
                else:
                    raise RuntimeError("Target window disappeared; stopping localization")
            else:
                screen_w, screen_h = screenshot_ps()
        results, error, tok = call_qwen3(targets, screen_w, screen_h)
        if error: print(f"[WARN] {error}"); continue
        tok_total += tok if tok else 0
        # 加窗口偏移
        if win_x or win_y:
            for r in results.values(): r["cx"] += win_x; r["cy"] += win_y
        all_runs.append(results)
        if single_pass or run == 1: continue
        if run == 2:
            names = set(all_runs[0].keys()) & set(all_runs[1].keys())
            if not names: break
            md = max(max(abs(all_runs[0][n]["cx"]-all_runs[1][n]["cx"]), abs(all_runs[0][n]["cy"]-all_runs[1][n]["cy"])) for n in names)
            print(f"\nMax deviation: {md}px {'OK' if md<=MAX_DEVIATION else 'running 3rd'}")
            if md <= MAX_DEVIATION: break

    print(f"\n{'='*60}\n=== RESULTS ({len(all_runs)} runs) ===\n{'='*60}")
    names = set(); [names.update(r.keys()) for r in all_runs]
    final = {}
    unstable = False
    for name in sorted(names):
        pts = [(r[name]["cx"], r[name]["cy"]) for r in all_runs if name in r]
        if len(pts) == 1:
            avg_x, avg_y = pts[0]
        else:
            # 两两最大偏差检测(双模态/离群)
            all_spread = max(max(abs(p1[0]-p2[0]), abs(p1[1]-p2[1])) for p1 in pts for p2 in pts)
            # 中位数稳健聚合 + 离群剔除
            pts_sorted = sorted(pts, key=lambda p: (p[0], p[1]))
            med = pts_sorted[len(pts_sorted)//2]
            keep = [p for p in pts if abs(p[0]-med[0]) <= OUTLIER_PX and abs(p[1]-med[1]) <= OUTLIER_PX]
            if not keep: keep = pts
            avg_x = int(sum(p[0] for p in keep)/len(keep))
            avg_y = int(sum(p[1] for p in keep)/len(keep))
            if all_spread > UNSTABLE_PX:
                unstable = True
        rd = " | ".join([f"({p[0]},{p[1]})" for p in pts])
        print(f"\n  {name}\n    runs: {rd}\n    -> ({avg_x}, {avg_y})")
        final[name] = {"cx": avg_x, "cy": avg_y}
    if unstable:
        print(f"\n[WARN] UNSTABLE: 多轮结果分歧 >{UNSTABLE_PX}px (双模态/离群)! 勿直接点击。")
        print(f"  建议: 1) 布局网格校验(窗口尺寸不变时最可靠); 2) 异源视觉模型复核(如 openai/gpt-5.5); 3) 重跑 --1 单次取一致簇; 4) 人工核对截图")
    print(f"\nqwen3-vl-plus | Runs: {len(all_runs)} | Input tokens: {tok_total}")
    return final

if __name__ == "__main__":
    args = sys.argv[1:]
    mode = "full"; single_pass = False; window_name = None; parts = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--win" and i+1 < len(args): mode = "win"; i += 1; window_name = args[i]
        elif a == "--1": single_pass = True
        else: parts.append(a)
        i += 1
    target = "\n".join(parts) if parts else "数字键 1\n数字键 5\n数字键 9\n加号键 +"
    locate(target, mode=mode, single_pass=single_pass, window_name=window_name)
