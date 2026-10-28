# Windows Vision Control

A Windows desktop-control skill built around Qwen3-VL visual grounding and DPI-aware mouse input. It can locate visible controls on the primary desktop, including the taskbar and system tray, then click or paste at physical coordinates.

This is an independent skill and script bundle, not an OpenAI Computer Use modification or a Microsoft product. It does not provide an MCP server.

## 安装与使用

需要 Windows 10/11、Python 3.10+。将整个仓库放进你的技能目录（文件夹名 windows-vision-control），或作为普通 Python 工具运行。

```powershell
git clone https://github.com/xsdwzly/windows-vision-control.git
cd windows-vision-control
python -m pip install -r requirements.txt
$env:QWEN_API_KEY = "YOUR_DASHSCOPE_API_KEY"
python scripts/win_control.py locate --target "托盘里的千牛图标" --single
```

也支持 DASHSCOPE_API_KEY 环境变量。不要把真实密钥写入代码或提交到 Git。

定位只返回坐标，不自动点击。先根据最新截图核对位置，再运行：

```powershell
python scripts/win_control.py click --x 100 --y 200
python scripts/win_control.py paste --win "记事本" --x 100 --y 200 --text "示例文字"
```

窗口截图与鼠标位置：

```powershell
python scripts/winsnap.py --list
python scripts/winsnap.py "记事本"
python scripts/mouse.py pos
```

## 数据与费用

视觉定位会将所选窗口截图或主屏截图发送至阿里云 DashScope，调用 qwen3-vl-plus，可能产生服务费用。截图可能包含私人内容，定位前请检查可见画面。直接坐标点击和窗口截图不调用视觉服务。没有附带任何 API key，也不会自动读取 OpenClaw 的私人配置。

截图和日志默认保存到 runtime/，可用 WVC_OUTPUT_DIR 指定其他目录；已加入 Git 忽略。V2 日志可能包含目标名称、窗口标题与输入文字，请勿公开。

## 实现与边界

- Qwen 输出归一化框，换算成物理像素；支持全屏及窗口模式。
- 多轮定位聚合与分歧警告；窗口移动或变化会使本轮定位失效。点击后通过观察或可选本地 OCR 检查结果。
- 主屏截图尺寸动态获取；窗口边界优先采用 DWM。
- 提供 V1 简单封装、实验性 V2 结构化动作、独立截图和鼠标脚本。
- V2 的目标点击 dry-run 仍会调用模型并上传截图；只跳过最终输入。
- V2 目前没有全屏验证截图导出，--verify 只保存指定窗口截图，不自动判断成功。
- 窗口标题匹配多个窗口时停止；遮挡、同尺寸布局变化和小图标仍可能导致误定位。
- 尚未完成多显示器、混合 DPI、管理员窗口和真实千牛托盘的发布版本验收。不要将历史准确率或速度当作通用保证。

## 发布验证

见 VALIDATION.md。原始来源为作者自用 windows-vision-control 与 qwen-vl-position 脚本；公开版移除了个人路径、私人配置读取、截图与日志，并打包必要脚本。早期发布时保留了原安装；本机后续安装和验收记录见集中项目记忆，公开仓库不包含这些私人记录。

当前未声明开源许可证；公开可浏览不等于授予任意再分发许可。


## Window and text guards (2026-10-28)

Window title queries must match exactly one visible window. Window localization binds
that handle, title and physical rectangle; movement/replacement during any model
request aborts instead of combining stale coordinates. V2 window target actions
recheck geometry, foreground and point ownership before input. These checks cannot
eliminate the final operating-system scheduling race or detect every layout change.
Raw coordinate clicks and full-screen actions have no window binding.

V1 paste and V2 paste/type require a Win32 text caret and reject active/read-error
IMM composition before clearing or sending text. They do not cancel candidates or
switch keyboard layouts. TSF-only/custom editors may not expose enough state;
IMM checks do not guarantee detection of all modern IME candidate windows. Inspect
focus and resulting text; a successful key injection is not content verification.
Multiple returned targets require a unique target/prefer-name; no default first match.

## Pure visual checkpoints (optional)

`scripts/visual_sequence.py` runs inspected, bounded click segments in one Python
process and verifies a tight, single-line result region with local RapidOCR.
It never reads UIA, editor values or app internals and never sends verification
images to a cloud model. Model/dependency setup may require downloads first.

Install optional dependencies with `python -m pip install -r requirements-vision.txt`.
A separate virtual environment is recommended. Then:

```powershell
python scripts/visual_sequence.py observe --win "Calculator" --out runtime/observation
# Inspect runtime/observation/observation.png, then author a plan from that image.
python scripts/visual_sequence.py run --plan runtime/plan.json --observation runtime/observation/observation.json --out runtime/result
```

Plan example (example coordinates only; replace from the fresh observation):

```json
{"segments":[
  {"points":[],"roi":[10,80,300,140],"expect":"0","mode":"integer"},
  {"points":[[50,300],[100,300]],"roi":[10,80,300,140],"expect":"12","mode":"integer"}
]}
```

All coordinates are physical pixels relative to the observed window. Begin with
an empty-point checkpoint to verify the initial screen. Use short reversible
segments only, at most 20 clicks each. Every segment requires an exact expected
single-line string. Integer mode only removes correctly grouped thousands commas;
it does not fix OCR mistakes. Two consecutive matching frames with OCR confidence >=0.90
are required; pixel-identical frames reuse the previous local OCR result. A timeout, geometry/focus/point-owner change or other failure stops
all later clicks and writes a local report and, if possible, failure screenshot.
No automatic click retries, no automatic cloud fallback. On success only the
final full-window screenshot and compact report are saved, not every intermediate
frame. The 120-second observation expiry includes OCR initialization; warm the
model before observing if initialization/downloads are slow. `--dry-run` checks
the plan and window without clicks, OCR initialization or cloud requests.

OCR confidence is not a correctness guarantee. Wrong but consistently recognized
text can still pass. Same-size layout changes and the small interval between
validation and input remain limitations. Pillow region capture reduces the data
processed by OCR, but capture internals may still read a larger screen area.
