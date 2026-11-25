import os
import threading
from datetime import datetime, timedelta
import flet as ft


def NotificationsView(db, role, page):
    notif_list = ft.Column(spacing=10, scroll=ft.ScrollMode.AUTO, expand=True)
    current_user = (page.session.get("user") or db.get_setting("last_logged_user") or "").strip()

    sound_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "notify.wav")
    if not os.path.exists(sound_path):
        sound_path = "notify.wav"

    def play_notif_sound():
        try:
            import flet_audio as fta
            if not os.path.exists(sound_path) or not hasattr(fta, "Audio"):
                return
            if hasattr(page, "services"):
                for s in list(page.services):
                    if isinstance(s, fta.Audio):
                        try:
                            page.services.remove(s)
                        except Exception:
                            pass
                player = fta.Audio(src=sound_path, autoplay=True, volume=1.0)
                page.services.append(player)
                page.update()
        except Exception:
            pass

    def notify(msg, color=ft.Colors.GREEN_700):
        try:
            sb = ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE, weight="bold"), bgcolor=color, duration=3000)
            sb.open = True
            if sb not in page.overlay:
                page.overlay.append(sb)
            page.update()
        except Exception:
            pass

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

    # ==========================================================
    # منظومة توجيه الإشعارات: للكل أو لأعضاء محددين بقائمة اختيار
    # ==========================================================
    member_checks = {}
    members_checklist_col = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO, height=135)
    selected_summary_txt = ft.Text("المستلمون: جميع أعضاء الفريق 📢", size=12, weight="bold", color=ft.Colors.GREEN_300)

    def _update_selected_summary(e=None):
        chosen = [name for name, cb in member_checks.items() if cb.value]
        if target_mode_radio.value == "all":
            selected_summary_txt.value = "المستلمون: جميع أعضاء الفريق 📢"
            selected_summary_txt.color = ft.Colors.GREEN_300
        else:
            if chosen:
                selected_summary_txt.value = f"المختارون ({len(chosen)}): {', '.join(chosen)}"
                selected_summary_txt.color = ft.Colors.AMBER_300
            else:
                selected_summary_txt.value = "⚠️ يرجى تحديد عضو واحد على الأقل من القائمة أدناه"
                selected_summary_txt.color = ft.Colors.RED_300
        try:
            selected_summary_txt.update()
        except Exception:
            pass

    def _refresh_member_checkboxes():
        member_checks.clear()
        members_checklist_col.controls.clear()
        names = []
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT name FROM members ORDER BY name ASC")
            for (n,) in cur.fetchall():
                clean_n = str(n or "").strip()
                if clean_n and clean_n not in names:
                    names.append(clean_n)
            cur.execute("SELECT name FROM admins ORDER BY name ASC")
            for (n,) in cur.fetchall():
                clean_n = str(n or "").strip()
                if clean_n and clean_n != current_user and clean_n not in names:
                    names.append(clean_n)
        except Exception:
            pass

        if not names:
            members_checklist_col.controls.append(
                ft.Text("لا يوجد أعضاء مسجلون حالياً — اضغط تحديث السحابة 🔄", size=12, color=ft.Colors.GREY_400)
            )
        else:
            for nm in names:
                cb = ft.Checkbox(label=nm, value=False, active_color=ft.Colors.AMBER, on_change=_update_selected_summary)
                member_checks[nm] = cb
                members_checklist_col.controls.append(cb)

    def _on_target_mode_change(e):
        is_specific = (target_mode_radio.value == "specific")
        specific_box.visible = is_specific
        if is_specific and not member_checks:
            _refresh_member_checkboxes()
        _update_selected_summary()
        page.update()

    target_mode_radio = ft.RadioGroup(
        value="all",
        on_change=_on_target_mode_change,
        content=ft.Row(
            [
                ft.Radio(value="all", label="إرسال للكل 📢"),
                ft.Radio(value="specific", label="لأعضاء محددين 🎯"),
            ],
            spacing=12,
        ),
    )

    specific_box = ft.Container(
        visible=False,
        bgcolor="#0F172A",
        border=ft.Border.all(1, ft.Colors.AMBER_700),
        border_radius=10,
        padding=8,
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text("اختر الأعضاء المستهدفين بالإشعار:", size=12, weight="bold", color=ft.Colors.AMBER_200),
                        ft.TextButton(
                            content=ft.Text("تحديث القائمة 🔄", size=11),
                            on_click=lambda e: (_refresh_member_checkboxes(), page.update()),
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                members_checklist_col,
            ],
            spacing=4,
        ),
    )

    content_input = ft.TextField(
        label="اكتب نص الإشعار...",
        multiline=True,
        min_lines=2,
        max_lines=4,
    )

    DURATION_LABELS = {"1": "يوم واحد", "3": "3 أيام", "7": "أسبوع", "30": "شهر", "0": "دائم"}

    def encode_content(raw_text, duration_days, targets_list=None):
        label = DURATION_LABELS.get(duration_days, "أسبوع")
        if duration_days == "0":
            exp_str = "PERMANENT"
        else:
            exp_str = (datetime.now() + timedelta(days=int(duration_days))).strftime("%Y-%m-%d %H:%M")
        target_tag = ""
        if targets_list:
            target_tag = f"[TARGET:{','.join(targets_list)}]\n"
        return f"[DUR:{label}|{exp_str}]\n{target_tag}{raw_text}"

    def parse_content(stored_text):
        txt = str(stored_text or "")
        dur_info = "المدة: دائم"
        is_exp = False
        if txt.startswith("[DUR:") and "]\n" in txt:
            header, txt = txt.split("]\n", 1)
            parts = header.replace("[DUR:", "").split("|")
            dur_label = parts[0] if len(parts) > 0 else "دائم"
            exp_str = parts[1] if len(parts) > 1 else "PERMANENT"
            dur_info = f"المدة: {dur_label}"
            if exp_str != "PERMANENT":
                try:
                    if datetime.now() > datetime.strptime(exp_str, "%Y-%m-%d %H:%M"):
                        is_exp = True
                    dur_info = f"المدة: {dur_label} (ينتهي: {exp_str})"
                except Exception:
                    pass

        targets = []
        if txt.startswith("[TARGET:") and "]\n" in txt:
            t_header, txt = txt.split("]\n", 1)
            raw_t = t_header.replace("[TARGET:", "").strip()
            targets = [x.strip() for x in raw_t.split(",") if x.strip()]

        return txt, dur_info, is_exp, targets

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
        clean_text, dur_info, is_expired, targets = parse_content(body)
        if is_expired and role != "admin":
            return None
        # إذا كان الإشعار مخصصاً لأعضاء محددين: لا يراه إلا المدير أو العضو الموجود اسمه في القائمة
        if targets and role != "admin" and current_user not in targets:
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

        audience_badge = (
            ft.Text(f"🎯 موجّه إلى: {', '.join(targets)}", size=11, weight="bold", color=ft.Colors.AMBER_300)
            if targets
            else ft.Text("📢 عام لجميع أعضاء الفريق", size=11, color=ft.Colors.GREEN_300)
        )

        return ft.Card(
            content=ft.Container(
                padding=14,
                content=ft.Column(
                    [
                        ft.Row(header_row, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        audience_badge,
                        ft.Divider(height=1, color=ft.Colors.GREY_800),
                        ft.Text(clean_text, size=15, weight="w500"),
                        ft.Text(f"المرسل: {sender}", size=11, color=ft.Colors.GREY_400),
                    ],
                    spacing=6,
                ),
            )
        )

    def load_notifications(is_init=False):
        notif_list.controls.clear()
        rows = db.get_notifications()
        cards = []
        for r in rows:
            card = build_card(r[0], r[1], r[2], r[3], r[4], r[5], is_cloud=False)
            if card is not None:
                cards.append(card)

        if not cards:
            notif_list.controls.append(
                ft.Container(
                    content=ft.Text("لا توجد إشعارات موجهة لك حالياً.", color=ft.Colors.GREY_500),
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
            if role == "admin":
                db.pull_records_from_cloud()
                _refresh_member_checkboxes()
            added = db.pull_notifications_from_cloud()
            if added > 0:
                load_notifications()
                play_notif_sound()
                notify("تم تحديث الإشعارات من السحابة 🔔", ft.Colors.GREEN_700)
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

        targets_list = None
        if target_mode_radio.value == "specific":
            targets_list = [name for name, cb in member_checks.items() if cb.value]
            if not targets_list:
                notify("يرجى تحديد عضو واحد على الأقل من القائمة! ⚠️", ft.Colors.RED_700)
                return

        packaged = encode_content(raw, dur_days, targets_list=targets_list)
        db.add_notification(title=ntype, body=packaged, notif_type=ntype, sender="الإدارة")
        content_input.value = ""
        load_notifications()
        play_notif_sound()
        notify("تم حفظ وبث الإشعار بنجاح 🚀", ft.Colors.GREEN_700)

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
        _refresh_member_checkboxes()
        top_controls.append(
            ft.Card(
                content=ft.Container(
                    padding=12,
                    content=ft.Column(
                        [
                            ft.Row([type_dropdown, duration_dropdown], spacing=8),
                            target_mode_radio,
                            selected_summary_txt,
                            specific_box,
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
