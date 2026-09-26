@echo off
rem Dung PipeCutStudio.exe va bo cai ngay tren may Windows cua ban.
rem Can: Python 3.10+ (python.org, tich "Add python.exe to PATH") va Inno Setup 6 (jrsoftware.org).
rem Chay tu thu muc goc du an:  packaging\build_windows.bat
setlocal
cd /d "%~dp0\.."

python -m pip install --upgrade pip || goto :fail
python -m pip install pyinstaller pyserial pillow || goto :fail
python packaging\make_icon.py || goto :fail
python -m PyInstaller packaging\pipecut.spec --noconfirm --clean || goto :fail

for /f %%v in ('python -c "import pipecut; print(pipecut.__version__)"') do set VER=%%v
dist\PipeCutStudio\pipecut.exe --version || goto :fail

set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% (
  echo Chua cai Inno Setup 6: da co ban chay lien o dist\PipeCutStudio\, chi thieu bo cai.
  goto :eof
)
%ISCC% /DAppVersion=%VER% packaging\installer.iss || goto :fail
echo.
echo Xong: dist\PipeCutStudio-%VER%-setup.exe
goto :eof

:fail
echo LOI - xem thong bao phia tren.
exit /b 1
