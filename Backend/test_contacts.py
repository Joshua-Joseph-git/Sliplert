import requests
import json

BASE_URL = "http://localhost:8000"

def test_add_contact():
    contact = {
        "name": "Test Contact",
        "phone": "+1234567890",
        "relationship": "Test"
    }

    try:
        response = requests.post(f"{BASE_URL}/emergency-contacts", json=contact)
        print(f"Add Contact Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error adding contact: {e}")
        return False

def test_get_contacts():
    try:
        response = requests.get(f"{BASE_URL}/emergency-contacts")
        print(f"\nGet Contacts Status: {response.status_code}")
        print(f"Contacts: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error getting contacts: {e}")
        return False

def test_delete_contact(contact_id):
    try:
        response = requests.delete(f"{BASE_URL}/emergency-contacts/{contact_id}")
        print(f"\nDelete Contact Status: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error deleting contact: {e}")
        return False

if __name__ == "__main__":
    print("Testing Emergency Contact System")
    print("=" * 50)

    if test_add_contact():
        print("\n✓ Add contact successful")
    else:
        print("\n✗ Add contact failed")

    if test_get_contacts():
        print("✓ Get contacts successful")
    else:
        print("✗ Get contacts failed")

    contacts = requests.get(f"{BASE_URL}/emergency-contacts").json()
    if contacts.get("contacts"):
        contact_id = contacts["contacts"][0]["id"]
        if test_delete_contact(contact_id):
            print("✓ Delete contact successful")
        else:
            print("✗ Delete contact failed")
