import os
import threading
from datetime import datetime, timedelta
import flet as ft


def NotificationsView(db, role, page):
    notif_list = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)

    sound_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notify.wav")
    if not os.path.exists(sound_path):
        sound_path = "notify.wav"

    def play_notif_sound():
        try:
            import flet_audio as fta
            if not os.path.exists(sound_path) or not hasattr(fta, "Audio"):
                return
            # في Flet 1.1.2 يجب إضافة Audio إلى page.services وليس page.overlay حتى لا يُرسم شريط مرئي على الشاشة
            if hasattr(page, "services"):
                for s in list(page.services):
                    if isinstance(s, fta.Audio):
                        try:
                            page.services.remove(s)
                        except Exception:
                            pass
                player = fta.Audio(src=sound_path, autoplay=True)
                page.services.append(player)
                page.update()
        except Exception:
            pass

    def notify(msg, color=ft.Colors.GREEN_700):
        page.open(ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color))

    type_dropdown = ft.Dropdown(
        label="نوع الإشعار",
        value="تدريب",
        options=[
            ft.dropdown.Option("تدريب", "تدريب ⚽"),
            ft.dropdown.Option("مباراة", "مباراة 🏆"),
            ft.dropdown.Option("اجتماع", "اجتماع 📋"),
            ft.dropdown.Option("إداري", "إداري 📢"),
            ft.dropdown.Option("عاجل", "عاجل 🚨"),
        ],
        expand=True,
    )

    duration_dropdown = ft.Dropdown(
        label="مدة الصلاحية ⏳",
        value="7",
        options=[
            ft.dropdown.Option("1", "يوم واحد (24 ساعة)"),
            ft.dropdown.Option("3", "3 أيام"),
            ft.dropdown.Option("7", "أسبوع واحد (7 أيام)"),
            ft.dropdown.Option("30", "شهر واحد (30 يوماً)"),
            ft.dropdown.Option("0", "دائم (بدون انتهاء)"),
        ],
        expand=True,
    )

    content_input = ft.TextField(
        label="اكتب نص الإشعار للأعضاء...",
        multiline=True,
        min_lines=2,
        max_lines=4,
    )

    DURATION_LABELS = {"1": "يوم واحد", "3": "3 أيام", "7": "أسبوع", "30": "شهر", "0": "دائم"}

    def encode_content(raw_text, duration_days):
        label = DURATION_LABELS.get(duration_days, "أسبوع")
        if duration_days == "0":
            exp_str = "PERMANENT"
        else:
            exp_str = (datetime.now() + timedelta(days=int(duration_days))).strftime("%Y-%m-%d %H:%M")
        return f"[DUR:{label}|{exp_str}]\n{raw_text}"

    def parse_content(stored_text):
        txt = str(stored_text or "")
        if txt.startswith("[DUR:") and "]\n" in txt:
            header, actual = txt.split("]\n", 1)
            parts = header.replace("[DUR:", "").split("|")
            dur_label = parts[0] if len(parts) > 0 else "دائم"
            exp_str = parts[1] if len(parts) > 1 else "PERMANENT"
            is_exp = False
            info = f"المدة: {dur_label}"
            if exp_str != "PERMANENT":
                try:
                    if datetime.now() > datetime.strptime(exp_str, "%Y-%m-%d %H:%M"):
                        is_exp = True
                    info = f"المدة: {dur_label} (ينتهي: {exp_str})"
                except Exception:
                    pass
            return actual, info, is_exp
        return txt, "المدة: دائم", False

    def get_badge_color(ntype):
        return {
            "عاجل": ft.Colors.RED_700,
            "مباراة": ft.Colors.GREEN_700,
            "تدريب": ft.Colors.BLUE_700,
            "اجتماع": ft.Colors.PURPLE_700,
            "إداري": ft.Colors.TEAL_700,
        }.get(ntype, ft.Colors.GREY_700)

    def delete_notif_action(nid):
        db.delete_notification(nid)
        load_notifications()
        notify("تم حذف الإشعار 🗑️", ft.Colors.GREY_800)

    def build_card(nid, title, body, ntype, sender, created_at, is_cloud=False):
        clean_text, dur_info, is_expired = parse_content(body)
        if is_expired and role != "admin":
            return None

        header_row = [
            ft.Container(
                content=ft.Text(ntype or "عام", size=12, weight="bold", color=ft.Colors.WHITE),
                bgcolor=get_badge_color(ntype),
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                border_radius=8,
            ),
            ft.Container(
                content=ft.Text(
                    "منتهي ⛔" if is_expired else f"⏳ {dur_info}",
                    size=11,
                    weight="bold",
                    color=ft.Colors.RED_200 if is_expired else ft.Colors.AMBER_200,
                ),
                bgcolor=ft.Colors.RED_900 if is_expired else ft.Colors.BLUE_GREY_900,
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                border_radius=6,
            ),
            ft.Container(expand=True),
            ft.Text(str(created_at or ""), size=11, color=ft.Colors.GREY_500),
        ]

        if role == "admin" and not is_cloud and nid is not None:
            header_row.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=ft.Colors.RED_400,
                    icon_size=18,
                    tooltip="حذف الإشعار",
                    on_click=lambda e, x=nid: delete_notif_action(x),
                )
            )

        return ft.Card(
            content=ft.Container(
                padding=14,
                content=ft.Column(
                    [
                        ft.Row(header_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Divider(height=1, color=ft.Colors.GREY_800),
                        ft.Text(clean_text, size=15, weight="w500"),
                        ft.Text(f"المرسل: {sender}", size=11, color=ft.Colors.GREY_400),
                    ],
                    spacing=8,
                ),
            )
        )

    def load_notifications(is_init=False):
        notif_list.controls.clear()
        rows = db.get_notifications()
        cards = []
        for r in rows:
            # r = (id, title, body, notif_type, sender, created_at)
            card = build_card(r[0], r[1], r[2], r[3], r[4], r[5], is_cloud=False)
            if card is not None:
                cards.append(card)

        if not cards:
            notif_list.controls.append(
                ft.Container(
                    content=ft.Text("لا توجد إشعارات سارية المفعول حالياً.", color=ft.Colors.GREY_500),
                    alignment=ft.Alignment.CENTER,
                    padding=30,
                )
            )
        else:
            notif_list.controls.extend(cards)

        if not is_init:
            try:
                notif_list.update()
            except Exception:
                pass
            page.update()

    def sync_from_cloud(e=None):
        if e is not None:
            notify("جاري تحديث الإشعارات... 🔄", ft.Colors.BLUE_700)
        load_notifications()

        def worker():
            added = db.pull_notifications_from_cloud()
            if added > 0:
                load_notifications()
                play_notif_sound()
                notify(f"وصلك ({added}) إشعار جديد من الإدارة 🔔", ft.Colors.GREEN_700)
            elif e is not None:
                notify("لا توجد إشعارات جديدة في السحابة.", ft.Colors.BLUE_700)

        threading.Thread(target=worker, daemon=True).start()

    def send_notification_action(e):
        ntype = type_dropdown.value or "عام"
        dur_days = duration_dropdown.value or "7"
        raw = (content_input.value or "").strip()
        if not raw:
            notify("يرجى كتابة نص الإشعار أولاً! ⚠️", ft.Colors.RED_700)
            return

        packaged = encode_content(raw, dur_days)
        db.add_notification(title=ntype, body=packaged, notif_type=ntype, sender="الإدارة")
        content_input.value = ""
        load_notifications()
        play_notif_sound()
        notify("تم حفظ ونشر الإشعار بنجاح 🚀", ft.Colors.GREEN_700)

        threading.Thread(target=lambda: db.push_notification_to_cloud(ntype, packaged, "الإدارة"), daemon=True).start()

    send_btn = ft.Button(
        content=ft.Text("نشر وبث الإشعار 🚀", weight="bold"),
        bgcolor=ft.Colors.AMBER_700,
        color=ft.Colors.BLACK,
        on_click=send_notification_action,
        expand=True,
    )

    top_controls = [
        ft.Row(
            [
                ft.Text("إشعارات وتوجيهات الفريق 📢", size=19, weight="bold", color=ft.Colors.AMBER),
                ft.IconButton(icon=ft.Icons.SYNC, icon_color=ft.Colors.AMBER, tooltip="تحديث الإشعارات", on_click=sync_from_cloud),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )
    ]

    if role == "admin":
        top_controls.append(
            ft.Card(
                content=ft.Container(
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Row([type_dropdown, duration_dropdown], spacing=8),
                            content_input,
                            ft.Row([send_btn]),
                        ],
                        spacing=8,
                    ),
                )
            )
        )

    top_controls.append(notif_list)
    load_notifications(is_init=True)
    return ft.Container(content=ft.Column(top_controls, expand=True), padding=10, expand=True)
