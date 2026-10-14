@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================================
echo   NetBridge Lite - build the program (Windows)
echo ============================================================
python --version >nul 2>&1 || (echo Python is not installed / not in PATH. & pause & exit /b 1)

echo [1/5] Installing build tools ...
python -m pip install -r requirements.txt pyinstaller || goto :err

echo [2/5] Xray core ...
python get_xray.py || goto :err

echo [3/5] Update signing key (created only once) ...
python tools\gen_update_keys.py || goto :err

echo [4/5] Building NetBridgeLite.exe ...
python -m PyInstaller --noconfirm --clean NetBridgeLite.spec || goto :err
xcopy /E /I /Y cores dist\NetBridgeLite\cores >nul

echo [5/5] Making the release zip + signed latest.json ...
python tools\make_release.py || goto :err

echo.
echo ============================================================
echo  DONE.
echo   Program folder : dist\NetBridgeLite\   (run NetBridgeLite.exe)
echo   For the family : release\NetBridgeLite-*-win64.zip   (they unzip and run NetBridgeLite.exe)
echo   For updates    : upload the zip AND release\latest.json to the same web folder
echo ============================================================
pause
exit /b 0
:err
echo.
echo BUILD FAILED - see the message above.
pause
exit /b 1
