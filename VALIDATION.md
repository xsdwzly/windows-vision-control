# Publication validation — 2026-10-28

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

Not validated in this release: live DashScope requests, localization accuracy/cost/latency, real tray clicks, mixed-DPI/multiple monitors, administrator windows, and V2 clipboard/typing workflows. Historical local accuracy claims are not release acceptance evidence.
