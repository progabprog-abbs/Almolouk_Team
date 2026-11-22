import ssl
import sys
from flet_cli.cli import main

# إيقاف فحص شهادات الأمان (SSL) مؤقتاً لتجاوز الحجب والخطأ
ssl._create_default_https_context = ssl._create_unverified_context

# تمرير أمر بناء تطبيق الأندرويد برمجياً
sys.argv = ["flet", "build", "apk", "--project", "KingsTeam", "--org", "com.almoola.kings"]

print("🚀 جاري تخطي فحص شهادات الأمان وبدء بناء التطبيق...")
main()