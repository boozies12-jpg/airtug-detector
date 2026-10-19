# Banana Pi BLE POC deployment

## Installed device

Verified on 2026-10-18: Banana Pi BPI-M5, ARM64, about 4 GB RAM,
Armbian 24.5.1 Jammy, Python 3.10.12. A Realtek USB Wi-Fi adapter provides
wireless access. The board performs reception processing and classification;
the phone is a browser client, not the receiver.

The Pluto is reachable at `ip:10.1.0.1` over the existing Ethernet/fiber link.
The board retains its original `eth0` configuration, `10.1.0.2/24`.
The detected SDR reports PlutoSDR Rev.C, Z7010/AD9361 and firmware
`1.33.7-dirty-v0.33-4-gb912-dirty-2024.01.26_13.31`.

## Using a phone

In the workshop, connect the phone to the same Wi-Fi as the board and open
`http://192.168.1.74:41732`. This is the commissioning DHCP address and may
change; `hostname -I` on the board shows its addresses.
Select Pluto SDR and `ip:10.1.0.1`, then Start BLE Scan.
Use the browser rather than the separate native Android BLE scanner.

The NetworkManager profile `ble-poc-hotspot` is the next-boot default and provides a standalone
5 GHz network called `BLE-POC`, without a password as explicitly requested by
the operator, at `http://192.168.50.1:41732`. The previous protected profile
is preserved as `ble-poc-hotspot-protected` with autoconnect disabled.
Activate it from the board console with:

```sh
nmcli connection up ble-poc-hotspot
```

Join that Wi-Fi from the phone and accept staying connected without internet.
This adapter uses either client or access-point mode at a time. Switching
profiles disconnects an SSH session through the previous Wi-Fi network.
Return to workshop mode from the console with:

```sh
nmcli connection up ble-poc-workshop
```

Workshop autoconnect is disabled; hotspot autoconnect is enabled at priority 50.
The current workshop connection stays up until explicitly switched or rebooted.
Startup profile settings have been checked, but physical power-cycle behavior
has not yet been tested. The operator confirmed successful phone access during
a three-minute open-hotspot test, without a router or internet. Automatic
return to the workshop profile was verified afterward. The POC web service has no application authentication;
the field Wi-Fi is deliberately open. No internet port forwarding was configured
by this deployment.

## Service and files

### Switching Wi-Fi from the phone

Refresh the application and open the English "Wi-Fi & field mode" panel. It offers
a return-to-field button, a saved TDCOMM workshop shortcut, and a network-name
and password form for another open or WPA personal network. Leave the password
empty for an open network. Internet access is not required.

After requesting a client network, join that same network on the phone and
open `http://SENS-WA21-398A-0005.local:41732`, then confirm the connection within
three minutes. Hostname discovery depends on the phone and network; if it does
not work, allow recovery and reconnect to BLE-POC at the field URL. Without
confirmation, a systemd user timer returns the board to BLE-POC independently
of the web application. Switching back to field mode takes about five seconds.

Each boot still defaults to BLE-POC; modes do not alternate across power cycles.
Client profiles created by the panel have autoconnect disabled. The service
uses `BLE_WIFI_INTERFACE=wlx90de800f9259` and the sensorz user bus; lingering is
enabled with `loginctl enable-linger sensorz` so recovery timers do not require
an interactive login. Passwords are stored by NetworkManager, not in the
application's state file or response. The feature passed 49 tests on the board
(Windows: 42 passed, seven native-library tests skipped).

- Application: `/home/sensorz/ble-poc`
- Isolated environment: `/home/sensorz/ble-poc-venv`
- Service: `/etc/systemd/system/ble-poc.service`, enabled at boot
- Logs: `journalctl -u ble-poc`
- Sessions and capture health: `/home/sensorz/ble-poc/data/`
- Wi-Fi and Ethernet configuration: NetworkManager

The existing `sensorz_rf_scanner.service` was stopped and disabled to avoid
two programs controlling the receiver. Its unit and application were preserved.
Other existing services were not deliberately disabled by this deployment.
To restore the old scanner, first stop the BLE service:

```sh
sudo systemctl disable --now ble-poc
sudo systemctl enable --now sensorz_rf_scanner
```

## Rebuilding

Build the UI on the development computer with `npm run build:board`. Copy
`dist-board/` as `dist/` on the board. Also deploy `src/`, `rules/`, `catalog/`
and `tests/`; the catalog is required at startup. The regular desktop build
retains its original default source and Pluto URI.

Install `deploy/banana-pi/requirements.txt` in an isolated Python 3.10
environment. The board uses system `libiio0` 0.23 and `libad9361-0` 0.2.
The Wi-Fi hotspot additionally needs `dnsmasq-base` (installed from the
official Ubuntu ARM64 package archive).

