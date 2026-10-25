'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

type EmergencyContact = {
  id: number;
  name: string;
  phone: string;
  relationship: string;
};

export default function Home() {
  const [contacts, setContacts] = useState<EmergencyContact[]>([]);
  const [newContact, setNewContact] = useState({
    name: '',
    phone: '',
    relationship: ''
  });
  const [showContactForm, setShowContactForm] = useState(false);
  const [showContacts, setShowContacts] = useState(false);

  useEffect(() => {
    loadContacts();
  }, []);

  const loadContacts = async () => {
    try {
      const response = await fetch(`${BACKEND_URL}/emergency-contacts`);
      if (!response.ok) return;
      const data = await response.json();
      setContacts(data.contacts || []);
    } catch (error) {
      console.error('Failed to load contacts:', error);
    }
  };

  const addContact = async () => {
    if (!newContact.name || !newContact.phone || !newContact.relationship) {
      alert('Please fill in all fields');
      return;
    }

    try {
      const response = await fetch(`${BACKEND_URL}/emergency-contacts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(newContact),
      });

      if (response.ok) {
        const data = await response.json();
        setContacts([...contacts, data.contact]);
        setNewContact({ name: '', phone: '', relationship: '' });
        setShowContactForm(false);
        alert('Contact added successfully!');
      } else {
        alert('Failed to add contact');
      }
    } catch (error) {
      console.error('Failed to add contact:', error);
      alert('Backend not running. Start the backend first.');
    }
  };

  const deleteContact = async (id: number) => {
    if (!confirm('Delete this contact?')) return;

    try {
      const response = await fetch(`${BACKEND_URL}/emergency-contacts/${id}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        setContacts(contacts.filter(c => c.id !== id));
        alert('Contact deleted!');
      }
    } catch (error) {
      console.error('Failed to delete contact:', error);
    }
  };

  return(
    <div className="min-h-screen bg-slate-950 text-white">

      {/* Navigation Bar */}
      <nav className="border-b border-slate-800 bg-slate-950/80 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <Link href="/" className="flex items-center space-x-3">
          <div className="h-3 w-3 rounded-full bg-indigo-500 animate-pulse" />
          <h1 className="text-xl font-bold tracking-wider text-slate-200">
            Slip<span className="text-indigo-500">Lert</span>
          </h1>
        </Link>
        <div className="flex items-center space-x-6">
          <Link href="/" className="flex items-center gap-1.5 bg-slate-800 text-white px-3 py-1.5 rounded-lg text-sm font-medium transition">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
            </svg>
            Home
          </Link>
          <Link href="/dashboard" className="flex items-center gap-1.5 text-slate-400 hover:text-white transition text-sm">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
            Dashboard
          </Link>
          <Link href="/settings" className="flex items-center gap-1.5 text-slate-400 hover:text-white transition text-sm">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Settings
          </Link>
        </div>
      </nav>

      {/* Hero Section */}
      <div className="flex flex-col items-center justify-center px-4 pt-24 pb-16 relative">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-500/15 rounded-full blur-3xl animate-pulse" />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-violet-500/15 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        </div>

        <div className="text-center max-w-4xl relative z-10">
          <div className="inline-flex items-center bg-indigo-500/10 border border-indigo-500/30 rounded-full px-5 py-1.5 mb-8">
            <span className="text-indigo-400 text-xs font-semibold tracking-widest">ACTIVE FALL DETECTION SYSTEM</span>
          </div>

          <h1 className="text-6xl font-bold mb-6 tracking-tight leading-tight">
            24/7 Safety & Instant
            <br />
            Emergency Alerts
          </h1>

          <p className="text-lg text-slate-400 mb-10 max-w-2xl mx-auto leading-relaxed">
            SlipLert actively monitors for accidental slips and falls, notifying your trusted loved ones and medical emergency contacts in milliseconds.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link href="/dashboard">
              <button className="bg-indigo-600 hover:bg-indigo-500 text-white px-8 py-3.5 rounded-lg font-semibold text-base shadow-lg shadow-indigo-500/25 transition transform hover:scale-105 active:scale-95 w-full sm:w-auto">
                View Dashboard
              </button>
            </Link>
            <button
              onClick={() => { setShowContacts(!showContacts); setShowContactForm(false); }}
              className="bg-slate-700 hover:bg-slate-600 text-white px-8 py-3.5 rounded-lg font-semibold text-base transition w-full sm:w-auto"
            >
              Manage Contacts ({contacts.length})
            </button>
          </div>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5 max-w-5xl mx-auto px-6 pb-12">
        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <div className="w-10 h-10 bg-emerald-500/10 rounded-lg flex items-center justify-center mb-4">
            <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
          </div>
          <h3 className="text-slate-300 font-semibold mb-1">System Status</h3>
          <div className="text-emerald-400 font-bold text-lg flex items-center gap-1.5">
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
            Online
          </div>
          <p className="text-slate-500 text-xs mt-1">Sensors calibrated & active</p>
        </div>

        <button
          onClick={() => { setShowContacts(!showContacts); setShowContactForm(false); }}
          className="bg-slate-900 border border-slate-800 rounded-xl p-6 text-left hover:border-indigo-500/50 transition"
        >
          <div className="w-10 h-10 bg-indigo-500/10 rounded-lg flex items-center justify-center mb-4">
            <svg className="w-5 h-5 text-indigo-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
            </svg>
          </div>
          <h3 className="text-slate-300 font-semibold mb-1">Emergency Contacts</h3>
          <div className="text-white font-bold text-lg">{contacts.length} Configured</div>
          <p className="text-slate-500 text-xs mt-1">Ready to auto-call on fall detection</p>
        </button>

        <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
          <div className="w-10 h-10 bg-violet-500/10 rounded-lg flex items-center justify-center mb-4">
            <svg className="w-5 h-5 text-violet-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
            </svg>
          </div>
          <h3 className="text-slate-300 font-semibold mb-1">Health Monitor</h3>
          <div className="text-white font-bold text-lg">Normal</div>
          <p className="text-slate-500 text-xs mt-1">No abnormal motion detected</p>
        </div>
      </div>

      {/* Contacts Panel (expandable) */}
      {showContacts && (
        <div className="max-w-3xl mx-auto px-6 pb-16">
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
            <div className="flex justify-between items-center mb-6">
              <h2 className="text-xl font-bold text-slate-200">Emergency Contacts</h2>
              <button
                onClick={() => setShowContactForm(!showContactForm)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition text-sm font-medium"
              >
                {showContactForm ? 'Cancel' : 'Add Contact'}
              </button>
            </div>

            {showContactForm && (
              <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6 space-y-4">
                <input
                  type="text"
                  value={newContact.name}
                  onChange={(e) => setNewContact({ ...newContact, name: e.target.value })}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-slate-200"
                  placeholder="Contact name"
                />
                <input
                  type="tel"
                  value={newContact.phone}
                  onChange={(e) => setNewContact({ ...newContact, phone: e.target.value })}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-slate-200"
                  placeholder="+1 (555) 123-4567"
                />
                <input
                  type="text"
                  value={newContact.relationship}
                  onChange={(e) => setNewContact({ ...newContact, relationship: e.target.value })}
                  className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-slate-200"
                  placeholder="e.g., Son, Daughter, Caregiver"
                />
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
                <p className="text-sm mt-2">Add contacts to enable automatic emergency calls.</p>
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
                      onClick={() => deleteContact(contact.id)}
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
      )}
    </div>
  );
}
