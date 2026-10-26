#!/bin/bash
# One-step SlipLert setup for the Raspberry Pi. Safe to run again any time (after a reinstall,
# moving the folder, or a corrupted .venv):
#     bash setup_pi.sh
set -e
BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$BACKEND_DIR"
echo "SlipLert folder: $BACKEND_DIR"

echo
echo "== 1/5 Raspberry Pi camera + motor packages"
missing=()
python3 -c "import picamera2" 2>/dev/null || missing+=(python3-picamera2)
python3 -c "import lgpio" 2>/dev/null || missing+=(python3-lgpio)
if [ ${#missing[@]} -gt 0 ]; then
    echo "Installing: ${missing[*]}"
    sudo apt-get install -y "${missing[@]}" || { sudo apt-get update && sudo apt-get install -y "${missing[@]}"; }
else
    echo "Already installed"
fi

echo
echo "== 2/5 Python environment (.venv that can see the Pi camera and motor driver)"
if [ ! -x .venv/bin/python ] || ! grep -q "include-system-site-packages = true" .venv/pyvenv.cfg 2>/dev/null; then
    python3 -m venv --system-site-packages --clear .venv
    echo "Created a fresh .venv"
else
    echo ".venv already set up correctly"
fi

echo
echo "== 3/5 Python packages (first time can take several minutes)"
.venv/bin/pip install -r requirements.txt

echo
echo "== 4/5 Checking everything can load"
.venv/bin/python -c "import fastapi, cv2, numpy; print('Server + OpenCV: OK')"
.venv/bin/python -c "import picamera2; print('Pi camera library: OK')" || echo "WARNING: Pi camera library not loading - is the camera enabled and the ribbon cable seated?"
.venv/bin/python -c "import lgpio; print('Motor driver library: OK')" || echo "WARNING: motor driver library (lgpio) not loading"

echo
echo "== 5/5 Auto-start on boot (points it at THIS folder)"
bash install_service.sh
sudo systemctl restart sliplert
echo "Waiting for SlipLert to start..."
sleep 12
journalctl -u sliplert -n 30 --no-pager

echo
echo "Done. In the dashboard, type this address and click Connect:  $(hostname -I | awk '{print $1}')"
echo "Live logs any time:  journalctl -u sliplert -f"
