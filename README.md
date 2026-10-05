# Tactile Visualiser – Stakeholder Demo

This folder contains the current prototype GUI for stakeholder testing.

## Quick start

### macOS
1. Install Python 3 if it is not already installed: https://www.python.org/downloads/
2. Double-click `Launch_Tactile_Visualiser.command`.
3. On first launch, the script creates a private environment, installs the required packages, then opens the GUI.
4. If macOS blocks the launcher, right-click it and choose **Open** once.

### Windows
1. Install Python 3 from: https://www.python.org/downloads/
2. During Python installation, enable **Add Python to PATH** and keep **pip** selected.
3. Double-click `Launch_Tactile_Visualiser.bat`.
4. The launcher checks Python/pip, installs any missing required packages for the current user, then opens the GUI.

This Windows launcher intentionally does **not** create a virtual environment because some managed or Microsoft Store Python installations can fail during `ensurepip`.

An internet connection is needed on the first launch only.

## Required Python packages
- customtkinter
- numpy
- opencv-python
- pyserial

## Current prototype features
- configurable tactile grids up to 32 × 32
- non-square grids such as 5 × 20
- selectable individual taxels
- simulated force input in newtons
- multiple active taxels
- live heatmap
- selected-taxel information
- selected-taxel / whole-grid average force history
- raw and normalised views
- calibration controls
- recording and playback
- CSV export
- sensor-health view
- light and dark mode
- preliminary automatic sensor-grid detection architecture

## Simulation controls
In **Live View**:
- hover over a taxel
- scroll up/down to change simulated force
- left-click to select a taxel
- right-click to clear a taxel
- multiple taxels can hold force values simultaneously

Simulation range: **0–40 N**.

## Live Sensor mode
The GUI includes separate **Simulation** and **Live Sensor** modes so simulated data cannot accidentally alter live measurements.

Real sensor hardware is not integrated yet. If no compatible hardware is connected, the GUI should report **No sensor detected**.

## Recording and CSV export
The GUI can record and replay tactile data over time.

CSV export includes:
- time
- data source
- row
- column
- force in newtons
- raw value
- normalised value

## Important
This is an early-development prototype for interface testing and stakeholder feedback. Real hardware calibration, communication timing, force validation, and sensor-health thresholds still require validation.

## Feedback requested
Please comment on:
- ease of navigation
- heatmap clarity
- taxel selection
- graph usefulness
- recording/playback controls
- calibration/settings clarity
- missing information
- unnecessary or distracting features

## Files
- `tactile_visualiser.py` – GUI source
- `Launch_Tactile_Visualiser.command` – macOS launcher
- `Launch_Tactile_Visualiser.bat` – Windows launcher
- `requirements.txt` – dependencies
- `README.md` – instructions
- `STAKEHOLDER_FEEDBACK.txt` – optional feedback template

## Windows troubleshooting

If the launcher reports that `pip` is unavailable or Python cannot be started, install/reinstall Python from **python.org** rather than relying on a restricted system installation.

Recommended:
- Python 3.11 or 3.12
- `pip` enabled
- `Add Python to PATH` enabled

The launcher installs packages with `--user`, so administrator rights should not normally be required.
