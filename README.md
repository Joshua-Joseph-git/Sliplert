# SlipLert - AI-Powered Fall Detection System

Ai powered fall detection system
## Features

- **Media pipe that looks at poses**: Uses MediaPipe pose detection to analyze body movements to see if the elderly fall
- **Autonomous Robot Following**: Robot autonomously follows the elderly person using computer vision, via the camera 
and it outputs to the app
- **Real-Time Monitoring**: Live video feed with pose overlay and fall detection
- **Emergency Contact**: Automatic notification to configured emergency contacts when falls are detected
- **Dashboard**: Modern Next.js frontend with real-time telemetry and system logs
- **Customizable Settings**: Theme customization and emergency contact management

## Architecture

### Frontend (Next.js)
- **Home Page**: Landing page with feature overview
- **Dashboard**: Monitoring with video feed, fall detection, and system telemetry
- **Settings**: Theme customization and emergency contact management

### Backend (FastAPI)
- **Fall Detection API**: MediaPipe-based pose analysis
- **Emergency Contact Management**: CRUD operations for emergency contacts
- **Robot Control API**: Motor control and autonomous mode
- **WebSocket Support**: Real-time video streaming, that is shown on the App 

### Robot Controller
- **Autonomous Following**: Computer vision-based person tracking
- **Obstacle Avoidance**: Distance sensor integration
- **GPIO Control**: Raspberry Pi motor control via gpiozero

## Project Structure

```
CONGESSIONAL APP CONTEST 2026/
├── frontend/                 # Next.js frontend
│   ├── app/
│   │   ├── page.tsx         # Home page
│   │   ├── dashboard/       # Monitoring dashboard
│   │   ├── settings/        # Settings page
│   │   └── api/             # API routes
│   └── package.json
├── Backend/                  # FastAPI backend
│   ├── main.py              # Main API server
│   ├── autonomous_controller.py  # Autonomous robot control
│   ├── requirements.txt     # Python dependencies
│   └── .env.example         # Environment variables template
└── README.md
```





- Node.js 18+ and npm
- Python 3.9+
- Raspberry Pi (for robot deployment)
- Webcam/Camera

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The frontend will be available at `http://localhost:3000`

### Backend Setup

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

The backend API will be available at `http://localhost:8000`

### API Documentation

Once the backend is running, visit `http://localhost:8000/docs` for interactive API documentation.

## API Endpoints

### Fall Detection
- `POST /detect-fall` - Upload image for fall detection
- `POST /detect-fall-base64` - Send base64-encoded image for fall detection

### Emergency Contacts
- `POST /emergency-contacts` - Add emergency contact
- `GET /emergency-contacts` - Get all emergency contacts
- `DELETE /emergency-contacts/{id}` - Delete emergency contact

### Robot Control
- `POST /robot/control` - Control robot movement
- `POST /robot/autonomous` - Toggle autonomous mode
- `GET /robot/status` - Get robot status

### WebSocket
- `WS /ws/video` - Real-time video streaming and analysis

## Robot Hardware Setup

### Required Components
- Raspberry Pi 4
- Motor driver (L298N or similar)
- 2 DC motors with wheels
- Ultrasonic distance sensors (HC-SR04) - optional
- Webcam
- Power supply

### GPIO Pin Configuration
Default configuration (can be changed in `.env`):
- Left Motor Forward: GPIO 17
- Left Motor Backward: GPIO 18
- Right Motor Forward: GPIO 22
- Right Motor Backward: GPIO 23

### Wiring Diagram
```
Raspberry Pi          Motor Driver
GPIO 17    -------->  IN1
GPIO 18    -------->  IN2
GPIO 22    -------->  IN3
GPIO 23    -------->  IN4
5V         -------->  VCC
GND        -------->  GND
```

## Fall Detection Algorithm

The system uses multiple criteria to detect falls:

1. **Body Angle**: Measures the angle of the torso from vertical (>60° indicates fall)
2. **Velocity**: Calculates downward velocity of the person's center
3. **Vertical Alignment**: Measures how well body parts are aligned vertically
4. **Sudden Changes**: Detects rapid changes in posture

## Emergency Contact Configuration

1. Navigate to the Settings page
2. Click "Add Contact"
3. Fill in:
   - Name
   - Phone number (with country code, e.g., +1)
   - Relationship
4. Click "Add Contact"

When a fall is detected, the system will automatically call all configured contacts.

## Testing

### Test Fall Detection
1. Navigate to the Dashboard
2. Click "Simulate Fall Trajectory" to test the system
3. The system will analyze the frame and trigger an alert if a fall is detected

### Test Robot Control
```bash
# Move forward
curl -X POST http://localhost:8000/robot/control -H "Content-Type: application/json" -d '{"action": "forward", "speed": 50}'

# Stop
curl -X POST http://localhost:8000/robot/control -H "Content-Type: application/json" -d '{"action": "stop"}'
```

## Deployment

### GitHub Upload
See [GITHUB_DEPLOYMENT.md](./GITHUB_DEPLOYMENT.md) for detailed instructions.

### Raspberry Pi Deployment
See [RASPBERRY_PI_DEPLOYMENT.md](./RASPBERRY_PI_DEPLOYMENT.md) for detailed instructions.

## Troubleshooting

### Camera not working
- Ensure camera permissions are granted
- Check if another application is using the camera
- Try restarting the backend server

### GPIO not working
- Ensure you're running on a Raspberry Pi
- Check GPIO pin connections
- Verify no other process is using the GPIO pins
- Run with sudo if needed

### Fall detection not accurate
- Ensure good lighting conditions
- Adjust thresholds in `main.py` (FALL_VELOCITY_THRESHOLD, FALL_BODY_ANGLE_THRESHOLD)
- Ensure camera is positioned correctly

## Congressional App Contest 2026

This project was developed for the Congressional App Contest 2026. It demonstrates the use of AI and robotics to improve elderly care and safety.

## License

MIT License

## Acknowledgments

- MediaPipe for pose detection
- FastAPI for the backend framework
- Next.js for the frontend framework
- gpiozero for Raspberry Pi GPIO control
