import { BleClient, ScanMode, ScanResult } from '@capacitor-community/bluetooth-le';
import { Capacitor } from '@capacitor/core';
import { MobileClassifier, MobileSignalProcessor, NormalizedRecord } from './mobileEngine';
import { BleDeviceItem, AppStatus } from '../types';

export class MobileBleManager {
  private classifier = new MobileClassifier();
  private signalProcessor = new MobileSignalProcessor();
  private devices: Map<string, { record: NormalizedRecord; item: BleDeviceItem }> = new Map();
  private selectedTargetAddress: string | null = null;
  private pinnedAddresses: Set<string> = new Set();
  private isScanning = false;
  private isDemo = false;
  private demoInterval: any = null;
  private onUpdateCallback: ((candidates: BleDeviceItem[], otherDevices: BleDeviceItem[], status: AppStatus) => void) | null = null;

  constructor() {
    // Start periodic UI tick (every 250ms) to update RSSI ages & 20s summaries
    setInterval(() => {
      if (this.isScanning || this.isDemo) {
        this.emitState();
      }
    }, 250);
  }

  onUpdate(callback: (candidates: BleDeviceItem[], otherDevices: BleDeviceItem[], status: AppStatus) => void) {
    this.onUpdateCallback = callback;
  }

  isNative(): boolean {
    return Capacitor.isNativePlatform();
  }

  getStatus(): AppStatus {
    const selectedItem = this.selectedTargetAddress ? this.devices.get(this.selectedTargetAddress)?.item : null;
    return {
      is_scanning: this.isScanning,
      is_demo: this.isDemo,
      current_session_id: "mobile_session_" + Date.now(),
      selected_target_address: this.selectedTargetAddress,
      selected_target_summary: selectedItem ? selectedItem.signal : null,
      pinned_addresses: Array.from(this.pinnedAddresses),
      rule_catalog_version: "1.0.0",
      rule_catalog_hash: "mobile_native",
      rule_count: this.classifier.rules.size
    };
  }

  selectTarget(address: string | null) {
    this.selectedTargetAddress = address;
    this.emitState();
  }

  togglePin(address: string) {
    if (this.pinnedAddresses.has(address)) {
      this.pinnedAddresses.delete(address);
    } else {
      this.pinnedAddresses.add(address);
    }
    const dev = this.devices.get(address);
    if (dev) {
      dev.item.is_pinned = this.pinnedAddresses.has(address);
    }
    this.emitState();
  }

  async startScan(demo = false): Promise<void> {
    if (this.isScanning || this.isDemo) await this.stopScan();

    if (demo) {
      this.isDemo = true;
      this.startDemoLoop();
      this.emitState();
      return;
    }

    if (!this.isNative()) {
      // In web browser without local server, fallback to demo mode
      this.isDemo = true;
      this.startDemoLoop();
      this.emitState();
      return;
    }

    try {
      await BleClient.initialize();
      this.isScanning = true;

      await BleClient.requestLEScan(
        {
          allowDuplicates: true,
          scanMode: ScanMode.SCAN_MODE_LOW_LATENCY
        },
        (result: ScanResult) => {
          this.handleScanResult(result);
        }
      );
      this.emitState();
    } catch (err) {
      console.error("Failed to start native BLE scan:", err);
      this.isScanning = false;
      throw err;
    }
  }

  async stopScan(): Promise<void> {
    this.isScanning = false;
    this.isDemo = false;
    if (this.demoInterval) {
      clearInterval(this.demoInterval);
      this.demoInterval = null;
    }

    if (this.isNative()) {
      try {
        await BleClient.stopLEScan();
      } catch (e) {}
    }
    this.emitState();
  }

