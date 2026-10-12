# SDR BLE receiver: architecture, operation, and evidence

All application labels, generated comments, reports, and documentation are English.
Advertised device names and packet bytes are source evidence and are not translated.

## Receive paths

Computer Bluetooth uses the Windows controller and Bleak. The controller demodulates
the radio; the application receives advertisement reports. Windows can merge/filter
reports. The existing BTVS Wireshark shortcut observes host/controller HCI traffic,
not a raw over-the-air capture of all Bluetooth traffic.

Pluto uses its AD9363 RF receiver and existing firmware to deliver IQ through
libiio and pyadi-iio. The USB connection exposes the network URI `ip:192.168.2.1`.
No FPGA or firmware modification was made. Demodulation runs on the Windows PC.
The supported mode is receive-only legacy BLE 1M advertising on one fixed primary
channel (default channel 37, 2402 MHz). No hopping, connections, decryption, active
scan requests, or secondary-channel extended advertising is implemented.

Each IQ sample has in-phase and quadrature components: `x = I + jQ`.
The receiver translates the RF channel to baseband. At 4 MSPS it receives four
complex samples per 1 Mbps symbol, not 2.4 billion samples per second.
Int16 I plus int16 Q represents 16 MB/s before transport overhead. Saved complex64
experiment files use 32 MB/s; decoded packet exports are much smaller.

## Signal-processing chain

1. Tune Pluto to the channel with 2 MHz RF bandwidth and manual gain 40 dB.
2. Read blocks of 65,536 samples in a capture thread, normalize by 2048, and place
   them in a bounded queue of 16 blocks. Count queue overflow and read errors.
3. At 4 MSPS, apply a stateful 49-tap Hamming FIR: 650 kHz cutoff, designed
   transition width 200 kHz, group delay 24 samples. Reset state across known gaps.
4. Use the phase difference `angle(x[n] * conjugate(x[n-1]))` as a frequency
   discriminator. Search four symbol phases for advertising Access Address
   `0x8E89BED6`, allowing at most two initial address-bit mismatches.
5. Estimate frequency offset from the known address bits. Slice payload bits,
   reverse channel-dependent whitening, parse the header, and verify CRC-24/BLE.
   CRCInit is 0x555555 (reflected implementation state 0xAAAAAA).
6. Accept CRC-valid legacy packets. Parse AD length/type/value structures for
   service data, manufacturer data, service UUIDs, and local name.
7. Send packets to the shared normalizer, rule engine, signal history, and UI.

The custom decoder has no complete clock-recovery loop or full preamble validation.
It is a tested prototype, not a certified Bluetooth stack. Packet overlaps preserve
frames crossing block boundaries; known sample gaps are never stitched together.
`--no-prefilter` restores the original decoder. At 2 or 3 MSPS the original decoder
is used because the FIR configuration was validated only at 4 MSPS.

## Power and directional finding

For each decoded packet, power is `10*log10(mean(abs(IQ)**2))` over its Access
Address through CRC. It is measured on original IQ, with FIR delay compensated.
The unit is uncalibrated complex-power dBFS, not RF dBm at the antenna connector.
Clipped-sample fraction is also recorded. A less negative value means more
received energy with the same gain/settings. Noise and interference contribute.

Select one target, keep gain fixed, rotate the directional antenna slowly, and
compare several packets per direction. Reflections, body shielding, polarization,
and transmitter behavior can change readings. Signal power is not a distance meter.
Only successfully decoded packets receive power measurements; silence is not a
measured weak signal. Do not combine readings from different addresses as one target
without independent evidence, since addresses can rotate.

## App and Wireshark

`sdr_worker.py` is a separate subprocess with JSON packet/health events. The server
uses REST/WebSocket updates and throttles per-address UI events. UI units, checkpoint
records, and CSV carry source and signal unit. Computer Bluetooth uses dBm; Pluto
uses dBFS even though the compatibility JSON field is named `rssi`.

`sniff_sdr.py` writes PCAPNG with link type 256 (Bluetooth LE LL with RF header),
canonical advertising access address, decoded PDU, CRC and English packet comments.
Uncalibrated dBFS is in `frame.comment`; the RF dBm-valid flag is deliberately unset.
Timestamps are host export time, not RF arrival time. Logical BLE channel 37 maps to
RF frequency index 0 in this header. Filter with `btle` or
`btle.advertising_address == aa:bb:cc:dd:ee:ff` and add `frame.comment` as a column.

If the app is scanning via SDR, the shortcut follows new entries in its packet
journal without opening another receiver. Buffered journal writes add a short
delay. Stopping this viewer does not stop the app. Without an app SDR scan, the
shortcut owns the receiver; stop other SDR programs first. Stop via Ctrl+C or
Wireshark Stop. A persistent file remains under `data/wireshark-captures/`.

Live input uses local `TCP@` supported by installed Wireshark 4.6.8. The script
rejects Wireshark 5 for this transport; `--no-wireshark` still saves a capture.
The launcher creates a dedicated English Wireshark profile. Existing viewer windows
are not forcibly closed because they may contain unsaved captures.

## GNU Radio comparison, 2026-10-11

