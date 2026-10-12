# Tracker evidence review — 2026-10-12

## Confidence policy

The application separates protocol recognition, model attribution, and laboratory
verification. A catalog rule marked `validated` historically meant implementation
maturity; it is not proof of a lab-tested product. Existing and newly researched
rules are now explicitly marked **Web reference — not lab verified** until a
reviewed lab specimen is linked. Unit tests prove code behavior, not RF provenance.

`verification.level = lab_verified` requires `lab_capture_sha256` in the schema.
Promotion should also record model, firmware, receiver, pairing state, packet
examples, repeat captures, and negative controls. A hash is traceability metadata,
not an automatic certification. Only operator-reviewed rules should be promoted.
Every detection retains matched rule IDs and evidence references in its JSON
observation. Source links and compatible product families are visible in details.

## Findings and implemented coverage

| Product/family | Passive evidence | Implemented behavior |
|---|---|---|
| Chipolo ONE Spot / CARD Spot | Apple Find My support; shared Apple 004C / TLV 12 / length 19 hex format | Generic network recognition; never inferred as a specific Chipolo model |
| Chipolo POP | Supports Find My or Find Hub according to its selected configuration | Compatible-family catalog entry under either network; no invented unique bytes |
| Google Pixel Tag (2026) | Official Google product page confirms Find Hub; general Find Hub specification defines FEAA frame types 40/41 | Generic Find Hub recognition, model unknown |
| HUAWEI Tag | Official product/support information, but no sufficiently substantiated passive byte signature found | Catalog entry explicitly pending lab capture; no enabled tracker rule |
| Tile | AirGuard original implementation filters FEED service data beginning 02 00 | New experimental rule, possible tracker, model unknown |
| Chipolo own network | AirGuard original implementation uses FE33 service UUID | New experimental rule; does not identify ONE Spot/POP; firmware-dependent state bits intentionally not interpreted |

Find Hub payload checks bind length and first-byte checks to **the FEAA payload**.
They cannot borrow matching bytes or length from an unrelated service. The same
payload-scoping rule applies in desktop and mobile engines. FE2C alone means Fast
Pair capability, not a particular tracker model. Network advertising may be absent
in some device modes; a missing match is not proof that no tracker is nearby.

Primary sources, reviewed 2026-10-12:

- [Chipolo Spot support](https://support.chipolo.net/hc/en-us/articles/360020095258-How-to-use-the-Chipolo-ONE-Spot-or-CARD-Spot)
- [Chipolo POP manual](https://support.chipolo.net/hc/en-us/article_attachments/27152333956637)
- [Google Pixel Tag](https://blog.google/products-and-platforms/devices/pixel/google-pixel-tag/)
- [Google Find Hub advertising specification](https://developers.google.com/nearby/fast-pair/specifications/extensions/fmdn)
- [Huawei Tag support](https://consumer.huawei.com/cn/support/accessories/tag/)
- [Huawei Tag compatibility](https://consumer.huawei.com/cn/support/content/zh-cn15903456/)
- [AirGuard Tile detector](https://github.com/seemoo-lab/AirGuard/blob/main/app/src/main/java/de/seemoo/at_tracking_detection/database/models/device/types/Tile.kt)
- [AirGuard Chipolo detector](https://github.com/seemoo-lab/AirGuard/blob/main/app/src/main/java/de/seemoo/at_tracking_detection/database/models/device/types/Chipolo.kt)
- [OpenHaystack research](https://github.com/seemoo-lab/openhaystack)

External implementations were used as evidence for identifiers/conditions, not
copied as application source. Research entries live in `catalog/tracker_profiles.json`;
they are not all active detection rules. New passive heuristics live in
`rules/experimental/`. Review dated references again when firmware/protocols change.

## Address and company attribution

SDR advertising headers expose public/random address type (TxAdd). Random addresses
are additionally labelled static, resolvable, non-resolvable, or reserved using
their defined high bits. A BLE address must not be declared public based only on
its printed prefix. The current computer/mobile paths do not supply this metadata,
so they conservatively report unknown and skip OUI attribution.

Only confirmed public addresses receive offline 24-bit OUI lookup. The result is
an address-block registrant, not proof of the product manufacturer. The snapshot
does not implement 28/36-bit allocations. A missing lookup remains unattributed.

Advertised Bluetooth company identifiers are decoded separately. For example,
an Apple namespace can be used by a third-party Find My accessory. No tracker is
classified merely because a Huawei, Google, or Apple company identifier appears.

Registry provenance and checksum are in `catalog/registry_sources.json`. IEEE's
download endpoint returned HTTP 418 during this review, so the snapshot uses the
[Wireshark published manufacturer registry](https://www.wireshark.org/download/automated/data/).
Company IDs come from Bleak's Bluetooth SIG-derived registry. Official organization
names are retained as source data. No observed MAC addresses are uploaded for lookup.

[Bluetooth SIG address/privacy guidance](https://www.bluetooth.com/blog/enhancing-device-privacy-and-energy-efficiency-with-bluetooth-randomized-rpa-updates/)
explains why rotating/private addresses are common.

## Suggested next lab work

1. Capture each purchased model in unpaired, paired-near-owner, and separated modes.
2. Keep negative controls (phones, earbuds, televisions, generic beacons) in the test.
3. Store device labels and firmware separately from inferred classification.
4. Compare repeat sessions and only promote stable, discriminating conditions.
5. Add a directional sweep log with angle, median power, packet count, and gain.
6. Verify a hardware source sample counter before claiming lossless reception.
