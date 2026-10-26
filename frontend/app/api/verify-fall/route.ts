import { NextRequest, NextResponse } from 'next/server';

async function sendDirectEmailAlert(contacts: Array<{ name?: string; phone?: string }>, fallType: string) {
  const sentTo: string[] = [];
  for (const c of contacts) {
    const email = (c.phone || '').trim();
    if (!email.includes('@')) continue;
    sentTo.push(email);
    try {
      await fetch(`https://formsubmit.co/ajax/${encodeURIComponent(email)}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          _subject: 'URGENT: SlipLert Fall Detected - Check on Your Loved One',
          name: 'SlipLert Autonomous Safety Monitor',
          recipient: c.name || 'Emergency Contact',
          fall_type: fallType,
          timestamp: new Date().toLocaleString(),
          message: `Hello ${c.name || 'Caregiver'}, SlipLert detected a fall (${fallType}). The robot car has stopped safely next to your loved one. Please check on them immediately.`,
        }),
      });
    } catch {}
  }
  return sentTo;
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const targetUrl = body.backendUrl || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
    const contacts = Array.isArray(body.contacts) ? body.contacts : [];

    if (body.coordinates || body.simulate) {
      await sendDirectEmailAlert(contacts, 'simulated_fall');
    }

    let response;
    try {
      response = await fetch(`${targetUrl}/detect-fall-base64`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
    } catch {
      if (body.coordinates || body.simulate) {
        return NextResponse.json({
          confirmedFall: true,
          fallType: 'simulated_fall',
          confidence: 0.98,
          bodyAngle: 82,
          calledContacts: contacts.map((c: { name?: string; phone?: string }) => `${c.name} (${c.phone})`),
          calledPhones: contacts.map((c: { phone?: string }) => c.phone || ''),
          mock: true,
        });
      }
      return NextResponse.json({
        confirmedFall: false,
        fallType: null,
        confidence: 0,
        bodyAngle: 0,
        mock: true,
      });
    }

    if (!response.ok) {
      throw new Error('Backend request failed');
    }

    const data = await response.json();

    return NextResponse.json({
      confirmedFall: data.fall_detected,
      fallType: data.fall_type,
      confidence: data.confidence,
      bodyAngle: data.body_angle,
      calledContacts: data.called_contacts || [],
      calledPhones: data.called_phones || [],
    });
  } catch (error) {
    console.error('Error verifying fall:', error);
    return NextResponse.json({
      confirmedFall: false,
      fallType: null,
      confidence: 0,
      bodyAngle: 0,
      error: 'Failed to verify fall',
    });
  }
}
