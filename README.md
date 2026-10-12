# Windows BLE Tracker Search — Security Pilot Application

Pilot application for operators searching for Bluetooth Low Energy (BLE) tracking accessories (Apple Find My / AirTag, Google Find Hub / Xiaomi Tag, and provisional accessory formats) among physical objects, luggage, and inspection areas.

Developed strictly in accordance with `CURSOR_BLE_PRODUCT_SPEC.txt` (Revision 3).

---

## Key Capabilities

1. **Continuous Active BLE Scanner**:
   - Continuous scanning without periodic stop/restart cycles.
   - Captures both manufacturer data and delayed scan responses (local names).
   - Clear adapter off / missing error handling and recovery.

2. **Extensible Declarative Rule Catalog**:
   - Zero-code rule addition via versioned JSON files under `rules/`.
   - Validated against JSON schema (`rules/schema.json`).
   - Supports Google Find Hub (`FEAA`), Apple Find My type-12 offline broadcast, advertised name correlations (`Xiaomi Tag`), and experimental signatures (`FD44` 21-byte provisional rule).

3. **Responsive Signal Feedback & Stationary Summaries**:
   - **Main Locating Gauge**: Driven by the latest completed 250ms signal group with median smoothing; values older than 3 seconds are visibly held as historical.
   - **Secondary 20-Second Stationary Summary**: Median of signal groups over a 20-second window, reporting group count and temporal coverage.
   - **Historical Trend (20s vs previous 20s)**: Requires ≥3 groups spanning ≥10s in both windows. Classifies as `Stronger` (≥ +4 dB), `Weaker` (≤ -4 dB), or `Stable`.
   - **Throttled Sparse Audio Cues**: Throttled to at most 1 brief audio cue per second on fresh signal groups. Pitch scales with RSSI; never continuously beeps on stale data.

4. **Continuous Persistence & Safe Export**:
   - Automatically creates an immutable local session on **Start Scan**.
   - Continuous append-only logging of observations and operator actions.
   - Export to JSONL or sanitized CSV (with Excel formula injection protection).
   - Checkpoint measurements for comparing stationary signal readings across inspection positions.

---

## Architecture & Project Structure

- `src/domain/models.py`: Domain models, enums, normalized BLE records, and classification results.
- `src/domain/normalizer.py`: Normalization boundary (4-char company IDs, 16-bit UUID normalization, Apple record parsing with bounds checking).
- `src/domain/classifier.py`: Extensible JSON rule catalog, dependency graph resolver, and deterministic classifier engine.
- `src/domain/signal_processor.py`: 250ms monotonic-time bucketing, freshness state machine, and trend computation.
- `src/domain/session_manager.py`: Session storage, audit log, and safe CSV/JSONL export.
- `src/domain/acquisition.py`: Acquisition orchestrator coordinating Bleak BLE scanning, Demo feeds, and WebSocket events.
- `src/api/server.py`: FastAPI HTTP REST endpoints and WebSocket server.
- `src/App.tsx`: Modern, touch-ready operator UI built with React and Tailwind CSS.
- `rules/`: Declarative JSON rules organized into `protocols/`, `brands/`, and `experimental/`.
- `tests/`: Comprehensive regression and load test suites.

---

## Running the Application Locally

### 1. Install Backend & Frontend Dependencies
```bash
pip install -r requirements.txt
npm install
```

### 2. Start the Backend Server
```bash
python3 -m uvicorn src.api.server:app --host 0.0.0.0 --port 41730
```

### 3. Start the Frontend Dev Server
```bash
npm run dev
```

The web application will be accessible at:
```
http://localhost:41732
```

---

## Running Tests
Run all unit, regression, timing, and throughput load tests:
```bash
python3 -m pytest tests/
```
# Desktop SDR receiver option

For the Hebrew implementation walkthrough and desktop shortcut instructions,
see [SDR BLE guide](docs/SDR_BLE_GUIDE.md). Run `python sniff_sdr.py` for live
Wireshark 4.x reception or `python sniff_sdr.py --no-wireshark --seconds 30` to
save a PCAPNG. Captures are saved in `data/wireshark-captures/`. Power is stored
as dBFS in packet comments, not falsely labeled as RF dBm.

The desktop UI now has a **Scan source** selector: Computer Bluetooth or Pluto
SDR (single fixed channel 37, 2402 MHz). Stop the current scan before changing
sources. Both paths use the existing normalizer, rule catalog, candidate list,
signal processor, target gauge, checkpoints, and export.

For SDR, install `requirements-sdr.txt` and provide the official libiio v0.26
Windows x64 DLLs in `vendor/libiio-0.26/Windows-VS-2022-x64`, or set
`PLUTO_DLL_DIR` to their directory. Release:
https://github.com/analogdevicesinc/libiio/releases/tag/v0.26 . Build the frontend
with `npm ci` and `npm run build`, then run the existing Python entry point.

Computer readings use dBm; SDR readings use uncalibrated complex-power dBFS at
fixed gain 40 dB. The legacy `rssi` JSON field must be interpreted together with
`signal_unit`; it is not calibrated RSSI for SDR. Units and source are saved in
observations, checkpoints and CSV. Raw decoded SDR packets and capture-health
reports are also saved under `data/sdr-captures/` (ignored by Git).

SDR capture is receive-only and runs in a separate process. It supports legacy
BLE 1M advertising, not extended advertising or all three primary channels at
once. It cannot solicit names through active scan requests. Host queue drops
and read errors are monitored; hardware sample continuity remains unverified
without a source sample counter. Valid CRC does not prove lossless reception.

Run `python -m pytest -q` for tests. `python check_live_backends.py` explicitly
uses the attached hardware to test Computer -> SDR -> Computer and writes its
report to `data/backend-check.json`. Stop other SDR apps before running it.

The 4 MSPS receiver now uses a validated 49-tap Hamming channel FIR before
demodulation (650 kHz cutoff). Packet power is still measured on original IQ,
with the FIR group delay compensated. SciPy is required by `requirements-sdr.txt`.
`--no-prefilter` on `python -m src.domain.sdr_rx` restores the original decoder.
The app and SDR Wireshark shortcut use the filtered receiver automatically.

Same-IQ comparisons against GNU Radio 3.10.12 are reproducible using
`experiments/compare_decoders.py` in the installed Ubuntu/WSL environment.
See `docs/SDR_BLE_GUIDE.md` for methodology, limitations, and results, and
`docs/decoder-comparison-2026-10-11.json` for numerical evidence. The tested
generic GNU Radio GFSK path did not outperform the filtered custom receiver,
so GNU Radio remains an offline comparison dependency rather than the live backend.

Device lists auto-order for the first 60 seconds of a scan, then keep their positions.
Use **Sort & filter → Apply & lock** to take a new snapshot by signal, name, or last
seen, with name/company/address, minimum signal, and recency filters. Filters are
snapshots too; readings continue updating without rows disappearing as RSSI changes.
Unfiltered new devices append. Pinning takes effect on the next explicit sort.

Classification details distinguish **Web reference — not lab verified** from lab
verification. The research catalog documents Chipolo Spot/POP, Pixel Tag, Huawei
Tag, Tile and Chipolo own-network coverage without claiming unsupported models.
Address registrants and advertised company IDs are separate, qualified hints.
See [research and evidence policy](docs/TRACKER_RESEARCH.md),
[English receiver guide](docs/SDR_BLE_GUIDE.md), and
[Git details and setup](docs/GIT_AND_SETUP.md).