Build the optional native filter on the board:

```sh
cc -O3 -ffp-contract=off -std=c99 -shared -fPIC \
  src/domain/fir_native.c -lm -o src/domain/libble_fir.so
OPENBLAS_NUM_THREADS=1 ../ble-poc-venv/bin/python -m pytest tests/ -q
```

The native library uses ARM NEON for the FIR and exact Hamming-distance
matching for the BLE access address. Phase is evaluated only around candidate
packets. The filter uses rate-dependent taps (49 at 4 MSPS) and maintains IQ history across blocks,
resetting on known gaps. Without the library the existing SciPy path remains
available. Binary libraries and private SSH keys are excluded from Git.

## Receiver limits

This is receive-only legacy BLE 1M on channel 37, not simultaneous coverage
of all advertising channels. Classification identifies matching formats,
not a verified physical model. SDR power is uncalibrated dBFS, not meters.
Host drop/error counters do not prove continuity inside the SDR or transport.
Check the capture health after deployment and under the intended RF load.

The application explicitly selects logical receive channel 0 (RX1 / first
receive path). Its I/Q samples are `voltage0` and `voltage1` on the ADC;
these are not two separate antennas. The UI shows the configured receive path.
There is no cable-presence detection. R1/R2 labels on a custom enclosure
must be checked against its actual wiring before treating them as RX1/RX2.

Initial ARM deployment decoded real BLE packets but dropped host samples.
After optimization, the 60.49-second live run decoded 2,172 CRC-valid packets,
with zero host drops and zero read errors. Mean decode time was 15.53 ms per
16.384 ms block; queue high water was 13 of 16 blocks, so workload margin is
limited and longer field testing remains appropriate. Five candidate addresses
matched the catalog; this is not a verified count of physical tracking products.
All 40 board tests passed; Windows passed 33 tests with seven native-library
tests skipped.

**Performance qualification remains limited:** a subsequent longer operator scan
did show host drops, despite the successful one-minute test. The additional
fused ARM FIR build passed 12 focused equivalence/decoder tests, then a fresh
180.91-second live test decoded 7,622 CRC-valid packets with zero host drops
and zero read errors. Queue high water was 6/16, with 15.84 ms average decode
time per block. Five candidate addresses and 18 other addresses were observed.
The software still lacks hardware continuity counters, and earlier losses plus
the small processing margin mean it should not be described as lossless or
fully qualified for every field workload. The latest indicator explicitly
selects RX1; physical enclosure socket wiring has not been verified.
See [commissioning report](banana-pi-validation-2026-10-18.json).


## Receiver processing update (2026-10-19)

The board service now selects `BLE_SDR_SAMPLE_RATE=2000000`; the desktop default
remains 4 MSPS. The RF channel remains 37 and analog bandwidth remains 2 MHz.
The filtered decoder supports 2/3/4 MSPS with 25/37/49-tap Hamming filters,
650 kHz cutoff and 6 microsecond group delay. This changes sampling density,
not the number of advertising channels covered. Set the environment variable
back to 4000000 and restart the service to restore the previous board rate.

CRC uses an equivalent byte lookup table; whitening masks are cached; ARM
phase decisions use an optional native implementation with nonfinite handling.
Filtered reception measures packet power only on original IQ, avoiding the
previous duplicate calculation. Tests retain the Python fallback paths.

On one saved 4 MSPS recording, the optimized 4 MSPS decoder produced exactly
the same 363 packets and 302 CRC rejections, reducing replay time from 1.97 s
to 1.21 s. Digital resampling of the same recording to 3 MSPS yielded 364
packets / 48 addresses; 2 MSPS yielded 357 packets / 47 addresses versus
363 / 48 at 4 MSPS. These are limited replay results, not a sensitivity
calibration: lower sampling can change which marginal packets decode.
Three MSPS still dropped samples during the full application workload.


The board also sets `BLE_SDR_QUEUE_BLOCKS=64` (about 32 MiB of complex IQ,
2.1 seconds capacity at 2 MSPS) to absorb brief scheduling stalls. This does
not fix sustained overload by itself. Device-list endpoints return their
already serialized payloads directly as JSON, avoiding redundant recursive
encoding while the decoder is active.

The final three-minute full-application test captured 52,687 CRC-valid packets
with zero host-dropped samples and no read errors. Queue high water was 8/64,
maximum queue age 238 ms, and no blocks remained at shutdown. Mean decoding
took 19.11 ms per 32.768 ms block. Median HTTP times over workshop Wi-Fi were
41 ms for status, 56 ms for candidates and 180 ms for other devices; their
95th percentiles were approximately 128, 200 and 245 ms. These are server
request measurements, not phone rendering measurements or a field-hotspot test.
Windows tests passed 52 with seven native tests skipped; ARM passed 59 before
the final queue-capacity and JSON-response changes. The final deployed build
was exercised by the live test. The scan was stopped afterward.

