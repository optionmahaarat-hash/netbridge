@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================================
echo   NetBridge Lite - build Setup.exe for the family (Windows)
echo ============================================================
python --version >nul 2>&1 || (echo Python is not installed / not in PATH. & pause & exit /b 1)

echo [1/6] Installing build tools ...
python -m pip install -r requirements.txt pyinstaller || goto :err

echo [2/6] Xray core ...
python get_xray.py || goto :err

echo [3/6] Servers every new install starts with (from data\profiles.json) ...
python tools\make_seed.py || goto :err

echo [4/6] Update signing key (created only once) ...
python tools\gen_update_keys.py || goto :err

echo [5/6] Building the program ...
python -m PyInstaller --noconfirm --clean NetBridgeLite.spec || goto :err
xcopy /E /I /Y cores dist\NetBridgeLite\cores >nul
python tools\make_release.py || goto :err

echo [6/6] Making Setup.exe (Inno Setup) ...
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
for /f %%V in ('python -c "from app.lite.version import LITE_VERSION as v; print(v)"') do set "VER=%%V"
echo Using: %ISCC%
"%ISCC%" /DAppVersion=%VER% installer\NetBridgeLite.iss
if errorlevel 1 (echo. & echo Inno Setup reported an error - read the lines above. & goto :err)
if not exist "release\NetBridgeLite-Setup-%VER%.exe" (echo. & echo Setup.exe was NOT created - read the lines above. & goto :err)

echo.
echo ============================================================
echo  DONE.
echo   Give the family :  release\NetBridgeLite-Setup-%VER%.exe   (double-click, Next, done)
echo   For updates     :  upload release\NetBridgeLite-%VER%-win64.zip AND release\latest.json to the same web folder
echo ============================================================
pause
exit /b 0
:err
echo.
echo BUILD FAILED - see the message above.
pause
exit /b 1
