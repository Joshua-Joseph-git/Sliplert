'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import {
  EmergencyContact,
  contactKey,
  getSavedBackendUrl,
  loadCachedContacts,
  saveCachedContacts,
  syncContactsToPi,
  validateContactTarget,
} from '@/lib/sliplert';

export default function Settings() {
  const [contacts, setContacts] = useState<EmergencyContact[]>([]);
  const [newContact, setNewContact] = useState({
    name: '',
    phone: '',
    relationship: ''
  });
  const [showContactForm, setShowContactForm] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [syncNote, setSyncNote] = useState('');

  const updateContacts = (list: EmergencyContact[]) => {
    setContacts(list);
    saveCachedContacts(list);
  };

  const loadContacts = async () => {
    setContacts(loadCachedContacts());
    const backendUrl = getSavedBackendUrl();
    if (!backendUrl) {
      setSyncNote('Not connected to the robot yet. Contacts are saved in this browser and sync when you click Connect on the Dashboard.');
      return;
    }
    try {
      // The Pi is the one that sends the alerts, so its list is the real one
      const onPi = await syncContactsToPi(backendUrl);
      if (onPi) {
        updateContacts(onPi);
        setSyncNote(`Synced with the robot at ${backendUrl}.`);
        return;
      }
    } catch {}
    setSyncNote(`Robot at ${backendUrl} is offline. Changes are saved in this browser and sync when it is back.`);
  };

  useEffect(() => {
    loadContacts();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addContact = async () => {
    const contact = {
      name: newContact.name.trim(),
      phone: newContact.phone.trim(),
      relationship: newContact.relationship.trim(),
    };
    if (!contact.name || !contact.phone || !contact.relationship) {
      setFormError('Please fill in all fields.');
      return;
    }
    const problem = validateContactTarget(contact.phone);
    if (problem) {
      setFormError(problem);
      return;
    }
    if (contacts.some(c => contactKey(c.phone) === contactKey(contact.phone))) {
      setFormError('That contact is already saved.');
      return;
    }
    setFormError(null);

    const backendUrl = getSavedBackendUrl();
    let saved: EmergencyContact = { id: Date.now(), ...contact };
    if (backendUrl) {
      try {
        const response = await fetch(`${backendUrl}/emergency-contacts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(contact),
          signal: AbortSignal.timeout(3000),
        });
        if (response.ok) {
          saved = (await response.json()).contact;
        } else {
          setSyncNote('Robot did not accept the contact; saved in this browser only for now.');
        }
      } catch {
        setSyncNote('Robot is offline; saved in this browser. It will sync when you click Connect on the Dashboard.');
      }
    }
    updateContacts([...contacts, saved]);
    setNewContact({ name: '', phone: '', relationship: '' });
    setShowContactForm(false);
  };

  const deleteContact = async (contact: EmergencyContact) => {
    if (!confirm('Are you sure you want to delete this contact?')) return;

    updateContacts(contacts.filter(c => c.id !== contact.id));

    const backendUrl = getSavedBackendUrl();
    if (!backendUrl) return;
    try {
      // Match by address, not id: a contact added while offline has a different id on the Pi
      const res = await fetch(`${backendUrl}/emergency-contacts`, { signal: AbortSignal.timeout(3000) });
      const onPi: EmergencyContact[] = res.ok ? (await res.json()).contacts || [] : [];
      for (const c of onPi.filter(c => contactKey(c.phone) === contactKey(contact.phone))) {
        await fetch(`${backendUrl}/emergency-contacts/${c.id}`, { method: 'DELETE' });
      }
    } catch {
      setSyncNote('Robot is offline; the contact was removed here but may still be on the robot. Delete it again once the robot is online.');
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <nav className="border-b border-slate-800 bg-slate-950/50 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center space-x-3">
          <div className="h-3 w-3 rounded-full bg-indigo-500 animate-pulse" />
          <h1 className="text-xl font-bold tracking-wider text-slate-200">
            Slip<span className="text-indigo-500">Lert</span>
          </h1>
        </div>
        <div className="flex items-center space-x-6">
          <Link href="/" className="text-slate-400 hover:text-white transition text-sm">Home</Link>
          <Link href="/dashboard" className="text-slate-400 hover:text-white transition text-sm">Dashboard</Link>
          <Link href="/settings" className="text-white transition text-sm font-medium">Settings</Link>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-6 py-12">
        <h1 className="text-4xl font-bold mb-2 text-slate-200">Settings</h1>
        <p className="text-slate-400 mb-3">Manage your emergency contacts</p>
        {syncNote && <p className="text-xs text-slate-500 mb-9">{syncNote}</p>}

        <div className="mb-12">
          <h2 className="text-2xl font-semibold mb-6 text-slate-200">Emergency Contacts</h2>
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <div className="flex justify-between items-center mb-6">
              <p className="text-slate-400 text-sm">
                These contacts will receive an instant emergency email alert when a fall is detected.
              </p>
              <button
                onClick={() => { setShowContactForm(!showContactForm); setFormError(null); }}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition text-sm font-medium"
              >
                {showContactForm ? 'Cancel' : 'Add Contact'}
              </button>
            </div>

            {showContactForm && (
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6 space-y-4">
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Name</label>
                  <input
                    type="text"
                    value={newContact.name}
                    onChange={(e) => setNewContact({ ...newContact, name: e.target.value })}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-slate-200"
                    placeholder="Contact name"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Email Address (or Phone)</label>
                  <input
                    type="text"
                    value={newContact.phone}
                    onChange={(e) => setNewContact({ ...newContact, phone: e.target.value })}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-slate-200"
                    placeholder="caregiver@email.com"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-300 mb-2">Relationship</label>
                  <input
                    type="text"
                    value={newContact.relationship}
                    onChange={(e) => setNewContact({ ...newContact, relationship: e.target.value })}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-slate-200"
                    placeholder="e.g., Son, Daughter, Caregiver"
                  />
                </div>
                {formError && <p className="text-sm text-red-400">{formError}</p>}
                <button
                  onClick={addContact}
                  className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition font-medium"
                >
                  Add Contact
                </button>
              </div>
            )}

            {contacts.length === 0 ? (
              <div className="text-center py-8 text-slate-500">
                <p>No emergency contacts added yet.</p>
                <p className="text-sm mt-2">Add a caregiver&apos;s email address so SlipLert can alert them when a fall is detected.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {contacts.map((contact) => (
                  <div
                    key={contact.id}
                    className="bg-slate-800 border border-slate-700 rounded-lg p-4 flex justify-between items-center"
                  >
                    <div>
                      <h3 className="font-semibold text-slate-200">{contact.name}</h3>
                      <p className="text-sm text-slate-400">{contact.phone}</p>
                      <p className="text-xs text-slate-500 mt-1">{contact.relationship}</p>
                    </div>
                    <button
                      onClick={() => deleteContact(contact)}
                      className="px-3 py-1.5 bg-red-600/10 hover:bg-red-600/20 text-red-400 rounded-lg transition text-sm"
                    >
                      Delete
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
