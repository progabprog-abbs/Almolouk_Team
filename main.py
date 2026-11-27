import os
import sys
import traceback
import flet as ft

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
if APP_ROOT not in sys.path:
    sys.path.insert(0, APP_ROOT)


def resource_path(relative_path):
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, relative_path)
    p1 = os.path.join(APP_ROOT, relative_path)
    if os.path.exists(p1):
        return p1
    p2 = os.path.join(APP_ROOT, "assets", relative_path)
    if os.path.exists(p2):
        return p2
    return p1


import urllib.parse

def open_share_qr_dialog(page):
    ios_url_field = ft.TextField(
        label="رابط التثبيت المباشر للآيفون (iPhone OTA / Web)",
        value="https://almolouk-team.netlify.app",
        text_align="left",
        border_radius=10,
    )
    qr_image = ft.Image(
        src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https%3A%2F%2Falmolouk-team.netlify.app",
        width=190,
        height=190,
        fit=ft.BoxFit.CONTAIN,
    )

    def refresh_qr(ev):
        u = (ios_url_field.value or "").strip()
        if u:
            qr_image.src = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={urllib.parse.quote(u, safe='')}"
            qr_image.update()

    ios_url_field.on_change = refresh_qr

    dlg = ft.AlertDialog(
        modal=True,
        title=ft.Text("📲 تثبيت التطبيق على الآيفون والأندرويد", weight="bold", color=ft.Colors.AMBER),
        content=ft.Column(
            [
                ft.Text("اطلب من عضو الآيفون توجيه الكاميرا نحو الرمز ليتم التثبيت فوراً:", size=13),
                ft.Container(content=qr_image, bgcolor=ft.Colors.WHITE, padding=10, border_radius=12, alignment=ft.Alignment.CENTER),
                ios_url_field,
            ],
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=10,
        ),
        actions=[ft.IconButton(icon=ft.Icons.QR_CODE_2, icon_color=ft.Colors.AMBER, tooltip="مشاركة التطبيق (iPhone / Android)", on_click=lambda e: open_share_qr_dialog(page)), 
            ft.TextButton(content=ft.Text("إغلاق"), on_click=lambda ev: page.close(dlg)),
        ],
    )
    page.open(dlg)

