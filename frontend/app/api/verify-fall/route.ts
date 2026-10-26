import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const targetUrl = body.backendUrl || process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';

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
