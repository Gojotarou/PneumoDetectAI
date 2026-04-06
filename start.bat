@echo off
REM Start PneumoDetect Flask Application

echo Starting PneumoDetect Flask Server...
echo.
echo Opening Google Chrome in 2 seconds...
echo.

REM Start Flask in background (new command window)
start cmd /k py app.py

REM Wait 2 seconds for server to start
timeout /t 2 /nobreak

REM Open Chrome automatically
start chrome http://localhost:5000

echo.
echo Chrome should open automatically. If not, visit: http://localhost:5000
echo.
echo To stop the server: Close the Flask command window or press Ctrl+C there
pause
