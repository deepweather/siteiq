/**
 * Have-I-Been-Pwned k-anonymity breach check.
 *
 * Hash the password with SHA-1, send only the first 5 hex chars to the
 * HIBP API, and look up our remaining 35 chars in the response. The
 * password itself never leaves the browser.
 *
 * Returns the breach count (0 if not in any known breach), or -1 on
 * network error so callers can fail open. Debounced + cancellable.
 *
 * Spec: https://haveibeenpwned.com/API/v3#PwnedPasswords
 */

const API = 'https://api.pwnedpasswords.com/range/';

async function sha1Hex(input: string): Promise<string> {
  const data = new TextEncoder().encode(input);
  const buf = await crypto.subtle.digest('SHA-1', data);
  return [...new Uint8Array(buf)]
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('')
    .toUpperCase();
}

export async function checkBreach(password: string, signal?: AbortSignal): Promise<number> {
  if (!password || password.length < 4) return 0;
  let hash: string;
  try {
    hash = await sha1Hex(password);
  } catch {
    return -1;
  }
  const prefix = hash.slice(0, 5);
  const suffix = hash.slice(5);
  try {
    const res = await fetch(`${API}${prefix}`, {
      headers: { 'Add-Padding': 'true' },
      signal,
    });
    if (!res.ok) return -1;
    const text = await res.text();
    for (const line of text.split('\n')) {
      const [hex, countStr] = line.trim().split(':');
      if (hex === suffix) {
        const n = Number(countStr);
        return Number.isFinite(n) ? n : -1;
      }
    }
    return 0;
  } catch {
    return -1;
  }
}
