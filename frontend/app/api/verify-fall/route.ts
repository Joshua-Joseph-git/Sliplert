import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Try to connect to backend
    let response;
    try {
      response = await fetch('http://localhost:8000/detect-fall-base64', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(body),
      });
    } catch (fetchError) {
      // Backend not running - return mock response for demo
      return NextResponse.json({
        confirmedFall: false,
        fallType: null,
        confidence: 0,
        bodyAngle: 0,
        mock: true
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
    });
  } catch (error) {
    console.error('Error verifying fall:', error);
    return NextResponse.json({
      confirmedFall: false,
      fallType: null,
      confidence: 0,
      bodyAngle: 0,
      error: 'Failed to verify fall'
    });
  }
}
