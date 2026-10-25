'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';

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

  useEffect(() => {
    loadContacts();
  }, []);

  const loadContacts = async () => {
    try {
      const response = await fetch('http://localhost:8000/emergency-contacts');
      if (!response.ok) {
        console.error('Backend response not OK:', response.status);
        return;
      }
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
      const response = await fetch('http://localhost:8000/emergency-contacts', {
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
        const errorData = await response.json();
        alert(`Failed to add contact: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to add contact:', error);
    }
  };

  const deleteContact = async (id: number) => {
    if (!confirm('Are you sure you want to delete this contact?')) return;

    try {
      const response = await fetch(`http://localhost:8000/emergency-contacts/${id}`, {
        method: 'DELETE',
      });

      if (response.ok) {
        setContacts(contacts.filter(c => c.id !== id));
        alert('Contact deleted successfully!');
      } else {
        const errorData = await response.json();
        alert(`Failed to delete contact: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to delete contact:', error);
    }
  };

  return(
    <div className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-indigo-950 text-white overflow-hidden">
      
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
          <Link href="/settings" className="text-slate-400 hover:text-white transition text-sm">Settings</Link>
        </div>
      </nav>

      <div className="flex flex-col items-center justify-center min-h-[calc(100vh-80px)] px-4 relative">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-indigo-500/20 rounded-full blur-3xl animate-pulse" />
          <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-violet-500/20 rounded-full blur-3xl animate-pulse" style={{ animationDelay: '1s' }} />
        </div>

        <div className="text-center max-w-4xl relative z-10">
          <div className="inline-flex items-center bg-indigo-500/10 border border-indigo-500/20 rounded-full px-4 py-2 mb-8">
            <span className="text-indigo-400 text-sm font-medium">Congressional App Contest 2026</span>
          </div>

          <h1 className="text-7xl font-bold mb-6 tracking-tight leading-tight">
            Protecting What Matters
            <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-violet-400">With AI-Powered Care</span>
          </h1>
          
          <p className="text-2xl text-slate-300 mb-4 font-light">
            Slip<span className="text-indigo-500">Lert</span> — Intelligent Fall Detection System
          </p>
          
          <p className="text-lg text-slate-400 mb-12 max-w-2xl mx-auto leading-relaxed">
            Give your loved ones the freedom to live independently while ensuring their safety. Our AI-powered monitoring system detects falls instantly and alerts emergency contacts, providing peace of mind for families everywhere.
          </p>
          
          <div className="flex flex-col sm:flex-row gap-4 justify-center items-center">
            <Link href="/dashboard">
              <button className="bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white px-10 py-4 rounded-lg font-semibold text-lg shadow-lg shadow-indigo-500/25 transition transform hover:scale-105 active:scale-95 w-full sm:w-auto">
                Start Monitoring
              </button>
            </Link>
          </div>

          <div className="mt-12 flex items-center justify-center gap-8 text-slate-500 text-sm">
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span>Private & Secure</span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span>Real-Time Alerts</span>
            </div>
            <div className="flex items-center gap-2">
              <svg className="w-5 h-5 text-emerald-500" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
              </svg>
              <span>Easy to Use</span>
            </div>
          </div>
        </div>

        <div className="mt-24 max-w-3xl w-full px-4 relative z-10">
          <h2 className="text-3xl font-bold text-center text-slate-200 mb-8">Emergency Contacts</h2>
          <div className="bg-slate-900/50 border border-slate-800 rounded-xl p-6 backdrop-blur">
            <div className="flex justify-between items-center mb-6">
              <p className="text-slate-400 text-sm">
                These contacts will be called automatically when a fall is detected.
              </p>
              <button
                onClick={() => setShowContactForm(!showContactForm)}
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
                  <label className="block text-sm font-medium text-slate-300 mb-2">Phone Number</label>
                  <input
                    type="tel"
                    value={newContact.phone}
                    onChange={(e) => setNewContact({ ...newContact, phone: e.target.value })}
                    className="w-full bg-slate-700 border border-slate-600 rounded-lg px-4 py-2 text-slate-200"
                    placeholder="+1 (555) 123-4567"
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
      </div>
    </div>
  );
}
