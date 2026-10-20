# SDR channel selection

The web/desktop interface offers **Fixed channel 37 Â· 2402 MHz** (default) and **Hop 37 â†’ 38 â†’ 39 Â· 10 seconds each**. Stop the scan before changing mode. The browser remembers the selection locally. No internet connection is required in field mode.

Hopping listens to one channel at a time: 2402, 2426 and 2480 MHz. Each channel gets a ten-second dwell, plus buffer-boundary and retuning overhead between dwells. Revisiting a channel takes about 30 seconds. Fixed mode is preferable for continuous hot/cold measurements; frequency-dependent propagation can change signal strength between channels.

The capture thread destroys the previous receive buffer before tuning and discards one fresh buffer for settling. Each queued block carries its acquisition channel and tuning epoch. The consumer recreates the FIR and decoder on epoch changes, including revisits after queue losses, so whitening and partial-packet state cannot cross tuning boundaries. Packet exports retain each packet's channel.

Health includes the current channel/frequency, switch count, intentional settling discard count, retuning time, per-channel processed sample and packet totals, and the latest 120 transitions. Intentional settling discards are separate from host queue losses. The SDR source does not expose a sample counter; zero host drops does not prove uninterrupted RF reception.

API: `POST /api/scan/start` accepts `sdr_scan_mode: "fixed37"` (default) or `"hop"` when `source: "sdr"`. Other values are rejected. The standalone receiver supports `--hop`; fixed `--channel` remains available for diagnostics. Board sampling remains 2 MSPS with 2 MHz RF bandwidth and fixed 40 dB receive gain.

Validation results are recorded in `banana-pi-hopping-validation-2026-10-20.json`. Sequential RF runs are not a controlled sensitivity comparison: advertisers and packet schedules can change between runs.

## Banana Pi comparison (2026-10-20)

Each mode was observed for 180 seconds after startup; receiver wall time was 183.96 s fixed and 180.55 s hopping (startup/API/stop overhead differs). Fixed: 45,268 valid packets, 79 addresses, 159.68% CPU relative to one core, 169.72 MiB maximum combined app/worker RSS. Hopping: 38,286 valid packets, 96 addresses, 159.91% CPU, 172.82 MiB RSS. Both had zero host queue losses and zero read errors. CPU measurements cover the app and SDR worker, not total system utilization.

Hopping decoded 14,358 / 11,409 / 12,519 packets on channels 37 / 38 / 39. Seventeen transitions took 1.042 s in total (61 ms average); 1,114,112 settling samples were deliberately discarded. Transitions occurred about every 10.08 s including buffer alignment and retuning. Maximum queue ages were 725 ms fixed and 676 ms hopping. Median local HTTP status latency was 15 / 20 ms, but maxima reached 718 / 956 ms. These HTTP measurements are on the board, not phone end-to-end latency; neither mode guarantees instantaneous updates.

Windows validation: full suite 69 passed, 8 native-platform skips; the expanded three-channel PCAP test subsequently passed all 4 cases. TypeScript and both Vite builds passed. Banana Pi: 38 decoder, native FIR and hopping tests passed. Local UI selection and live board channel display were verified.