Two MSPS is a measured compromise: the replay above lost six packets net and
one address compared with 4 MSPS, while higher rates still overloaded under
live application traffic. No hardware continuity counter is available, and
longer runs in the intended RF environment remain necessary for qualification.
See [performance report](banana-pi-performance-2026-10-19.json).


## Fractional sampling update (2026-10-19)

The selected board rate is now 2.25 MSPS (`BLE_SDR_SAMPLE_RATE=2250000`),
43.75% below the original 4 MSPS. Analog RF bandwidth remains 2 MHz on
channel 37. The filter uses 29 taps (14 samples / 6.22 microseconds delay).
A native access-address matcher uses 9/4-sample symbol spacing with an
integer-start timing hypothesis at every sample; the NumPy fallback uses
identical indices. Payload decisions use the same spacing. This avoids
rounding the decoder down to 2 samples per symbol or resampling back to 2 MSPS.
Raw packet power and sample indices still refer to the original input IQ.

An initial implementation searched nine quarter-sample timing streams and
overloaded the board. It was stopped and replaced by the native matcher.
Fractional-rate tests cover packet/block alignment, raw power, bad CRC,
known sample gaps and native-versus-reference matching. A sampling increase
alone does not establish better receiver sensitivity; that requires matched
RF or replay measurements.

Final 2.25 MSPS live validation lasted 181.77 seconds: 47,603 CRC-valid
packets, zero host drops and no read errors. Mean decoding took 23.35 ms
per 29.13 ms block; queue high water was 11/64 and maximum queue age 304 ms.
One block remained at stop. Median HTTP latency was 40/47/175 ms for
status/candidates/other devices. This provides less processing margin than
2 MSPS but passed this three-minute workload. Sensitivity improvement is not
yet established, and hardware sample continuity remains unverified.
See [2.25 MSPS report](banana-pi-performance-225msps-2026-10-19.json).


## Live locating display correction (2026-10-19)

The gauge previously read the selected device from the one-second polled
lists even though WebSocket events updated the target summary separately.
`LiveTargetGauge` now owns the WebSocket and its own display state, so live
updates do not rerender the complete device lists. Snapshot monotonic timestamps
prevent delayed polling responses from overwriting newer target measurements.
The connection retries after disconnect, with polling fallback shown in the UI.
Gauge width animation is 100 ms rather than 300 ms. A short descriptive trend
compares the most recent two seconds with the preceding two seconds; it needs
at least one group in each window and does not imply physical direction or distance.
The historical 20-second trend remains separate.

During investigation, an operator scan at 2.25 MSPS had 3,473,408 host-dropped
samples out of 514,523,136 received and a maximum queue age of 2.825 seconds.
This demonstrates that the earlier three-minute pass does not qualify longer
workloads. The selected target's history had observations roughly two seconds
apart and its last observation was already 32 seconds old at inspection.
Fixing display delivery cannot manufacture new observations or remove upstream
receiver backlog. End-to-end phone latency and hotspot performance still need
measurement. The initial deployment was delayed by the board switching back
to its hotspot. Access was subsequently recovered over BLE-POC and the board
was reconnected to TDCOMM with no pending rollback timer.


## Current field-search configuration

At the operator's request the board now uses **2 MSPS**, superseding the
2.25 MSPS trial. The live locating gauge correction is installed. The gauge
ages its displayed measurement on a local timer even if network updates stop,
and automatically reconnects its WebSocket. Both phone and computer web
clients use the same live target component. Reload existing browser pages
once after deployment. Native Android scanning remains a separate path.

For hot/cold searching, select the target and read the main live gauge and
measurement age. The 20-second summary is historical and intentionally slower.
The movement trend compares two adjacent two-second windows with at least one
observation in each; sparse advertisements can leave a window empty. Movement
trend means changing signal power, not a calibrated distance or direction.
The receiver cannot supply a new measurement between successfully decoded
advertisements. A measured Xiaomi target delivered roughly one observation
every two seconds, despite low WebSocket network round-trip latency.

Final validation: 297.35 seconds of receiver capture during a five-minute
application test produced 71,116 CRC-valid packets with zero host drops and
read errors. Maximum queue age was 180 ms, high water 6/64, and zero blocks
remained at stop. Mean decode time was 18.09 ms per 32.768 ms block.
WebSocket RTT from the development computer had an 18.02 ms median; this is
not an RF-to-phone measurement. All 74 ARM tests passed, TypeScript checking
and the board frontend build passed, and the live gauge was verified in the
browser updating ahead of the device list. Diagnostic scanning was stopped.
See [live gauge validation](banana-pi-live-gauge-validation-2026-10-19.json).
