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
