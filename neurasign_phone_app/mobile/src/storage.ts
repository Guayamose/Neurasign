import * as SecureStore from 'expo-secure-store';
import * as Crypto from 'expo-crypto';
import * as SQLite from 'expo-sqlite';
import type { Observation } from '../../src/contract';
import type { ObservationQueue } from '../../src/gateway';
import { fromByteArray } from 'base64-js';

const secureOptions = { keychainAccessible: SecureStore.AFTER_FIRST_UNLOCK_THIS_DEVICE_ONLY };
export const secret = () => fromByteArray(Crypto.getRandomBytes(32)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
export async function readSecret<T>(key: string): Promise<T | null> { const value = await SecureStore.getItemAsync(key, secureOptions); return value ? JSON.parse(value) : null; }
export async function writeSecret(key: string, value: unknown) { await SecureStore.setItemAsync(key, JSON.stringify(value), secureOptions); }
export async function removeSecret(key: string) { await SecureStore.deleteItemAsync(key, secureOptions); }

/** SQLCipher file; the independent encryption key never enters AsyncStorage. */
export class EncryptedQueue implements ObservationQueue {
  private constructor(private db: SQLite.SQLiteDatabase) {}
  static async open() {
    let key = await readSecret<string>('queue-key');
    if (!key) { key = Array.from(Crypto.getRandomBytes(32), b => b.toString(16).padStart(2, '0')).join(''); await writeSecret('queue-key', key); }
    if (!/^[a-f0-9]{64}$/.test(key)) throw new Error('Invalid secure queue key.');
    const db = await SQLite.openDatabaseAsync('neurasign-queue.db');
    await db.execAsync(`PRAGMA key = "x'${key}'";`);
    const cipher = await db.getFirstAsync<Record<string, unknown>>('PRAGMA cipher_version');
    if (!cipher || !Object.values(cipher)[0]) throw new Error('Encrypted storage is unavailable.');
    await db.execAsync('PRAGMA journal_mode = WAL; CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, enrollment TEXT NOT NULL, measured REAL NOT NULL, body TEXT NOT NULL); CREATE INDEX IF NOT EXISTS queue_enrollment ON observations(enrollment, measured);');
    return new EncryptedQueue(db);
  }
  async append(enrollment: string, row: Observation) {
    await this.db.runAsync('INSERT OR IGNORE INTO observations VALUES (?, ?, ?, ?)', row.id, enrollment, Date.parse(row.measured_at), JSON.stringify(row));
    await this.db.runAsync('DELETE FROM observations WHERE measured < ?', Date.now() - 7 * 86400000);
    await this.db.runAsync('DELETE FROM observations WHERE id IN (SELECT id FROM observations ORDER BY measured DESC LIMIT -1 OFFSET 20000)');
  }
  async peek(enrollment: string, limit: number) {
    await this.db.runAsync('DELETE FROM observations WHERE measured < ?', Date.now() - 7 * 86400000);
    const rows = await this.db.getAllAsync<{ body: string }>('SELECT body FROM observations WHERE enrollment = ? ORDER BY measured LIMIT ?', enrollment, limit);
    return rows.map(row => JSON.parse(row.body) as Observation);
  }
  async acknowledge(enrollment: string, ids: string[]) {
    if (ids.length) await this.db.runAsync(`DELETE FROM observations WHERE enrollment = ? AND id IN (${ids.map(() => '?').join(',')})`, enrollment, ...ids);
  }
  async clear() { await this.db.runAsync('DELETE FROM observations'); }
  async count() { return (await this.db.getFirstAsync<{ n: number }>('SELECT COUNT(*) AS n FROM observations'))?.n ?? 0; }
}