def main(page: ft.Page):
    # 1. رسم الإطار الأول فوراً قبل أي استيراد أو قاعدة بيانات (يمنع الشاشة البيضاء 100%)
    page.title = "فريق الملوك لكرة القدم"
    page.theme_mode = ft.ThemeMode.DARK
    page.bgcolor = "#0B1120"
    page.dark_theme = ft.Theme(
        color_scheme_seed=ft.Colors.AMBER,
        scaffold_bgcolor="#0B1120",
    )
    page.theme = ft.Theme(
        color_scheme_seed=ft.Colors.AMBER,
        scaffold_bgcolor="#0B1120",
    )
    page.rtl = True
    page.padding = 0

    boot_status = ft.Text("جاري تشغيل نظام فريق الملوك... ⚽", size=16, color=ft.Colors.AMBER, weight="bold")
    boot_box = ft.Container(
        bgcolor="#0B1120",
        expand=True,
        alignment=ft.Alignment.CENTER,
        padding=20,
        content=ft.Column(
            [
                ft.Icon(ft.Icons.SPORTS_SOCCER, size=60, color=ft.Colors.AMBER),
                boot_status,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.AUTO,
        ),
    )
    page.add(boot_box)
    page.update()

    def show_fatal_error(stage, err_text):
        boot_box.content = ft.Column(
            [
                ft.Text(f"⚠️ توقف التشغيل في مرحلة: {stage}", size=17, weight="bold", color=ft.Colors.RED_400),
                ft.Divider(),
                ft.Text(err_text, size=12, color=ft.Colors.WHITE, selectable=True),
            ],
            scroll=ft.ScrollMode.AUTO,
        )
        page.update()

    # 2. تهيئة طبقة التوافق ومجلد التخزين الآمن بعد ظهور الشاشة
    try:
        import flet_compat
        flet_compat.apply_flet_compat()

        if sys.platform == "win32":
            app_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else APP_ROOT
            os.chdir(app_dir)
        else:
            data_dir = os.getenv("FLET_APP_STORAGE_DATA") or os.path.expanduser("~")
            os.makedirs(data_dir, exist_ok=True)
            if os.access(data_dir, os.W_OK):
                os.chdir(data_dir)
    except Exception:
        show_fatal_error("تهيئة التخزين والتوافق", traceback.format_exc())
        return

    # 3. استيراد الوحدات وقاعدة البيانات داخل حماية كاملة
    try:
        from database import DatabaseManager
        from views.login import LoginView
        from views.data_manage import DataManageView
        from views.notifications import NotificationsView
        from views.chat import ChatView
        from views.sync_settings import SyncSettingsView
        db = DatabaseManager()
        from android_notifier import AndroidSystemNotifier
        sys_notifier = AndroidSystemNotifier(page, db)
        sys_notifier.start_background_listener()
        try:
            if hasattr(ft, "Wakelock"):
                wl = ft.Wakelock()
                if hasattr(page, "services"):
                    page.services.append(wl)
                if hasattr(wl, "enable"):
                    res_wl = wl.enable()
                    import inspect as _insp
                    if _insp.isawaitable(res_wl):
                        async def _en_wl(c=res_wl):
                            try:
                                await c
                            except Exception:
                                pass
                        page.run_task(_en_wl)
        except Exception:
            pass
    except Exception:
        show_fatal_error("تحميل الوحدات وقاعدة البيانات", traceback.format_exc())
        return

    # 4. إدارة التنقل بين الشاشات مباشرة داخل root_host عبر page.add (الأكثر استقراراً في Flet 1.1.2)
    icon_file = resource_path("icon_new.png")
    root_host = ft.Container(expand=True, bgcolor="#0B1120")

    def navigate_to(route_name):
        try:
            page.route = route_name
            if route_name == "/login" or route_name == "/":
                root_host.content = LoginView(page, db)

            elif route_name == "/dashboard":
                user = page.session.get("user") or "مستخدم"
                role = page.session.get("role") or "member"
                phone = page.session.get("phone") or ""
                is_dev = db.is_developer(user, phone)
                if is_dev:
                    role = "admin"
                    page.session.set("role", "admin")

                v_notif = NotificationsView(db, role, page)
                v_chat = ChatView(db, user, page)

                if is_dev:
                    # المطور الرئيسي (Abbas Almoola): كافة الصلاحيات المطلقة للنظام
                    v_data = DataManageView(db, page)
                    v_sync = SyncSettingsView(page, db)
                    main_container = ft.Container(content=v_data, expand=True)
                    dest = [
                        ft.NavigationBarDestination(icon=ft.Icons.PEOPLE, label="البيانات"),
                        ft.NavigationBarDestination(icon=ft.Icons.NOTIFICATIONS, label="الإشعارات"),
                        ft.NavigationBarDestination(icon=ft.Icons.CHAT, label="الدردشة"),
                        ft.NavigationBarDestination(icon=ft.Icons.SYNC, label="المزامنة"),
                    ]

                    def on_nav(e):
                        idx = e.control.selected_index
                        if idx == 0:
                            main_container.content = v_data
                        elif idx == 1:
                            main_container.content = v_notif
                        elif idx == 2:
                            main_container.content = v_chat
                        elif idx == 3:
                            main_container.content = v_sync
                        page.update()
                elif role == "admin":
                    # المخول الثانوي (المدير): محجوب نهائياً عن البيانات والسجلات، وله فقط ما يحدده المطور
                    db.sync_admin_permissions_from_cloud(user)
                    perms = db.get_admin_permissions(user, phone)
                    v_sync = SyncSettingsView(page, db)
                    allowed_views = []
                    dest = []
                    if perms.get("notif", True):
                        allowed_views.append(v_notif)
                        dest.append(ft.NavigationBarDestination(icon=ft.Icons.NOTIFICATIONS, label="الإشعارات"))
                    if perms.get("chat", True):
                        allowed_views.append(v_chat)
                        dest.append(ft.NavigationBarDestination(icon=ft.Icons.CHAT, label="الدردشة"))
                    if perms.get("sync", True):
                        allowed_views.append(v_sync)
                        dest.append(ft.NavigationBarDestination(icon=ft.Icons.SYNC, label="المزامنة"))
                    if not allowed_views:
                        allowed_views = [v_chat]
                        dest = [ft.NavigationBarDestination(icon=ft.Icons.CHAT, label="الدردشة")]
                    if len(dest) < 2:
                        allowed_views.append(v_notif)
                        dest.append(ft.NavigationBarDestination(icon=ft.Icons.NOTIFICATIONS, label="الإشعارات"))

                    main_container = ft.Container(content=allowed_views[0], expand=True)

                    def on_nav(e):
                        idx = e.control.selected_index
                        if 0 <= idx < len(allowed_views):
                            main_container.content = allowed_views[idx]
                        page.update()
                else:
                    main_container = ft.Container(content=v_notif, expand=True)
                    dest = [
                        ft.NavigationBarDestination(icon=ft.Icons.NOTIFICATIONS, label="الإشعارات"),
                        ft.NavigationBarDestination(icon=ft.Icons.CHAT, label="الدردشة"),
                    ]

                    def on_nav(e):
                        idx = e.control.selected_index
                        if idx == 0:
                            main_container.content = v_notif
                        elif idx == 1:
                            main_container.content = v_chat
                        page.update()

                app_bar = ft.Container(
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    padding=ft.Padding.symmetric(horizontal=12, vertical=8),
                    content=ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Image(src=icon_file, width=32, height=32, fit=ft.BoxFit.CONTAIN)
                                    if os.path.exists(icon_file)
                                    else ft.Icon(ft.Icons.SPORTS_SOCCER, color=ft.Colors.AMBER),
                                    ft.Text(f"أهلاً {user}", size=18, weight="bold"),
                                ]
                            ),
                            ft.IconButton(
                                ft.Icons.LOGOUT,
                                on_click=lambda e: navigate_to("/login"),
                                tooltip="تسجيل خروج",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                )

                footer = ft.Container(
                    content=ft.Text("Devloper Mahammd Almoola 2026", size=11, color=ft.Colors.GREY_500),
                    alignment=ft.Alignment.CENTER,
                    padding=4,
                )

                root_host.content = ft.Column(
                    [
                        app_bar,
                        main_container,
                        ft.NavigationBar(destinations=dest, on_change=on_nav, selected_index=0),
                        footer,
                    ],
                    expand=True,
                    spacing=0,
                )

            page.controls.clear()
            page.add(root_host)
            page.update()
        except Exception:
            page.controls.clear()
            page.add(boot_box)
            show_fatal_error(f"بناء الشاشة ({route_name})", traceback.format_exc())

    page.go = navigate_to

    if not hasattr(page, "open"):
        def _safe_open(ctrl):
            ctrl.open = True
            if ctrl not in page.overlay:
                page.overlay.append(ctrl)
            page.update()
        page.open = _safe_open

    navigate_to("/login")


if __name__ == "__main__":
    ft.run(main, assets_dir=APP_ROOT)
