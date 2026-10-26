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

When a fall is detected, the robot stops and every saved contact gets an email (or a text/call for phone numbers when Twilio is configured).

## Testing

### Test Fall Detection
1. Navigate to the Dashboard
2. Click "Simulate Fall Trajectory" to test the system
3. The system will analyze the frame and trigger an alert if a fall is detected

### Raspberry Pi Setup (also fixes a reinstalled or moved SlipLert folder)
```bash
cd ~/Documents/Sliplert/Backend     # wherever your copy lives
bash setup_pi.sh
```
This installs the Pi camera and motor packages, rebuilds `.venv` so it can see them, installs the
requirements, and points the auto-start service at this folder. It ends by printing the address to type
into the dashboard.

### Test the Motors (do this first on the Pi)
Lift the car so the wheels are off the ground, then:
```bash
cd ~/Sliplert/Backend
sudo systemctl stop sliplert        # frees the GPIO pins
.venv/bin/python motor_test.py      # runs each wheel/turn and tells you which .env flag to flip
sudo systemctl start sliplert
```
If it prints `Motors are NOT working`, the message says why (missing GPIO driver -> `sudo apt install python3-lgpio`,
pins in use, etc.). The dashboard shows the same message in a yellow box under Robot Car Control.

### Test Robot Control
Each command drives for `duration` seconds and then stops by itself (the dashboard re-sends it while a button is held):
```bash
curl -X POST http://PI_IP:8000/robot/control -H "Content-Type: application/json" -d '{"action": "forward", "duration": 1.0}'
curl -X POST http://PI_IP:8000/robot/control -H "Content-Type: application/json" -d '{"action": "stop"}'
```

### Automatic Checks
```bash
cd Backend
python -m unittest test_robot_logic -v   # motors (fake pins), steering, search, pose geometry, API, alerts
```

### Reliable Alert Emails
Put a Gmail address and a Gmail **App Password** in `Backend/.env` (`SMTP_EMAIL`, `SMTP_PASSWORD`, see `.env.example`).
Without them the Pi tries direct delivery on port 25, which most home internet providers block. The dashboard's
Email Outbox shows DELIVERED or FAILED (with the reason) for every contact.

### Open the Dashboard Over http://
Run the frontend with `npm run dev` and open `http://localhost:3000` on a computer on the same Wi-Fi as the Pi.
A page served over https:// (for example a Vercel deployment) cannot talk to the Pi's `http://` address.

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
