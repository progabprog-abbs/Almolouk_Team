import flet as ft
import requests


def SyncSettingsView(page, db):
    DEFAULT_FIREBASE_URL = "https://kingsteam-671a6-default-rtdb.asia-southeast1.firebasedatabase.app/"
    saved_url = db.get_setting("api_url") or DEFAULT_FIREBASE_URL

    def notify(msg, color=ft.Colors.GREEN_700):
        page.open(ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color))

    sync_switch = ft.Switch(
        label="تفعيل المزامنة السحابية (Firebase / UltraMsg)",
        value=(db.get_setting("sync_enabled") == "1"),
    )
    api_url = ft.TextField(label="رابط منصة Firebase", value=saved_url, text_align="left")
    ultra_instance = ft.TextField(label="UltraMsg Instance ID", value=db.get_setting("ultra_instance"), text_align="left")
    ultra_token = ft.TextField(label="UltraMsg Token", value=db.get_setting("ultra_token"), password=True, can_reveal_password=True, text_align="left")

    sms_mode_dropdown = ft.Dropdown(
        label="وسيلة SMS عند انقطاع الإنترنت 📴",
        value=db.get_setting("offline_sms_mode", "android_gateway"),
        options=[
            ft.dropdown.Option("android_gateway", "بوابة هاتف أندرويد (Wi-Fi / Hotspot)"),
            ft.dropdown.Option("usb_modem", "مودم USB بشريحة SIM"),
        ],
    )
    sms_gateway_ip = ft.TextField(label="رابط بوابة الهاتف (http://192.168.43.1:8080/send)", value=db.get_setting("sms_gateway_ip"), text_align="left")
    sms_com_port = ft.TextField(label="منفذ المودم (COM3)", value=db.get_setting("sms_com_port", "COM3"), text_align="left")

    msg_input = ft.TextField(label="محتوى رسالة الواتساب", multiline=True)
    single_phone = ft.TextField(label="رقم الهاتف (+964...)", expand=True)

    def get_members_options():
        rows = db.get_records("members")
        valid = [r for r in rows if (r[2] or "").strip()]
        if not valid:
            return [ft.dropdown.Option(key="", text="لا يوجد أعضاء مسجلون بأرقام هواتف", disabled=True)]
        return [ft.dropdown.Option(key=str(r[2]), text=f"{r[1]} ({r[2]})") for r in valid]

    def on_member_select(e):
        if member_dropdown.value:
            single_phone.value = member_dropdown.value
            page.update()

    member_dropdown = ft.Dropdown(
        label="اختر عضواً من القائمة",
        options=get_members_options(),
        on_select=on_member_select,
        expand=True,
    )

    def refresh_members(e):
        member_dropdown.options = get_members_options()
        member_dropdown.value = None
        page.update()
        notify("تم تحديث قائمة الأعضاء بنجاح 🔄", ft.Colors.BLUE_700)

    def save_settings(e):
        db.set_setting("sync_enabled", "1" if sync_switch.value else "0")
        db.set_setting("api_url", (api_url.value or "").strip())
        db.set_setting("ultra_instance", (ultra_instance.value or "").strip())
        db.set_setting("ultra_token", (ultra_token.value or "").strip())
        db.set_setting("offline_sms_mode", sms_mode_dropdown.value or "android_gateway")
        db.set_setting("sms_gateway_ip", (sms_gateway_ip.value or "").strip())
        db.set_setting("sms_com_port", (sms_com_port.value or "").strip())
        notify("تم حفظ جميع إعدادات المزامنة والطوارئ ✔️", ft.Colors.GREEN_700)

    def test_firebase_connection(e):
        url = (api_url.value or "").strip()
        if not url:
            notify("يرجى إدخال رابط Firebase أولاً!", ft.Colors.RED_700)
            return
        try:
            res = requests.put(f"{url.rstrip('/')}/test_connection.json", json={"status": "connected", "team": "Almolouk"}, timeout=8)
            if res.status_code == 200:
                notify("تم الاتصال بنجاح بـ Firebase! قاعدة البيانات تستجيب 🟢", ft.Colors.GREEN_700)
            else:
                notify(f"رفض السيرفر الاتصال: {res.status_code}", ft.Colors.ORANGE_800)
        except Exception:
            notify("فشل الوصول للسيرفر، تأكد من اتصال الإنترنت.", ft.Colors.RED_700)

    def send_whatsapp_msg(e):
        instance = (ultra_instance.value or "").strip()
        token = (ultra_token.value or "").strip()
        phone = (single_phone.value or "").strip()
        msg = (msg_input.value or "").strip()
        if not instance or not token or not phone or not msg:
            notify("يرجى ملء الحقول (Instance, Token, الرقم، والرسالة) ⚠️", ft.Colors.RED_700)
            return
        try:
            response = requests.post(f"https://api.ultramsg.com/{instance}/messages/chat", data={"token": token, "to": phone, "body": msg}, timeout=10)
            if response.status_code == 200 and '"sent":"true"' in response.text:
                notify("تم إرسال رسالة الواتساب بنجاح! ✔️", ft.Colors.GREEN_700)
            else:
                notify(f"رد السيرفر: {response.text}", ft.Colors.ORANGE_800)
        except Exception:
            notify("فشل الاتصال بالخادم، تأكد من الإنترنت.", ft.Colors.RED_700)

    def clear_msg_fields(e):
        member_dropdown.value = None
        single_phone.value = ""
        msg_input.value = ""
        page.update()

    return ft.Container(
        padding=10,
        expand=True,
        content=ft.Column(
            [
                ft.Text("إعدادات المزامنة والرسائل القصيرة ☁️", size=20, weight="bold", color=ft.Colors.AMBER),
                ft.Card(
                    content=ft.Container(
                        padding=16,
                        content=ft.Column(
                            [
                                sync_switch,
                                api_url,
                                ultra_instance,
                                ultra_token,
                                ft.Divider(height=10),
                                ft.Text("إعدادات وضع الطوارئ (SMS) 📴", weight="bold", color=ft.Colors.AMBER_200),
                                sms_mode_dropdown,
                                sms_gateway_ip,
                                sms_com_port,
                                ft.Row(
                                    [
                                        ft.Button(content=ft.Text("حفظ الإعدادات", weight="bold"), on_click=save_settings, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE, expand=True),
                                        ft.Button(content=ft.Text("فحص Firebase 🔌"), on_click=test_firebase_connection, bgcolor=ft.Colors.TEAL_700, color=ft.Colors.WHITE),
                                    ],
                                    spacing=8,
                                ),
                            ],
                            spacing=8,
                        ),
                    )
                ),
                ft.Card(
                    content=ft.Container(
                        padding=16,
                        content=ft.Column(
                            [
                                ft.Text("إرسال رسائل WhatsApp فردية 💬", weight="bold"),
                                ft.Row([member_dropdown, ft.IconButton(icon=ft.Icons.REFRESH, tooltip="تحديث", on_click=refresh_members, icon_color=ft.Colors.AMBER)]),
                                single_phone,
                                msg_input,
                                ft.Row(
                                    [
                                        ft.Button(content=ft.Text("إرسال الواتساب الآن", weight="bold"), on_click=send_whatsapp_msg, bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, expand=True),
                                        ft.Button(content=ft.Text("تفريغ"), on_click=clear_msg_fields, bgcolor=ft.Colors.GREY_700, color=ft.Colors.WHITE),
                                    ],
                                    spacing=8,
                                ),
                            ],
                            spacing=8,
                        ),
                    )
                ),
            ],
            scroll=ft.ScrollMode.ALWAYS,
        ),
    )
