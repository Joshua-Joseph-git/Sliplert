// Shared helpers for talking to the Raspberry Pi backend (used by the dashboard and settings pages)

export type EmergencyContact = {
  id: number;
  name: string;
  phone: string; // email address or phone number
  relationship: string;
};

export const BACKEND_URL_KEY = 'sliplert_backend_url';
export const CONTACTS_KEY = 'sliplert_contacts';

export function getSavedBackendUrl(): string {
  if (typeof window === 'undefined') return '';
  return window.localStorage.getItem(BACKEND_URL_KEY) || process.env.NEXT_PUBLIC_BACKEND_URL || '';
}

// "192.168.1.20" -> "http://192.168.1.20:8000"
export function normalizeBackendUrl(input: string): string {
  const clean = input.trim().replace(/\/+$/, '');
  if (!clean) return '';
  if (clean.startsWith('http')) return clean;
  return `http://${clean}${clean.includes(':') ? '' : ':8000'}`;
}

// A page loaded over https:// can't call the Pi's http:// address (the browser blocks "mixed content")
export function mixedContentProblem(backendUrl: string): string | null {
  if (typeof window === 'undefined') return null;
  if (window.location.protocol === 'https:' && backendUrl.startsWith('http://')) {
    return 'This page is open over HTTPS, so the browser blocks the Pi\'s http:// address. Run the dashboard locally (npm run dev → http://localhost:3000) on the same Wi-Fi as the Pi.';
  }
  return null;
}

// Same person no matter how it was typed: emails ignore case, phones ignore formatting
export function contactKey(target: string): string {
  const t = String(target).trim();
  if (t.includes('@')) return t.toLowerCase();
  const digits = t.replace(/[^\d]/g, '');
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
  return t.startsWith('+') ? `+${digits}` : digits;
}

export function validateContactTarget(target: string): string | null {
  const t = target.trim();
  if (t.includes('@')) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(t) ? null : 'That email address doesn\'t look right (example: name@gmail.com).';
  }
  return t.replace(/[^\d]/g, '').length >= 10 ? null : 'Enter an email address, or a phone number with area code.';
}

export function loadCachedContacts(): EmergencyContact[] {
  try {
    const saved = JSON.parse(window.localStorage.getItem(CONTACTS_KEY) || '[]');
    return Array.isArray(saved) ? saved : [];
  } catch {
    return [];
  }
}

export function saveCachedContacts(contacts: EmergencyContact[]) {
  window.localStorage.setItem(CONTACTS_KEY, JSON.stringify(contacts));
}

// Push any contacts saved in this browser that the Pi doesn't have yet. Returns the Pi's list.
export async function syncContactsToPi(backendUrl: string): Promise<EmergencyContact[] | null> {
  const res = await fetch(`${backendUrl}/emergency-contacts`, { signal: AbortSignal.timeout(3000) });
  if (!res.ok) return null;
  const onPi: EmergencyContact[] = (await res.json()).contacts || [];
  const known = new Set(onPi.map(c => contactKey(c.phone)));
  let changed = false;
  for (const c of loadCachedContacts()) {
    if (c.name && c.phone && !known.has(contactKey(c.phone))) {
      await fetch(`${backendUrl}/emergency-contacts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: c.name, phone: c.phone, relationship: c.relationship || 'Family' }),
        signal: AbortSignal.timeout(3000),
      });
      known.add(contactKey(c.phone));
      changed = true;
    }
  }
  if (!changed) return onPi;
  const again = await fetch(`${backendUrl}/emergency-contacts`, { signal: AbortSignal.timeout(3000) });
  return again.ok ? (await again.json()).contacts || [] : onPi;
}
