#!/bin/bash

echo "📦 Installing dependencies..."
pip install -r requirements.txt

echo "🚀 Starting Sniper Bot..."
python bot.py
