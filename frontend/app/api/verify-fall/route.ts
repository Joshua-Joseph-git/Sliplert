import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const targetUrl = body.backendUrl || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

    // Note: the dashboard calls the Pi directly from the browser. This server route only works when
    // the Next.js server itself is on the same network as the Pi.
    let response;
    try {
      response = await fetch(`${targetUrl}/detect-fall-base64`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(8000),
      });
    } catch {
      // Never pretend an alert went out when the robot couldn't be reached
      return NextResponse.json({
        confirmedFall: false,
        fallType: null,
        confidence: 0,
        bodyAngle: 0,
        error: `Could not reach the robot at ${targetUrl}`,
      }, { status: 502 });
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
      delivery: data.delivery || [],
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
