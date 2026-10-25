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

export default function Settings() {
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
      const response = await fetch(`${BACKEND_URL}/emergency-contacts`);
      if (!response.ok) {
        console.error('Backend response not OK:', response.status);
        return;
      }
      const data = await response.json();
      setContacts(data.contacts || []);
    } catch (error) {
      console.error('Failed to load contacts:', error);
      alert(`Failed to connect to backend. Make sure the backend is running on ${BACKEND_URL}`);
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
        const errorData = await response.json();
        alert(`Failed to add contact: ${errorData.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to add contact:', error);
      alert(`Failed to connect to backend. Make sure the backend is running on ${BACKEND_URL}`);
    }
  };

  const deleteContact = async (id: number) => {
    if (!confirm('Are you sure you want to delete this contact?')) return;

    try {
      const response = await fetch(`${BACKEND_URL}/emergency-contacts/${id}`, {
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
      alert(`Failed to connect to backend. Make sure the backend is running on ${BACKEND_URL}`);
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
        <p className="text-slate-400 mb-12">Manage your emergency contacts</p>

        <div className="mb-12">
          <h2 className="text-2xl font-semibold mb-6 text-slate-200">Emergency Contacts</h2>
          <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
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
