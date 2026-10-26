#!/bin/bash
set -e
BACKEND_DIR="$(cd "$(dirname "$0")" && pwd)"

sudo tee /etc/systemd/system/sliplert.service > /dev/null <<EOF
[Unit]
Description=SlipLert Robot Backend
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$BACKEND_DIR
ExecStart=$BACKEND_DIR/.venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now sliplert.service
echo "SlipLert will now start automatically on boot."
echo "Check it with: sudo systemctl status sliplert"
echo "Live logs:     journalctl -u sliplert -f"