  private handleScanResult(res: ScanResult) {
    const monoS = performance.now() / 1000;
    const address = (res.device.deviceId || "").toUpperCase();
    if (!address) return;

    // Parse manufacturer data
    const mfgData: Record<string, string> = {};
    if (res.manufacturerData) {
      for (const [cidStr, dataVal] of Object.entries(res.manufacturerData)) {
        let cidHex = "";
        const cidNum = parseInt(cidStr, 10);
        if (!isNaN(cidNum)) {
          cidHex = cidNum.toString(16).padStart(4, "0").toLowerCase();
        } else {
          cidHex = cidStr.toLowerCase().replace("0x", "").padStart(4, "0");
        }
        mfgData[cidHex] = this.dataToHex(dataVal);
      }
    }

    // Parse service data
    const svcData: Record<string, string> = {};
    if (res.serviceData) {
      for (const [uuidStr, dataVal] of Object.entries(res.serviceData)) {
        let normUuid = uuidStr.toLowerCase().replace(/-/g, "");
        if (normUuid.length === 32 && normUuid.startsWith("0000") && normUuid.endsWith("00001000800000805f9b34fb")) {
          normUuid = normUuid.substring(4, 8);
        }
        svcData[normUuid] = this.dataToHex(dataVal);
      }
    }

    const uuids = (res.uuids || []).map((u) => {
      let nu = u.toLowerCase().replace(/-/g, "");
      if (nu.length === 32 && nu.startsWith("0000") && nu.endsWith("00001000800000805f9b34fb")) {
        return nu.substring(4, 8);
      }
      return nu;
    });

    const localName = res.localName || res.device.name || null;
    const rssi = res.rssi ?? -70;

    const record: NormalizedRecord = {
      address,
      rssi,
      local_name: localName,
      manufacturer_data: mfgData,
      service_data: svcData,
      service_uuids: uuids,
      parsed_apple_records: [],
      monotonic_s: monoS
    };

    this.signalProcessor.addObservation(address, rssi, monoS);
    const classification = this.classifier.classify(record);
    const summary = this.signalProcessor.getSummary(address, monoS);

    const item: BleDeviceItem = {
      address,
      local_name: localName,
      classification,
      signal: summary,
      is_pinned: this.pinnedAddresses.has(address),
      is_found: false
    };

    this.devices.set(address, { record, item });
  }

  private dataToHex(val: any): string {
    if (!val) return "";
    if (typeof val === "string") return val.toLowerCase();
    if (val instanceof DataView) {
      let hex = "";
      for (let i = 0; i < val.byteLength; i++) {
        hex += val.getUint8(i).toString(16).padStart(2, "0");
      }
      return hex;
    }
    if (val instanceof Uint8Array || Array.isArray(val)) {
      return Array.from(val)
        .map((b: number) => b.toString(16).padStart(2, "0"))
        .join("");
    }
    return "";
  }

  private startDemoLoop() {
    const demoSpecimens = [
      {
        address: "C2:9F:5B:4C:F3:69",
        local_name: "Xiaomi Tag",
        service_data: { feaa: "409870c3dbac216705d74478fe934f363e60d0fee206" },
        rssi_base: -38
      },
      {
        address: "E4:C1:38:BA:C5:D5",
        local_name: "My Finder",
        service_data: { fd44: "f3253682d8a77c3401000000000000000000000001" },
        rssi_base: -52
      },
      {
        address: "68:82:53:B7:3C:5D",
        local_name: null,
        service_data: { fd5a: "12245a038612137f87e9bfbab70000009e8e759c" },
        service_uuids: ["fd5a"],
        rssi_base: -34
      },
      {
        address: "D0:03:DF:BE:F0:8D",
        local_name: "[TV] Samsung 7 Series (55)",
        manufacturer_data: { "0075": "4204018060d003dfbef08dd203dfbef08c014cc6fcf1d4c3" },
        rssi_base: -68
      },
      {
        address: "AA:BB:CC:DD:EE:01",
        local_name: "Office Surface Laptop",
        manufacturer_data: { "0006": "010f20227065d4b26d11d444d6cd782d0ed31f243757edb8791de6" },
        rssi_base: -72
      }
    ];

    let tIdx = 0;
    this.demoInterval = setInterval(() => {
      tIdx++;
      const monoS = performance.now() / 1000;
      for (const spec of demoSpecimens) {
        const fluctuation = ((tIdx * 7 + spec.address.charCodeAt(0)) % 9) - 4;
        const curRssi = spec.rssi_base + fluctuation;

        const record: NormalizedRecord = {
          address: spec.address,
          rssi: curRssi,
          local_name: spec.local_name,
          manufacturer_data: spec.manufacturer_data || {},
          service_data: spec.service_data || {},
          service_uuids: spec.service_uuids || [],
          parsed_apple_records: [],
          monotonic_s: monoS
        };

        this.signalProcessor.addObservation(record.address, curRssi, monoS);
        const classification = this.classifier.classify(record);
        const summary = this.signalProcessor.getSummary(record.address, monoS);

        this.devices.set(record.address, {
          record,
          item: {
            address: record.address,
            local_name: record.local_name,
            classification,
            signal: summary,
            is_pinned: this.pinnedAddresses.has(record.address),
            is_found: false
          }
        });
      }
    }, 400);
  }

  private emitState() {
    if (!this.onUpdateCallback) return;
    const monoS = performance.now() / 1000;
    const candidates: BleDeviceItem[] = [];
    const others: BleDeviceItem[] = [];

    for (const [addr, entry] of this.devices.entries()) {
      entry.item.signal = this.signalProcessor.getSummary(addr, monoS);
      entry.item.is_pinned = this.pinnedAddresses.has(addr);
      if (entry.item.classification.is_candidate) {
        candidates.push(entry.item);
      } else {
        others.push(entry.item);
      }
    }

    this.onUpdateCallback(candidates, others, this.getStatus());
  }
}

export const mobileBleManager = new MobileBleManager();
