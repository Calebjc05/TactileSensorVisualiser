@echo off
setlocal
cd /d "%~dp0"

echo ==============================================
echo  Tactile Visualiser - Stakeholder Demo
echo ==============================================
echo.

REM Prefer the Python launcher if available.
where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON=py"
) else (
    where python >nul 2>nul
    if %errorlevel% neq 0 (
        echo Python 3 was not found on this computer.
        echo.
        echo Please install Python 3 from:
        echo https://www.python.org/downloads/
        echo.
        echo During installation, enable "Add Python to PATH".
        echo.
        pause
        exit /b 1
    )
    set "PYTHON=python"
)

echo Checking Python...
%PYTHON% --version
if %errorlevel% neq 0 (
    echo.
    echo Python could not be started correctly.
    pause
    exit /b 1
)

echo.
echo Checking pip...
%PYTHON% -m pip --version >nul 2>nul

if %errorlevel% neq 0 (
    echo pip is not available in this Python installation.
    echo.
    echo Please reinstall Python from:
    echo https://www.python.org/downloads/
    echo.
    echo Make sure "pip" and "Add Python to PATH" are enabled.
    pause
    exit /b 1
)

echo.
echo Installing/checking required packages...
%PYTHON% -m pip install --user -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo Package installation failed.
    echo Please check your internet connection and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo Launching Tactile Visualiser...
%PYTHON% tactile_visualiser.py

if %errorlevel% neq 0 (
    echo.
    echo The GUI closed with an error.
    echo Please copy the error message above and send it back to the developer.
    echo.
    pause
)

endlocal
