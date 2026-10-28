---
name: windows-vision-control
description: Locate visible Windows desktop controls with Qwen vision, then click physical screen coordinates or paste text. Use for taskbar, tray, desktop and app controls when visual interaction is needed.
---

# Windows Vision Control

Run the bundled scripts relative to this skill directory. Windows, Python and the dependencies in requirements.txt are required. See README.md for setup and data handling.

## Workflow

1. Inspect a fresh screenshot of the intended desktop or window.
2. Locate the requested visible target. Full-screen mode covers the primary monitor, including taskbar and tray; open hidden icons first if needed.
3. Inspect returned coordinates against the screenshot. Stop on UNSTABLE or ambiguous targets; reobserve after any window movement or layout change.
4. Perform one intended action, then capture and inspect the result before claiming success.

Use physical pixels. Window captures use DwmGetWindowAttribute and include the physical window offset. Use mouse.py for DPI-aware input. Do not assume a focus border means a text cursor is active. For fragile Chinese inputs, confirm focus before clipboard paste; pasting does not press Enter.

## Commands

```powershell
python scripts/win_control.py locate --target "system tray application icon" --single
python scripts/win_control.py locate --win "Calculator" --target "number key 5" --single
python scripts/win_control.py click --x 100 --y 200
python scripts/win_control.py paste --win "Notepad" --x 100 --y 200 --text "示例文字"
python scripts/winsnap.py "Calculator"
python scripts/mouse.py pos
```

Localization sends the captured image to Alibaba Cloud DashScope using the user's API key. Coordinate-only clicks and window screenshots do not call the model. Use the installed host's permissions and the user's requested scope; this skill does not grant permission to send messages, publish content or perform unrelated actions.

## Experimental V2 wrapper

scripts/win_control_v2.py provides structured actions, action logs and dry-run input. It stops on UNSTABLE results. Important: target-based dry-run still performs localization and sends a screenshot; it only suppresses the final input. Full-screen verification export is not implemented in V2. Logs may contain window titles, targets and typed text; keep runtime/ private.


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

## Pure visual fast verification

For an inspected stable layout and authorized reversible clicks, prefer
`scripts/visual_sequence.py observe/run` with local RapidOCR checkpoints; see
README.md for the plan schema and optional requirements-vision.txt. Inspect the
new observation, use window-relative physical coordinates and tight single-line
result ROIs, start by verifying the initial display, then verify each short
segment. Do not treat pixel changes alone as semantic success. Never skip a failed
checkpoint or replay uncertain actions. On mismatch inspect the saved local failure
image and observe again; there is no automatic upload or retry. This flow uses no
UIA and does not use the older paste/type caret checks. Keep raw text/reports private.

If `runtime/vision-runtime.json` exists locally, its `python` field identifies the optional OCR interpreter. Use that interpreter for visual_sequence.py. This machine-local config stays under ignored runtime/.
