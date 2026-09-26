import { GatewayError } from './gateway.js';
export type EnrollmentLink = { apiOrigin: string; token: string };
export function parseEnrollmentLink(value: string, allowLocalHttp = false): EnrollmentLink {
  const url = new URL(value.trim());
  if (url.protocol !== 'neurasign:' || url.hostname !== 'enroll' || (url.pathname && url.pathname !== '/') || url.search || url.username || url.password) throw new Error('Scan a NEURASIGN connection code.');
  const params = new URLSearchParams(url.hash.slice(1));
  let unknown = false; params.forEach((_, key) => { if (!['server', 'token'].includes(key)) unknown = true; });
  if (params.getAll('server').length !== 1 || params.getAll('token').length !== 1 || unknown) throw new Error('Invalid connection code.');
  const server = new URL(params.get('server') ?? '');
  const local = allowLocalHttp && server.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(server.hostname);
  if ((server.protocol !== 'https:' && !local) || server.username || server.password || server.pathname !== '/' || server.search || server.hash) throw new Error('The company server must use HTTPS.');
  const token = params.get('token') ?? '';
  if (!/^nse_[a-f0-9]{32}\.[A-Za-z0-9_-]{43}$/.test(token)) throw new Error('Invalid connection code.');
  return { apiOrigin: server.origin, token };
}
export async function gatewayRequest<T>(origin: string, path: string, options: { method?: string; body?: unknown; credential?: string; signal?: AbortSignal; fetch?: typeof fetch } = {}): Promise<T> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  options.signal?.addEventListener('abort', abort);
  if (options.signal?.aborted) controller.abort();
  const timer = setTimeout(abort, 20000);
  try {
    const response = await (options.fetch ?? fetch)(`${origin}/api/v1/gateway${path}`, {
      method: options.method ?? 'GET', redirect: 'error', signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(options.credential ? { Authorization: `Bearer ${options.credential}` } : {}) },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new GatewayError(response.status, typeof result.detail === 'string' ? result.detail : `Connection failed (${response.status}).`);
    return result as T;
  } finally { clearTimeout(timer); options.signal?.removeEventListener('abort', abort); }
}