GNU Radio 3.10.12 was installed from Ubuntu packages in the existing WSL environment.
Two independent 10.010624-second recordings were replayed identically, with SHA256
verification, at 4 MSPS/channel 37/gain 40 dB. No capture-queue drops or read errors
were reported; hardware continuity remains unverified.

| Decoder | CRC-valid packets A | CRC-valid packets B |
|---|---:|---:|
| Original custom decoder | 1,092 | 1,243 |
| GNU Radio generic GFSK | 1,025 | 1,177 |
| GNU Radio GFSK plus FIR | 2,006 | 2,180 |
| Custom decoder plus FIR, now integrated | 2,202 | 2,346 |

Four timing-loop gains were tested on A, with/without FIR. The selected GNU Radio
gain_mu=0.175 was checked on held-out B. A same-coefficient NumPy control isolated
the filter benefit. Local FIR coefficients differ from GNU Radio firdes.low_pass
by at most approximately 2.3e-8. B improved approximately 89% over the original.

Nine synthetic cases each contain 120 unique known packets generated using GNU
Radio gfsk_mod (BT=0.5, modulation index=0.5), fractional sample offset 0.37,
random burst spacing, and a fixed random seed. No RF transmission was performed.

| Synthetic case | Original | Integrated FIR | GNU Radio + FIR |
|---|---:|---:|---:|
| Clean, nominal SNR 30 dB | 120 | 120 | 120 |
| CFO 35 kHz, SNR 20 dB | 119 | 120 | 113 |
| CFO 100 kHz, SNR 20 dB | 119 | 120 | 87 |
| CFO 150 kHz, SNR 20 dB | 94 | 120 | 0 |
| SNR 10 dB, CFO 35 kHz | 0 | 120 | 114 |
| SNR 5 dB, CFO 35 kHz | 0 | 71 | 30 |
| SNR 0 dB, CFO 35 kHz | 0 | 0 | 0 |
| Clock error 150 ppm, SNR 20 dB/CFO 35 kHz | 116 | 120 | 117 |
| Clock error 500 ppm stress test, SNR 20 dB/CFO 35 kHz | 119 | 120 | 117 |

Nominal SNR is relative to pre-interpolation modulation power and full-band added
IQ noise, not calibrated sensitivity. Framing/CRC/whitening code is shared; this
is not independent protocol conformance testing. The generic GNU Radio baseline
lacks the custom decoder's address-based CFO correction. Results do not imply
that an optimized GNU Radio BLE burst receiver would perform worse.

The production path remains custom decoding plus FIR. Live app validation returned
2,643 packets/61 addresses in 15.14 seconds with no queue overflow/read errors.
Mean decode time was 10.98 ms per 16.384 ms block. One queued block remained at stop.
WSL offline timings include IO and are not Windows live-throughput measurements.
Multiset payload overlap does not establish exact RF-event correspondence.

Numerical evidence: `docs/decoder-comparison-2026-10-11.json`.
Local IQ/logs: `data/decoder-comparison/`, excluded from Git.
Replay in the GNU Radio environment:

```sh
python3 experiments/compare_decoders.py data/decoder-comparison/real-b --repeat 3
python3 experiments/run_synthetic_suite.py
```

Record a new sample using Windows Python with the SDR idle:

```powershell
python experiments/capture_iq.py --seconds 10 --name real-c
```

## Evidence levels and manufacturer hints

See `TRACKER_RESEARCH.md`. Rule maturity is distinct from lab verification.
Web-reference matches are explicitly marked as not lab verified. A network-format
match does not prove the product model. Public SDR addresses can be checked against
the offline 24-bit OUI registry; random or unknown address types are never attributed
by prefix. Advertised Bluetooth company IDs refer to protocol namespaces and may
name an ecosystem provider rather than the physical manufacturer.

## Libraries and source map

- Analog Devices libiio/pylibiio/pyadi-iio: transport and Pluto configuration.
- NumPy: array-based demodulation; SciPy: stateful FIR and synthetic testing.
- Bleak: computer Bluetooth only. FastAPI/Uvicorn and React: app service/UI.
- GNU Radio: offline comparison and synthetic modulation, not the live backend.
- Wireshark/TShark: decoded-packet interpretation, not IQ demodulation.
- `sdr_rx.py`, `ble_filter.py`: receiver and FIR/raw-power mapping.
- `sdr_worker.py`, `sdr_backend.py`: subprocess lifecycle and app transport.
- `ble_pcapng.py`, `shared_capture.py`, `sniff_sdr.py`: capture export/sharing.
- `classifier.py`, `rules/`, `catalog/`: classification, sources, identity hints.
- `experiments/`, `tests/`: repeatable comparisons and regression checks.

References: [BLE primer](https://www.bluetooth.com/bluetooth-le-primer/),
[pyadi-iio](https://github.com/analogdevicesinc/pyadi-iio),
[libiio](https://analogdevicesinc.github.io/libiio/main/index.html),
[GNU Radio GFSK](https://github.com/gnuradio/gnuradio/blob/main/gr-digital/python/digital/gfsk.py),
[Wireshark pipes](https://wiki.wireshark.org/CaptureSetup/Pipes).

Valid CRC proves internal packet consistency, not that all packets were received.
Hardware sample continuity requires a verified source counter; the firmware name
containing "timestamping" is not sufficient proof that such a counter was checked.
