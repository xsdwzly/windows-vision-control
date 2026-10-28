# Validation history — 2026-10-28

## Current release summary

- 16 offline regression tests and Python compilation pass.
- Window ambiguity/staleness, target ambiguity and text-focus rejection paths are covered offline.
- Pure visual checkpoint execution passed a Windows Calculator positive test and
  a wrong-expected-value negative test; timings and limits are recorded below.
- No private images, logs, API keys or local interpreter configuration are published.
- Mixed DPI, arbitrary app accuracy, real IME candidate handling and browser GUI
  execution through WVC remain unvalidated.

## Initial portable publication (before the optimizations below)

- Python compilation passed for all scripts and tests (Python 3.13 on Windows).
- V1 and V2 command help loaded; pywin32, Pillow and PyAutoGUI imports passed.
- Skill metadata validation passed.
- Five offline regression tests passed: retained window handle; dynamic primary dimensions; updated geometry after window move/resize; V2 blocks UNSTABLE localization; missing API key does not open private config.
- Read-only physical mouse position query succeeded. No automated click was performed for this release.
- Publication uses an explicit source-file allowlist; screenshots, logs, caches and credentials are excluded.

Run offline tests on Windows:

```powershell
python -m unittest discover -s tests -v
```

Not validated at initial publication: live DashScope requests, localization accuracy/cost/latency, real tray clicks, mixed-DPI/multiple monitors, administrator windows, and V2 clipboard/typing workflows. Historical local accuracy claims are not release acceptance evidence.


## Local optimization validation — 2026-10-28

Eight offline regression tests and Python compilation passed after window/text guards.
New cases cover duplicate windows, movement during a model request, ambiguous targets,
and blocked replacement/paste when focus validation fails. These are mocked failure
paths, not live desktop/IME acceptance. No new online model or business app test was run.

## Pure visual checkpoint validation — 2026-10-28

- 16 offline regression tests, compilation and diff whitespace checks passed.
- Optional OCR runtime: isolated Python 3.13 venv, RapidOCR 3.10.0, ONNX Runtime 1.31.1.
- Windows Calculator: initial 0, clear 0, 13654, 7894, final 21548 verified
  using only screenshot pixels. Twelve mouse clicks and five local checkpoints
  completed in 4.925 seconds inside the runner, excluding observation/coordinate
  preparation and dependency setup. Each checkpoint took 0.273–0.481 seconds.
- Checkpoints sampled two matching frames and cached unchanged images: five OCR
  calls total. Final image was visually inspected separately.
- Live negative test expected 999 while display was 21548: runner stopped with
  zero clicks, skipped the later clear action and saved failure.png/report.json.
- No UIA or cloud calls in this runner. This validates one Calculator layout,
  not generic app/Chinese-text accuracy, all DPI scales, occlusion recovery or
  licensing/production readiness. Old Qwen localization latency is unchanged.
