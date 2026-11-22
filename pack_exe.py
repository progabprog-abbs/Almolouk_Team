import ssl
import sys
from PyInstaller.__main__ import run

# تخطي عقبة الشهادات
ssl._create_default_https_context = ssl._create_unverified_context

# التغليف الشامل الإجباري لجميع ملفات Flet والتشفير
sys.argv = [
    "pyinstaller",
    "--noconsole",
    "--name=Almolouk_Team",
    "--icon=icon_new.png",
    "--add-data=icon_new.png;.",
    "--add-data=bg.png;.",
    "--collect-all=flet",
    "--collect-all=flet_core",
    "--collect-all=flet_runtime",
    "--collect-all=cryptography",
    "main.py"
]

print("🚀 جاري بناء النظام التنفيذي باستخدام التجميع الشامل (Collect All)...")
run()