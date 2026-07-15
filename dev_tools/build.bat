@echo off
echo Starting PyInstaller Build...
rmdir /s /q dist
rmdir /s /q build

d:\AntigravityIDE\Applications\.venv\Scripts\pyinstaller.exe ^
    --name SmartSchoolBot ^
    --onedir ^
    --add-data "static;static" ^
    --add-data "liff;liff" ^
    --clean ^
    run.py

echo Build Complete!
pause
