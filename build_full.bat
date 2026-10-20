@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================================
echo   NetBridge (full) - build Setup.exe (Windows)
echo ============================================================
python --version >nul 2>&1 || (echo Python is not installed / not in PATH. & pause & exit /b 1)
echo [1/4] Installing build tools ...
python -m pip install -r requirements.txt pyinstaller || goto :err
echo [2/4] Xray core ...
python get_xray.py || goto :err
echo [3/4] Building the program ...
python -m PyInstaller --noconfirm --clean NetBridge.spec || goto :err
xcopy /E /I /Y cores dist\NetBridge\cores >nul
echo [4/4] Making Setup.exe (Inno Setup) ...
set "ISCC="
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
if not defined ISCC (
  echo Inno Setup is not installed - installing it with winget ...
  winget install --id JRSoftware.InnoSetup -e --silent --accept-package-agreements --accept-source-agreements
  for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
  echo Could not find Inno Setup. Install it from https://jrsoftware.org/isdl.php then run this file again.
  goto :err
)
for /f %%V in ('python -c "from app.version import VERSION as v; print(v)"') do set "VER=%%V"
"%ISCC%" /DAppVersion=%VER% installer\NetBridge.iss || goto :err
echo ============================================================
echo  DONE:  release\NetBridge-Setup-%VER%.exe
echo ============================================================
pause
exit /b 0
:err
echo.
echo BUILD FAILED - see the message above.
pause
exit /b 1
