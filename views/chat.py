import os
import io
import sys
import time
import base64
import inspect
import urllib.parse
import webbrowser
import threading
from datetime import datetime
import flet as ft

try:
    import flet_audio as fta
except Exception:
    fta = None

try:
    import flet_audio_recorder as ftar
except Exception:
    ftar = None


def ChatView(db, user, page):
    role = (page.session.get("role") or "member").strip()
    is_admin = (role == "admin")
    audio_dir = os.path.join(db.storage_dir, "local_audio")
    files_dir = os.path.join(db.storage_dir, "local_files")
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(files_dir, exist_ok=True)
    db.set_setting("last_logged_user", str(user))

    def close_dialog_safe(dlg):
        try:
            dlg.open = False
            page.update()
        except Exception:
            pass

    def open_dialog_safe(dlg):
        try:
            dlg.open = True
            if dlg not in page.overlay:
                page.overlay.append(dlg)
            page.update()
        except Exception:
            pass

    def notify(msg, color=ft.Colors.GREEN_700):
        try:
            sb = ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE, weight="bold"), bgcolor=color, duration=3200)
            open_dialog_safe(sb)
        except Exception:
            pass

    chat_list = ft.ListView(expand=True, spacing=8, auto_scroll=True, padding=10)
    msg_input = ft.TextField(
        hint_text="مراسلة مشفرة للفريق...",
        expand=True,
        filled=True,
        bgcolor="#1F2C34",
        border=ft.OutlineInputBorder(border_radius=24, side=ft.BorderSide(1, "#2A3942")),
        content_padding=ft.Padding.symmetric(horizontal=16, vertical=10),
    )

    state = {"recording": False, "record_path": None, "active_audio": None, "alive": True, "ringing_call_id": None}

    # ==========================================================
    # 1. فتح الاتصال الصوتي والمرئي عبر خادم WebRTC مفتوح في متصفح النظام
    #    (يتجاوز حظر vdo.ninja وحظر كاميرا WebView في أندرويد 100%)
    # ==========================================================
    url_launcher = None
    if hasattr(ft, "UrlLauncher"):
        try:
            url_launcher = ft.UrlLauncher()
            if hasattr(page, "services") and url_launcher not in page.services:
                page.services.append(url_launcher)
        except Exception:
            url_launcher = None

    def open_direct_call_browser(call_url):
        notify("جاري فتح غرفة الاتصال المباشر بالصوت والصورة... 📞", ft.Colors.GREEN_700)
        if url_launcher is not None and hasattr(url_launcher, "launch_url"):
            try:
                res = url_launcher.launch_url(call_url)
                if inspect.isawaitable(res):
                    async def _r(c=res):
                        try:
                            await c
                        except Exception:
                            pass
                    page.run_task(_r)
                return
            except Exception:
                pass
        if hasattr(page, "launch_url"):
            try:
                res2 = page.launch_url(call_url)
                if inspect.isawaitable(res2):
                    async def _r2(c=res2):
                        try:
                            await c
                        except Exception:
                            pass
                    page.run_task(_r2)
                return
            except Exception:
                pass
        try:
            webbrowser.open(call_url)
        except Exception as ex:
            notify(f"تعذر فتح المتصفح: {ex}", ft.Colors.RED_700)

    def _build_open_call_url(room_slug, is_video=True):
        safe_name = urllib.parse.quote(str(user))
        vid_muted = "false" if is_video else "true"
        # خادم FFMUC الألماني المفتوح لـ WebRTC: مجاني بالكامل، لا يطلب تثبيت تطبيق خارجي، وغير محجوب
        return (
            f"https://meet.ffmuc.net/{room_slug}"
            f"#config.prejoinConfig.enabled=false"
            f"&config.disableDeepLinking=true"
            f"&config.startWithAudioMuted=false"
            f"&config.startWithVideoMuted={vid_muted}"
            f"&userInfo.displayName={safe_name}"
        )

    def _get_all_call_targets():
        targets = []
        try:
            cur = db.conn.cursor()
            cur.execute("SELECT name FROM admins")
            for (n,) in cur.fetchall():
                n_clean = str(n or "").strip()
                if n_clean and n_clean != user and n_clean not in targets:
                    targets.append(f"🛡️ {n_clean}")
            cur.execute("SELECT name FROM members")
            for (n,) in cur.fetchall():
                n_clean = str(n or "").strip()
                if n_clean and n_clean != user and f"🛡️ {n_clean}" not in targets and n_clean not in targets:
                    targets.append(n_clean)
        except Exception:
            pass
        return targets

    def _start_group_call(is_video):
        mode_code = "video" if is_video else "audio"
        room_slug = f"AlmoloukFootball2003Grp{datetime.now().strftime('%Y%m%d%H%M')}"
        c_url = _build_open_call_url(room_slug, is_video=is_video)
        payload = f"[GRP_CALL|{mode_code}|{c_url}]"
        db.add_chat_message(sender=user, msg_type="text", content=payload)
        render_local_messages()
        threading.Thread(target=lambda: db.push_chat_to_cloud(sender=user, msg_type="text", content=payload), daemon=True).start()
        open_direct_call_browser(c_url)

    def _start_private_call(target_raw, is_video):
        target_name = target_raw.replace("🛡️ ", "").strip()
        if not target_name:
            notify("يرجى اختيار العضو أو المدير أولاً ⚠️", ft.Colors.AMBER_800)
            return
        mode_code = "video" if is_video else "audio"
        room_slug = f"AlmoloukFootball2003Prv{datetime.now().strftime('%Y%m%d%H%M%S')}"
        c_url = _build_open_call_url(room_slug, is_video=is_video)
        payload = f"[PRIV_CALL|{target_name}|{mode_code}|{c_url}]"
        db.add_chat_message(sender=user, msg_type="text", content=payload)
        render_local_messages()
        threading.Thread(target=lambda: db.push_chat_to_cloud(sender=user, msg_type="text", content=payload), daemon=True).start()
        open_direct_call_browser(c_url)

    def open_call_center_dialog(e):
        threading.Thread(target=db.pull_records_from_cloud, daemon=True).start()
        targets = _get_all_call_targets()
        target_dropdown = ft.Dropdown(
            label="اختر العضو أو المدير للمكالمة الفردية",
            options=[ft.dropdown.Option(t) for t in targets],
            value=targets[0] if targets else None,
            width=275,
        )

        call_dlg = ft.AlertDialog(
            modal=True,
            bgcolor="#1F2C34",
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.CALL, color=ft.Colors.GREEN_400, size=22),
                    ft.Text("مخابرة صوتية ومرئية مباشرة", weight="bold", size=15, color=ft.Colors.WHITE),
                ],
                spacing=6,
            ),
            content=ft.Container(
                width=295,
                content=ft.Column(
                    [
                        ft.Text("🌐 مكالمة جماعية (لكل أعضاء الفريق):", size=13, weight="bold", color=ft.Colors.GREEN_300),
                        ft.Row(
                            [
                                ft.Button(content=ft.Text("صوت جماعي 🎙️", size=12, weight="bold"), bgcolor="#00A884", color=ft.Colors.WHITE, expand=True, on_click=lambda ev: (close_dialog_safe(call_dlg), _start_group_call(False))),
                                ft.Button(content=ft.Text("فيديو جماعي 📹", size=12, weight="bold"), bgcolor=ft.Colors.GREEN_700, color=ft.Colors.WHITE, expand=True, on_click=lambda ev: (close_dialog_safe(call_dlg), _start_group_call(True))),
                            ],
                            spacing=8,
                        ),
                        ft.Divider(height=8, color="#2A3942"),
                        ft.Text("👤 مكالمة فردية خاصة (بين طرفين فقط):", size=13, weight="bold", color=ft.Colors.LIGHT_BLUE_200),
                        target_dropdown,
                        ft.Row(
                            [
                                ft.Button(content=ft.Text("اتصال صوتي 🎙️", size=12, weight="bold"), bgcolor=ft.Colors.BLUE_800, color=ft.Colors.WHITE, expand=True, on_click=lambda ev: (close_dialog_safe(call_dlg), _start_private_call(target_dropdown.value or "", False))),
                                ft.Button(content=ft.Text("اتصال فيديو 📹", size=12, weight="bold"), bgcolor=ft.Colors.INDIGO_700, color=ft.Colors.WHITE, expand=True, on_click=lambda ev: (close_dialog_safe(call_dlg), _start_private_call(target_dropdown.value or "", True))),
                            ],
                            spacing=8,
                        ),
                    ],
                    tight=True,
                    spacing=10,
                ),
            ),
            actions=[ft.TextButton(content=ft.Text("إغلاق ✖️", color=ft.Colors.AMBER), on_click=lambda ev: close_dialog_safe(call_dlg))],
        )
        open_dialog_safe(call_dlg)

    def show_incoming_call_popup(caller_name, is_video, c_url, is_group=False):
        title_txt = f"مكالمة {'فيديو' if is_video else 'صوتية'} {'جماعية' if is_group else 'واردة'}"
        inc_dlg = ft.AlertDialog(
            modal=True,
            bgcolor="#111B21",
            content=ft.Container(
                width=280,
                padding=12,
                content=ft.Column(
                    [
                        ft.Icon(ft.Icons.RING_VOLUME, color=ft.Colors.GREEN_400, size=48),
                        ft.Text(caller_name, size=18, weight="bold", color=ft.Colors.WHITE),
                        ft.Text(title_txt, size=13, color=ft.Colors.GREEN_300),
                        ft.Row(
                            [
                                ft.Button(content=ft.Text("رفض 🔴", weight="bold"), bgcolor=ft.Colors.RED_700, color=ft.Colors.WHITE, expand=True, on_click=lambda e: close_dialog_safe(inc_dlg)),
                                ft.Button(content=ft.Text("رد 🟢", weight="bold"), bgcolor="#00A884", color=ft.Colors.WHITE, expand=True, on_click=lambda e: (close_dialog_safe(inc_dlg), open_direct_call_browser(c_url))),
                            ],
                            spacing=12,
                        ),
                    ],
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=12,
                ),
            ),
        )
        open_dialog_safe(inc_dlg)

    # ==========================================================
    # 2. إدارة وتنظيف الوسائط (حذف المدير + الحذف التلقائي بالمدة)
    # ==========================================================
    def open_cleanup_settings_dialog(e):
        if not is_admin:
            return
        cur_hours = db.get_setting("chat_media_ttl_hours") or "168"
        ttl_dd = ft.Dropdown(
            label="مدة الاحتفاظ بالصور والصوتيات",
            value=cur_hours,
            options=[
                ft.dropdown.Option("24", "24 ساعة (يوم واحد)"),
                ft.dropdown.Option("72", "3 أيام"),
                ft.dropdown.Option("168", "7 أيام (أسبوع)"),
                ft.dropdown.Option("720", "30 يوماً (شهر)"),
                ft.dropdown.Option("0", "دائم (حذف يدوي فقط)"),
            ],
            width=265,
        )

        def save_and_clean(ev):
            val = ttl_dd.value or "168"
            db.set_setting("chat_media_ttl_hours", val)
            close_dialog_safe(clean_dlg)
            hrs = int(val)
            if hrs > 0:
                removed = db.cleanup_expired_chat_media(hrs)
                render_local_messages()
                notify(f"تم حفظ الإعداد وتنظيف ({removed}) ملف منتهي الصلاحية 🧹", ft.Colors.GREEN_700)
            else:
                notify("تم تفعيل الاحتفاظ الدائم بالوسائط ✔️", ft.Colors.BLUE_700)

        clean_dlg = ft.AlertDialog(
            modal=True,
            bgcolor="#1F2C34",
            title=ft.Text("🧹 إدارة وتنظيف وسائط الدردشة", size=15, weight="bold", color=ft.Colors.AMBER),
            content=ft.Container(
                width=285,
                content=ft.Column(
                    [
                        ft.Text("حدد المدة الزمنية لحذف الصور والملفات الصوتية القديمة تلقائياً لإبقاء التطبيق خفيفاً:", size=12, color=ft.Colors.GREY_300),
                        ttl_dd,
                    ],
                    tight=True,
                    spacing=10,
                ),
            ),
            actions=[
                ft.TextButton(content=ft.Text("إلغاء"), on_click=lambda ev: close_dialog_safe(clean_dlg)),
                ft.Button(content=ft.Text("حفظ وتنظيف الآن 🧹", weight="bold"), bgcolor="#00A884", color=ft.Colors.WHITE, on_click=save_and_clean),
            ],
        )
        open_dialog_safe(clean_dlg)

    def delete_single_message(msg_id, cloud_id):
        if not is_admin:
            return
        db.delete_chat_message(msg_id, cloud_id)
        render_local_messages()
        notify("تم حذف العنصر من الدردشة والسحابة 🗑️", ft.Colors.RED_800)

    # ==========================================================
    # 3. مشاركة الصور والملفات
    # ==========================================================
    def _compress_image_bytes(raw_bytes):
        if not raw_bytes:
            return None
        try:
            from PIL import Image
            im = Image.open(io.BytesIO(raw_bytes))
            if im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")
            im.thumbnail((540, 540))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=62)
            raw_bytes = buf.getvalue()
        except Exception:
            if len(raw_bytes) > 850 * 1024:
                return None
        return base64.b64encode(raw_bytes).decode("ascii")

    def _process_picked_items(files_list, is_doc=False):
        if not files_list:
            return
        f_obj = files_list[0]
        f_name = getattr(f_obj, "name", "attachment")
        raw_data = getattr(f_obj, "bytes", None)
        f_path = getattr(f_obj, "path", None)

        if not raw_data and f_path and os.path.exists(f_path):
            try:
                with open(f_path, "rb") as fp:
                    raw_data = fp.read()
            except Exception:
                raw_data = None

        if not raw_data:
            notify("تعذر قراءة الملف المختار من الجهاز ⚠️", ft.Colors.RED_700)
            return

        ext = os.path.splitext(f_name)[1].lower()
        is_image_ext = ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp") and not is_doc

        if is_image_ext:
            notify("جاري إرسال الصورة المشفرة... 📷", ft.Colors.TEAL_700)

            def _send_img(data_b=raw_data):
                b64_str = _compress_image_bytes(data_b)
                if not b64_str:
                    notify("حجم الصورة كبير جداً! اختر صورة أصغر ⚠️", ft.Colors.RED_700)
                    return
                payload = f"[IMG_B64]{b64_str}"
                db.add_chat_message(sender=user, msg_type="text", content=payload)
                render_local_messages()
                db.push_chat_to_cloud(sender=user, msg_type="text", content=payload)
                notify("تم إرسال الصورة بنجاح ✅", ft.Colors.GREEN_700)

            threading.Thread(target=_send_img, daemon=True).start()
        else:
            if len(raw_data) > 900 * 1024:
                notify("الحد الأقصى لحجم الملف المرفق هو 900 كيلوبايت ⚠️", ft.Colors.RED_700)
                return
            notify(f"جاري إرسال الملف ({f_name})... 📎", ft.Colors.BLUE_700)

            def _send_doc(data_b=raw_data, fn=f_name):
                b64_doc = base64.b64encode(data_b).decode("ascii")
                payload = f"[FILE_B64|{fn}|{b64_doc}]"
                db.add_chat_message(sender=user, msg_type="text", content=payload)
                render_local_messages()
                db.push_chat_to_cloud(sender=user, msg_type="text", content=payload)
                notify("تم إرسال الملف إلى غرفة الفريق بنجاح ✅", ft.Colors.GREEN_700)

            threading.Thread(target=_send_doc, daemon=True).start()

    media_picker = None
    picker_mode = {"is_doc": False}
    try:
        media_picker = ft.FilePicker()
        media_picker.on_result = lambda e: _process_picked_items(getattr(e, "files", None) or [], is_doc=picker_mode["is_doc"])
        if hasattr(page, "services") and media_picker not in page.services:
            page.services.append(media_picker)
    except Exception:
        media_picker = None

    async def pick_image_action(e):
        if media_picker is None:
            notify("منتقي الصور غير متاح ⚠️", ft.Colors.ORANGE_800)
            return
        picker_mode["is_doc"] = False
        try:
            picked = await media_picker.pick_files(dialog_title="اختر صورة", allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE, with_data=True)
            if picked:
                _process_picked_items(picked, is_doc=False)
        except Exception:
            try:
                picked2 = await media_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.IMAGE)
                if picked2:
                    _process_picked_items(picked2, is_doc=False)
            except Exception as ex:
                notify(f"تعذر فتح الصور: {ex}", ft.Colors.RED_700)

    async def pick_file_action(e):
        if media_picker is None:
            notify("منتقي الملفات غير متاح ⚠️", ft.Colors.ORANGE_800)
            return
        picker_mode["is_doc"] = True
        try:
            picked = await media_picker.pick_files(dialog_title="اختر ملفاً لإرساله", allow_multiple=False, file_type=ft.FilePickerFileType.ANY, with_data=True)
            if picked:
                _process_picked_items(picked, is_doc=True)
        except Exception:
            try:
                picked2 = await media_picker.pick_files(allow_multiple=False, file_type=ft.FilePickerFileType.ANY)
                if picked2:
                    _process_picked_items(picked2, is_doc=True)
            except Exception as ex:
                notify(f"تعذر فتح الملفات: {ex}", ft.Colors.RED_700)

    def open_full_image(b64_data):
        img_dlg = ft.AlertDialog(
            modal=True,
            bgcolor="#111B21",
            content=ft.Container(
                content=ft.Image(src=b64_data, fit=ft.BoxFit.CONTAIN, border_radius=12),
                width=310,
                height=370,
            ),
            actions=[
                ft.Button(
                    content=ft.Text("إغلاق ✖️", weight="bold"),
                    bgcolor=ft.Colors.RED_800,
                    color=ft.Colors.WHITE,
                    on_click=lambda e: close_dialog_safe(img_dlg),
                ),
            ],
        )
        open_dialog_safe(img_dlg)

    def save_and_open_attachment(file_name, b64_data):
        try:
            raw = base64.b64decode(b64_data)
            safe_name = os.path.basename(file_name) or "file.bin"
            out_path = os.path.join(files_dir, safe_name)
            with open(out_path, "wb") as fp:
                fp.write(raw)
            notify(f"تم حفظ الملف في: {out_path} ✅", ft.Colors.GREEN_700)
            if sys.platform == "win32":
                os.startfile(out_path)
            else:
                open_direct_call_browser(f"file://{out_path}")
        except Exception as ex:
            notify(f"تم حفظ الملف محلياً (تعذر الفتح التلقائي: {ex})", ft.Colors.AMBER_800)

    # ==========================================================
    # 4. المسجل الصوتي ومشغل الرسائل الصوتية
    # ==========================================================
    audio_recorder = None
    rec_err = ""
    rec_cls = getattr(ftar, "AudioRecorder", None) if ftar else None
    if rec_cls is not None:
        try:
            sig = inspect.signature(rec_cls.__init__)
            kwargs = {}
            if "audio_encoder" in sig.parameters and hasattr(ftar, "AudioEncoder"):
                kwargs["audio_encoder"] = getattr(ftar.AudioEncoder, "WAV", None) or list(ftar.AudioEncoder)[0]
            audio_recorder = rec_cls(**kwargs)
            if hasattr(page, "services") and audio_recorder not in page.services:
                page.services.append(audio_recorder)
        except Exception as ex:
            rec_err = str(ex)
            audio_recorder = None

    def play_voice_note(file_path):
        if not file_path or not os.path.exists(file_path):
            notify("الملف الصوتي غير متوفر على هذا الجهاز ⚠️", ft.Colors.RED_700)
            return
        try:
            audio_cls = getattr(fta, "Audio", None) if fta else getattr(ft, "Audio", None)
            if not audio_cls:
                notify("مشغل الصوت غير متاح", ft.Colors.ORANGE_800)
                return

            if hasattr(page, "services"):
                if state["active_audio"] and state["active_audio"] in page.services:
                    try:
                        page.services.remove(state["active_audio"])
                    except Exception:
                        pass
                player = audio_cls(src=file_path, autoplay=True)
                state["active_audio"] = player
                page.services.append(player)
                page.update()
                notify("جاري تشغيل الرسالة الصوتية 🔊", ft.Colors.TEAL_700)
        except Exception as ex:
            notify(f"تعذر تشغيل الصوت: {ex}", ft.Colors.RED_700)

    # ==========================================================
    # 5. بناء فقاعات المحادثة مع زر الحذف للمدير
    # ==========================================================
    def build_message_bubble(msg):
        msg_id = msg.get("id") or 0
        cloud_id = msg.get("cloud_id") or ""
        sender = (msg.get("sender") or "عضو").strip()
        msg_type = msg.get("msg_type") or msg.get("type") or "text"
        content = msg.get("content") or msg.get("message") or ""
        audio_path = msg.get("audio_path") or msg.get("audio_data") or ""
        timestamp = msg.get("timestamp") or ""

        is_me = (sender == user)
        bubble_color = "#005C4B" if is_me else "#202C33"
        align = ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START

        if content.startswith("[PRIV_CALL|"):
            parts = content.split("|", 3)
            if len(parts) == 4:
                _, target_name, c_mode, c_url = parts
                target_name = target_name.strip()
                c_url = c_url.rstrip("]")
                if user not in (sender, target_name) and not is_admin:
                    return None
                is_vid = (c_mode == "video")
                mode_label = "مكالمة فيديو خاصة 📹" if is_vid else "مكالمة صوتية خاصة 🎙️"
                sub_label = f"مع: {target_name}" if is_me else f"مكالمة خاصة من {sender} إلى {target_name}"
                body_control = ft.Column(
                    [
                        ft.Text(mode_label, size=13, weight="bold", color=ft.Colors.WHITE),
                        ft.Text(sub_label, size=11, color="#D1D7DB"),
                        ft.Button(content=ft.Text("انضمام للمكالمة 🟢", size=12, weight="bold"), on_click=lambda e, u=c_url: open_direct_call_browser(u), bgcolor="#00A884", color=ft.Colors.WHITE),
                    ],
                    spacing=5,
                    tight=True,
                )
        elif content.startswith("[GRP_CALL|"):
            parts = content.split("|", 2)
            c_mode = parts[1] if len(parts) >= 2 else "video"
            c_url = (parts[2] if len(parts) == 3 else "").rstrip("]")
            is_vid = (c_mode == "video")
            mode_label = "مكالمة فيديو جماعية 📹" if is_vid else "مكالمة صوتية جماعية 🎙️"
            body_control = ft.Column(
                [
                    ft.Text(mode_label, size=13, weight="bold", color=ft.Colors.WHITE),
                    ft.Button(content=ft.Text("دخول المكالمة الجماعية 🟢", size=12, weight="bold"), on_click=lambda e, u=c_url: open_direct_call_browser(u), bgcolor="#00A884", color=ft.Colors.WHITE),
                ],
                spacing=5,
                tight=True,
            )
        elif content.startswith("[CALL_URL]"):
            c_url = content.replace("[CALL_URL]", "", 1).strip()
            body_control = ft.Column(
                [
                    ft.Text("مخابرة مباشرة 📞", size=13, weight="bold", color=ft.Colors.WHITE),
                    ft.Button(content=ft.Text("انضمام الآن 🟢", size=12, weight="bold"), on_click=lambda e, u=c_url: open_direct_call_browser(u), bgcolor="#00A884", color=ft.Colors.WHITE),
                ],
                spacing=5,
                tight=True,
            )
        elif content.startswith("[IMG_B64]"):
            b64_img = content.replace("[IMG_B64]", "", 1).strip()
            body_control = ft.GestureDetector(
                on_tap=lambda e, img_d=b64_img: open_full_image(img_d),
                content=ft.Column(
                    [
                        ft.Image(src=b64_img, width=210, height=185, fit=ft.BoxFit.COVER, border_radius=10),
                        ft.Text("اضغط لعرض الصورة كاملة 🔍", size=10, color="#E9EDEF"),
                    ],
                    spacing=3,
                    tight=True,
                ),
            )
        elif content.startswith("[FILE_B64|"):
            parts = content.split("|", 2)
            fn = parts[1] if len(parts) >= 2 else "مستند مرفق"
            b64_f = (parts[2] if len(parts) == 3 else "").rstrip("]")
            body_control = ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.INSERT_DRIVE_FILE, color=ft.Colors.AMBER_300, size=26),
                            ft.Text(fn[:24], size=12, weight="bold", color=ft.Colors.WHITE, expand=True),
                        ],
                        spacing=6,
                    ),
                    ft.Button(content=ft.Text("تحميل وفتح الملف 📥", size=11, weight="bold"), bgcolor="#025144" if is_me else "#2A3942", color=ft.Colors.WHITE, on_click=lambda e, n=fn, d=b64_f: save_and_open_attachment(n, d)),
                ],
                spacing=5,
                tight=True,
            )
        elif msg_type == "audio":
            body_control = ft.Row(
                [
                    ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_color="#00A884" if not is_me else ft.Colors.AMBER, icon_size=34, tooltip="تشغيل الرسالة الصوتية", on_click=lambda e, p=audio_path: play_voice_note(p)),
                    ft.Text("رسالة صوتية 🎙️", size=13, weight="w500", color=ft.Colors.WHITE),
                ],
                tight=True,
            )
        else:
            body_control = ft.Text(content, size=14.5, selectable=True, color="#E9EDEF")

        top_meta = [
            ft.Text("أنت" if is_me else sender, size=11, weight="bold", color="#53BDEB" if not is_me else ft.Colors.AMBER_200),
        ]
        if is_admin:
            top_meta.append(
                ft.IconButton(
                    icon=ft.Icons.DELETE_OUTLINE,
                    icon_color=ft.Colors.RED_300,
                    icon_size=16,
                    tooltip="حذف نهائي (صلاحية المدير)",
                    on_click=lambda e, mid=msg_id, cid=cloud_id: delete_single_message(mid, cid),
                )
            )

        bubble = ft.Container(
            bgcolor=bubble_color,
            padding=ft.Padding.symmetric(horizontal=12, vertical=8),
            border_radius=14,
            width=250,
            content=ft.Column(
                [
                    ft.Row(top_meta, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    body_control,
                    ft.Row([ft.Text(timestamp, size=9.5, color="#8696A0"), ft.Icon(ft.Icons.DONE_ALL, size=13, color="#53BDEB") if is_me else ft.Container()], alignment=ft.MainAxisAlignment.END, spacing=3),
                ],
                spacing=3,
                tight=True,
            ),
        )
        return ft.Row([bubble], alignment=align)

    def render_local_messages(is_init=False):
        chat_list.controls.clear()
        messages = db.get_chat_messages()
        visible_bubbles = [b for m in messages if (b := build_message_bubble(m)) is not None]
        if not visible_bubbles:
            chat_list.controls.append(ft.Container(content=ft.Text("🔒 الرسائل والمكالمات مشفرة بالكامل بين أعضاء فريق الملوك", size=12, color="#8696A0", text_align=ft.TextAlign.CENTER), alignment=ft.Alignment.CENTER, padding=25))
        else:
            chat_list.controls.extend(visible_bubbles)
        if not is_init:
            try:
                chat_list.update()
            except Exception:
                pass
            page.update()

    def send_text_msg(e=None):
        text = (msg_input.value or "").strip()
        if not text:
            return
        msg_input.value = ""
        db.add_chat_message(sender=user, msg_type="text", content=text)
        render_local_messages()
        threading.Thread(target=lambda: db.push_chat_to_cloud(sender=user, msg_type="text", content=text), daemon=True).start()

    msg_input.on_submit = send_text_msg

    async def toggle_recording(e):
        if audio_recorder is None:
            detail = f" ({rec_err})" if rec_err else ""
            notify(f"تعذر تهيئة مسجل الصوت{detail} ⚠️", ft.Colors.ORANGE_800)
            return

        if not state["recording"]:
            fname = f"voice_{datetime.now().strftime('%Y%m%d_%H%M%S')}.m4a"
            out_path = os.path.join(audio_dir, fname)
            state["record_path"] = out_path
            try:
                if hasattr(audio_recorder, "has_permission"):
                    perm = audio_recorder.has_permission()
                    if inspect.isawaitable(perm):
                        perm = await perm
                    if perm is False:
                        notify("يرجى منح إذن الميكروفون من إعدادات الهاتف 🎙️", ft.Colors.RED_700)
                        return
                res = audio_recorder.start_recording(out_path)
                if inspect.isawaitable(res):
                    res = await res
                if res is False:
                    notify("لم يبدأ التسجيل الصوتي ⚠️", ft.Colors.RED_700)
                    return
                state["recording"] = True
                mic_btn.content.icon = ft.Icons.STOP_CIRCLE
                mic_btn.bgcolor = ft.Colors.RED_700
                notify("جاري التسجيل الصوتي... اضغط مجدداً للإرسال 🎙️", ft.Colors.RED_800)
                page.update()
            except Exception as ex:
                notify(f"خطأ أثناء بدء التسجيل: {ex}", ft.Colors.RED_700)
        else:
            ret_path = None
            try:
                ret_path = audio_recorder.stop_recording()
                if inspect.isawaitable(ret_path):
                    ret_path = await ret_path
            except Exception:
                pass
            state["recording"] = False
            mic_btn.content.icon = ft.Icons.MIC
            mic_btn.bgcolor = "#00A884"
            page.update()

            final_path = ret_path if (isinstance(ret_path, str) and os.path.exists(ret_path)) else state["record_path"]
            if final_path and os.path.exists(final_path):
                db.add_chat_message(sender=user, msg_type="audio", content="", audio_path=final_path)
                render_local_messages()
                notify("تم إرسال الرسالة الصوتية ✔️", ft.Colors.GREEN_700)
                threading.Thread(target=lambda: db.push_chat_to_cloud(sender=user, msg_type="audio", content="", audio_path=final_path), daemon=True).start()
            else:
                notify("لم يتم العثور على الملف الصوتي المسجل ⚠️", ft.Colors.ORANGE_800)

    def sync_chat_messages(e=None):
        if e is not None:
            notify("جاري تحديث المحادثة... 🔄", ft.Colors.TEAL_700)

        def worker():
            ttl_val = int(db.get_setting("chat_media_ttl_hours") or "168")
            if ttl_val > 0:
                db.cleanup_expired_chat_media(ttl_val)
            added = db.pull_chat_from_cloud()
            if added > 0 or e is not None:
                render_local_messages()
                if added > 0:
                    msgs = db.get_chat_messages()
                    if msgs:
                        last = msgs[-1]
                        c_id = f"{last.get('id', '')}:{last.get('timestamp', '')}"
                        sender = (last.get("sender") or "").strip()
                        raw = last.get("content") or ""
                        if sender != user and c_id != state["ringing_call_id"]:
                            if raw.startswith("[PRIV_CALL|"):
                                parts = raw.split("|", 3)
                                if len(parts) == 4 and parts[1].strip() == user:
                                    state["ringing_call_id"] = c_id
                                    show_incoming_call_popup(sender, parts[2] == "video", parts[3].rstrip("]"), is_group=False)
                            elif raw.startswith("[GRP_CALL|"):
                                parts = raw.split("|", 2)
                                if len(parts) == 3:
                                    state["ringing_call_id"] = c_id
                                    show_incoming_call_popup(sender, parts[1] == "video", parts[2].rstrip("]"), is_group=True)

        threading.Thread(target=worker, daemon=True).start()

    def auto_poll_chat():
        while state["alive"]:
            time.sleep(2.5)
            try:
                if page.route != "/dashboard":
                    break
                if db.pull_chat_from_cloud() > 0:
                    render_local_messages()
                    msgs = db.get_chat_messages()
                    if msgs:
                        last = msgs[-1]
                        c_id = f"{last.get('id', '')}:{last.get('timestamp', '')}"
                        sender = (last.get("sender") or "").strip()
                        raw = last.get("content") or ""
                        if sender != user and c_id != state["ringing_call_id"]:
                            if raw.startswith("[PRIV_CALL|"):
                                parts = raw.split("|", 3)
                                if len(parts) == 4 and parts[1].strip() == user:
                                    state["ringing_call_id"] = c_id
                                    show_incoming_call_popup(sender, parts[2] == "video", parts[3].rstrip("]"), is_group=False)
                            elif raw.startswith("[GRP_CALL|"):
                                parts = raw.split("|", 2)
                                if len(parts) == 3:
                                    state["ringing_call_id"] = c_id
                                    show_incoming_call_popup(sender, parts[1] == "video", parts[2].rstrip("]"), is_group=True)
            except Exception:
                pass

    threading.Thread(target=auto_poll_chat, daemon=True).start()

    attach_btn = ft.IconButton(icon=ft.Icons.ATTACH_FILE, icon_color="#8696A0", tooltip="إرسال ملف (PDF / مستند)", on_click=pick_file_action)
    cam_btn = ft.IconButton(icon=ft.Icons.CAMERA_ALT, icon_color="#8696A0", tooltip="إرسال صورة", on_click=pick_image_action)
    mic_btn = ft.Container(bgcolor="#00A884", border_radius=22, content=ft.IconButton(icon=ft.Icons.MIC, icon_color=ft.Colors.WHITE, icon_size=20, tooltip="تسجيل صوتي", on_click=toggle_recording))
    send_btn = ft.Container(bgcolor="#00A884", border_radius=22, content=ft.IconButton(icon=ft.Icons.SEND, icon_color=ft.Colors.WHITE, icon_size=20, tooltip="إرسال", on_click=send_text_msg))

    header_actions = [
        ft.IconButton(icon=ft.Icons.VIDEOCAM, icon_color=ft.Colors.WHITE, icon_size=21, tooltip="مكالمة فيديو (جماعية/فردية)", on_click=open_call_center_dialog),
        ft.IconButton(icon=ft.Icons.CALL, icon_color=ft.Colors.WHITE, icon_size=20, tooltip="مكالمة صوتية (جماعية/فردية)", on_click=open_call_center_dialog),
    ]
    if is_admin:
        header_actions.append(
            ft.IconButton(icon=ft.Icons.AUTO_DELETE, icon_color=ft.Colors.AMBER_300, icon_size=20, tooltip="تنظيف الوسائط المنتهية 🧹", on_click=open_cleanup_settings_dialog)
        )
    header_actions.append(
        ft.IconButton(icon=ft.Icons.SYNC, icon_color="#8696A0", icon_size=20, tooltip="مزامنة", on_click=sync_chat_messages)
    )

    wa_header = ft.Container(
        bgcolor="#1F2C34",
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=12,
        content=ft.Row(
            [
                ft.Row(
                    [
                        ft.CircleAvatar(bgcolor="#00A884", radius=17, content=ft.Icon(ft.Icons.GROUPS, color=ft.Colors.WHITE, size=20)),
                        ft.Column(
                            [
                                ft.Text("فريق الملوك 2003", size=13.5, weight="bold", color=ft.Colors.WHITE),
                                ft.Text("مشفّر • اتصال مباشر", size=10, color="#00A884"),
                            ],
                            spacing=1,
                        ),
                    ],
                    spacing=8,
                ),
                ft.Row(header_actions, spacing=0),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
    )

    render_local_messages(is_init=True)
    sync_chat_messages()

    return ft.Container(
        bgcolor="#0B141A",
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        expand=True,
        content=ft.Column(
            [
                wa_header,
                chat_list,
                ft.Row([attach_btn, cam_btn, msg_input, mic_btn, send_btn], spacing=3),
            ],
            expand=True,
            spacing=4,
        ),
    )