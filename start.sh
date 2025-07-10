#!/bin/bash
echo "[✔] Installing requirements..."
pip install -r requirements.txt

echo "[🚀] Starting RipperBot..."
python bot.py
