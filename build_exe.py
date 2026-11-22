import ssl
import sys
from PyInstaller.__main__ import run

# تجاوز فحص شهادات الأمان (SSL) أثناء التغليف
ssl._create_default_https_context = ssl._create_unverified_context

sys.argv = [
    "pyinstaller",
    "--noconsole",
    "--onedir",
    "--name=Almolouk_Team",
    "--icon=icon_new.png",
    "--add-data=icon_new.png;.",
    "--add-data=bg.png;.",
    "--add-data=views;views",
    "--hidden-import=cryptography",
    "--hidden-import=serial",
    "--hidden-import=requests",
    "main.py"
]

print("🚀 جاري بناء النسخة التنفيذية النهائية المتكاملة (Almolouk_Team.exe)...")
run()