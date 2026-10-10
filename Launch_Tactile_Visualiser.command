#!/bin/bash
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 was not found."
  echo "Install it from https://www.python.org/downloads/"
  read -p "Press Enter to close..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "First launch: setting up the application..."
  python3 -m venv .venv || exit 1
fi

source .venv/bin/activate
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet

if [ $? -ne 0 ]; then
  echo "Package installation failed. Check your internet connection."
  read -p "Press Enter to close..."
  exit 1
fi

python tactile_visualiser.py

if [ $? -ne 0 ]; then
  echo "The GUI closed with an error."
  read -p "Press Enter to close..."
fi
