# Repository and reproducible setup

- Repository: https://github.com/boozies12-jpg/airtug-detector
- Remote: `origin`
- HTTPS clone: `https://github.com/boozies12-jpg/airtug-detector.git`
- SSH clone: `git@github.com:boozies12-jpg/airtug-detector.git`
- Main branch: `main`
- Integration branch: `codex/sdr-tracker-evidence-stable-lists`
- Base commit: `954cfa79590926f3e53ccc3cd8507e04dfdba7ab`
- Current local checkout: `C:\Users\User\Documents\ChatGPT\sdr_ble_didective\airtug-detector`

The integration branch includes the desktop/mobile source, tracker rules and
registry snapshots, SDR receiver, Wireshark bridge, launcher scripts, experiments,
tests, dependency manifests, and English documentation. Inspect the exact saved
revision with `git log -1 --oneline` and `git status --short`.

Raw captures, observed-device session logs, virtual environments, downloaded DLLs,
node_modules, and generated web builds are excluded. They are runtime/private data
or reproducible dependencies, not application source. Numerical decoder-comparison
results are versioned without the raw per-device packet recordings.

## Restore on Windows

```powershell
git clone --branch codex/sdr-tracker-evidence-stable-lists https://github.com/boozies12-jpg/airtug-detector.git
cd airtug-detector
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-sdr.txt
npm ci
npm run build
.\start_tracker.cmd
```

For Pluto, obtain the Windows x64 runtime from the official
[libiio v0.26 release](https://github.com/analogdevicesinc/libiio/releases/tag/v0.26)
and extract DLLs to `vendor/libiio-0.26/Windows-VS-2022-x64`, or set `PLUTO_DLL_DIR`
to the extracted directory. Connect Pluto; the default USB-network URI is
`ip:192.168.2.1`. The application is at http://127.0.0.1:41732/ .

Run `install_shortcuts.ps1` to create the app and SDR Wireshark desktop shortcuts.
`sniff_sdr.cmd` opens live Wireshark 4.x, sharing an active app SDR scan when possible.
The existing BTVS computer-Bluetooth shortcut is independent and unchanged.

The launchers prefer `.venv` inside this checkout and also support the current
workspace's parent `.venv`. GNU Radio is only needed for offline experiments:
the existing Ubuntu/WSL environment contains package version 3.10.12. It is not
required to launch the Windows app.

## Validation

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --experimental-strip-types --test tests/device_order.test.mjs
npx tsc --noEmit
npm run build
```

Hardware checks in `experiments/` are explicit and do not run during pytest.
The branch does not change the main-branch APK release workflow or trigger its
main-branch publishing path until explicitly merged.
