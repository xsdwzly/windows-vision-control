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
- 多轮定位聚合与分歧警告，点击后需重新截图检查。
- 主屏截图尺寸动态获取；窗口边界优先采用 DWM。
- 提供 V1 简单封装、实验性 V2 结构化动作、独立截图和鼠标脚本。
- V2 的目标点击 dry-run 仍会调用模型并上传截图；只跳过最终输入。
- V2 目前没有全屏验证截图导出，--verify 只保存指定窗口截图，不自动判断成功。
- 相似窗口标题可能匹配多个窗口；务必确认目标。遮挡、界面变化和小图标可能导致误定位。
- 尚未完成多显示器、混合 DPI、管理员窗口和真实千牛托盘的发布版本验收。不要将历史准确率或速度当作通用保证。

## 发布验证

见 VALIDATION.md。原始来源为作者自用 windows-vision-control 与 qwen-vl-position 脚本；公开版移除了个人路径、私人配置读取、截图与日志，并打包必要脚本。原安装目录未修改。

当前未声明开源许可证；公开可浏览不等于授予任意再分发许可。
