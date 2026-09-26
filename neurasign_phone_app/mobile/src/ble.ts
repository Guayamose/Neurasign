import { PermissionsAndroid, Platform } from 'react-native';
import { BleManager, State } from 'react-native-ble-plx';
import { toByteArray, fromByteArray } from 'base64-js';
import type { Candidate } from '../../src/contract';
import type { GattTransport, GattConnection } from '../../src/ble-protocol';

export class NativeBle implements GattTransport {
  readonly manager = new BleManager({ restoreStateIdentifier: 'neurasign-link-ble', restoreStateFunction: state => {
    // Never restart capture from an OS callback without the persisted user session.
    for (const device of state?.connectedPeripherals ?? []) void device.cancelConnection().catch(() => {});
  } });
  async permission() {
    if (Platform.OS === 'android') {
      const required = Number(Platform.Version) >= 31 ? [PermissionsAndroid.PERMISSIONS.BLUETOOTH_SCAN, PermissionsAndroid.PERMISSIONS.BLUETOOTH_CONNECT] : [PermissionsAndroid.PERMISSIONS.ACCESS_FINE_LOCATION];
      const result = await PermissionsAndroid.requestMultiple(required);
      if (required.some(key => result[key] !== PermissionsAndroid.RESULTS.GRANTED)) throw new Error('Allow nearby devices to connect your wearable.');
      if (Number(Platform.Version) >= 33) await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS);
    }
    const state = await this.manager.state();
    if (state !== State.PoweredOn) throw new Error(state === State.Unsupported ? 'Bluetooth is unavailable on this device.' : 'Turn on Bluetooth and allow nearby devices.');
  }
  async scan(onFound: (candidate: Candidate) => void, onError: (error: Error) => void) {
    await this.permission();
    await this.manager.startDeviceScan(null, { allowDuplicates: false }, (error, device) => {
      if (error) { onError(new Error(error.message)); return; }
      if (device && device.isConnectable !== false) onFound({ id: device.id, name: device.name || device.localName || 'Bluetooth device', services: device.serviceUUIDs ?? [] });
    });
  }
  async stopScan() { await this.manager.stopDeviceScan(); }
  async connect(candidate: Candidate, signal: AbortSignal): Promise<GattConnection> {
    if (signal.aborted) throw new Error('Connection cancelled.');
    const cancel = () => { void this.manager.cancelDeviceConnection(candidate.id).catch(() => {}); };
    signal.addEventListener('abort', cancel);
    let device;
    try {
      device = await this.manager.connectToDevice(candidate.id, { timeout: 15000 });
      if (Platform.OS === 'android') {
        try { device = await device.requestMTU(232); }
        catch { /* Standard services can still work at the default MTU. */ }
      }
      await device.discoverAllServicesAndCharacteristics();
    }
    catch (e) { signal.removeEventListener('abort', cancel); cancel(); throw e; }
    if (signal.aborted) { cancel(); throw new Error('Connection cancelled.'); }
    const manager = this.manager;
    return {
      characteristics: async () => {
        const result = [];
        for (const service of await device.services()) {
          for (const characteristic of await service.characteristics()) result.push({ service: service.uuid, uuid: characteristic.uuid,
            notify: characteristic.isNotifiable, indicate: characteristic.isIndicatable, read: characteristic.isReadable, write: characteristic.isWritableWithResponse });
        }
        return result;
      },
      read: async (service, characteristic) => {
        const value = await device.readCharacteristicForService(service, characteristic);
        if (!value.value) throw new Error('Wearable returned an empty characteristic.');
        return toByteArray(value.value);
      },
      write: async (service, characteristic, bytes) => { await device.writeCharacteristicWithResponseForService(service, characteristic, fromByteArray(bytes)); },
      notifications: async function* (service, characteristic, abortSignal) {
        const packets: { bytes: Uint8Array; receivedAt: string }[] = [];
        let failed: Error | undefined, wake: (() => void) | undefined;
        const notify = () => { wake?.(); wake = undefined; };
        const sub = device.monitorCharacteristicForService(service, characteristic, (error, value) => {
          if (error) failed = new Error(error.message);
          else if (value?.value) {
            if (packets.length >= 120) failed = new Error('Sensor delivery exceeded the local buffer. Reconnecting.');
            else { try { packets.push({ bytes: toByteArray(value.value), receivedAt: new Date().toISOString() }); } catch { failed = new Error('Invalid Bluetooth measurement.'); } }
          }
          notify();
        });
        const disconnected = manager.onDeviceDisconnected(device.id, () => { failed = new Error('Wearable disconnected. Reconnecting…'); notify(); });
        abortSignal.addEventListener('abort', notify);
        try {
          while (!abortSignal.aborted) {
            if (failed) throw failed;
            if (packets.length) yield packets.shift()!;
            else await new Promise<void>(resolve => { wake = resolve; });
          }
        } finally { sub.remove(); disconnected.remove(); abortSignal.removeEventListener('abort', notify); }
      },
      close: async () => { signal.removeEventListener('abort', cancel); await manager.cancelDeviceConnection(candidate.id).catch(() => {}); },
    };
  }
}
