import os
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
    audio_dir = os.path.join(db.storage_dir, "local_audio")
    os.makedirs(audio_dir, exist_ok=True)
    db.set_setting("last_logged_user", str(user))

    def notify(msg, color=ft.Colors.GREEN_700):
        page.open(ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE, weight="bold"), bgcolor=color, duration=3200))

    chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True, padding=10)
    msg_input = ft.TextField(
        hint_text="اكتب رسالة مشفرة للفريق...",
        expand=True,
        border_radius=20,
        filled=True,
    )

    state = {"recording": False, "record_path": None, "active_audio": None, "alive": True}

    # ==========================================================
    # 1. فتح روابط المكالمات الحقيقية عبر UrlLauncher المتوافق مع Flet 1.1.2
    # ==========================================================
    url_launcher = None
    if hasattr(ft, "UrlLauncher"):
        try:
            url_launcher = ft.UrlLauncher()
            if hasattr(page, "services") and url_launcher not in page.services:
                page.services.append(url_launcher)
        except Exception:
            url_launcher = None

    def launch_call_room(call_url):
        notify("جاري فتح غرفة الاتصال المباشر بالصوت والصورة... 📞", ft.Colors.GREEN_700)
        launched = False
        if url_launcher is not None and hasattr(url_launcher, "launch_url"):
            try:
                res = url_launcher.launch_url(call_url)
                if inspect.isawaitable(res):
                    async def _do_launch(coro=res):
                        try:
                            await coro
                        except Exception:
                            pass
                    page.run_task(_do_launch)
                launched = True
            except Exception:
                pass
        if not launched and hasattr(page, "launch_url"):
            try:
                res2 = page.launch_url(call_url)
                if inspect.isawaitable(res2):
                    async def _do_launch2(coro=res2):
                        try:
                            await coro
                        except Exception:
                            pass
                    page.run_task(_do_launch2)
                launched = True
            except Exception:
                pass
        if not launched:
            try:
                webbrowser.open(call_url)
                launched = True
            except Exception:
                pass
        if not launched:
            notify("تعذر فتح المتصفح تلقائياً، انسخ الرابط من الدردشة ⚠️", ft.Colors.RED_700)

    # ==========================================================
    # 2. منظومة المكالمات الذكية (جماعية + فردية خاصة بالصوت أو الفيديو)
    # ==========================================================
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

    def _build_jitsi_url(room_slug, is_video=True):
        safe_user = urllib.parse.quote(str(user))
        vid_muted = "false" if is_video else "true"
        return (
            f"https://meet.jit.si/{room_slug}"
            f"#config.prejoinPageEnabled=false"
            f"&config.startWithAudioMuted=false"
            f"&config.startWithVideoMuted={vid_muted}"
            f"&userInfo.displayName={safe_user}"
        )

    def _start_group_call(is_video):
        mode_code = "video" if is_video else "audio"
        room_slug = f"Almolouk2003_Group_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        c_url = _build_jitsi_url(room_slug, is_video=is_video)
        payload = f"[GRP_CALL|{mode_code}|{c_url}]"
        db.add_chat_message(sender=user, msg_type="text", content=payload)
        render_local_messages()
        threading.Thread(
            target=lambda: db.push_chat_to_cloud(sender=user, msg_type="text", content=payload),
            daemon=True,
        ).start()
        launch_call_room(c_url)

    def _start_private_call(target_raw, is_video):
        target_name = target_raw.replace("🛡️ ", "").strip()
        if not target_name:
            notify("يرجى اختيار العضو أو المدير المطلوب الاتصال به أولاً ⚠️", ft.Colors.AMBER_800)
            return
        mode_code = "video" if is_video else "audio"
        room_slug = f"Almolouk2003_Priv_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        c_url = _build_jitsi_url(room_slug, is_video=is_video)
        payload = f"[PRIV_CALL|{target_name}|{mode_code}|{c_url}]"
        db.add_chat_message(sender=user, msg_type="text", content=payload)
        render_local_messages()
        threading.Thread(
            target=lambda: db.push_chat_to_cloud(sender=user, msg_type="text", content=payload),
            daemon=True,
        ).start()
        launch_call_room(c_url)

    def open_call_center_dialog(e):
        threading.Thread(target=db.pull_records_from_cloud, daemon=True).start()
        targets = _get_all_call_targets()
        target_dropdown = ft.Dropdown(
            label="اختر العضو أو المدير للمكالمة الفردية",
            options=[ft.dropdown.Option(t) for t in targets],
            value=targets[0] if targets else None,
            width=270,
        )

        def _close_dlg(ev=None):
            try:
                page.close(call_dlg)
            except Exception:
                call_dlg.open = False
                page.update()

        call_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Row(
                [
                    ft.Icon(ft.Icons.VIDEO_CALL, color=ft.Colors.GREEN_400, size=24),
                    ft.Text("مركز المخابرة والاتصال المباشر", weight="bold", size=15, color=ft.Colors.AMBER),
                ],
                spacing=6,
            ),
            content=ft.Container(
                width=295,
                content=ft.Column(
                    [
                        ft.Text("1️⃣ مكالمة جماعية (دعوة عامة للفريق):", size=13, weight="bold", color=ft.Colors.TEAL_200),
                        ft.Row(
                            [
                                ft.Button(
                                    content=ft.Text("صوت جماعي 🎙️", size=12, weight="bold"),
                                    bgcolor=ft.Colors.TEAL_700,
                                    color=ft.Colors.WHITE,
                                    expand=True,
                                    on_click=lambda ev: (_close_dlg(), _start_group_call(False)),
                                ),
                                ft.Button(
                                    content=ft.Text("فيديو جماعي 📹", size=12, weight="bold"),
                                    bgcolor=ft.Colors.GREEN_700,
                                    color=ft.Colors.WHITE,
                                    expand=True,
                                    on_click=lambda ev: (_close_dlg(), _start_group_call(True)),
                                ),
                            ],
                            spacing=8,
                        ),
                        ft.Divider(height=8),
                        ft.Text("2️⃣ مكالمة فردية خاصة (بين طرفين فقط):", size=13, weight="bold", color=ft.Colors.LIGHT_BLUE_200),
                        target_dropdown,
                        ft.Row(
                            [
                                ft.Button(
                                    content=ft.Text("اتصال صوتي 🎙️", size=12, weight="bold"),
                                    bgcolor=ft.Colors.BLUE_800,
                                    color=ft.Colors.WHITE,
                                    expand=True,
                                    on_click=lambda ev: (_close_dlg(), _start_private_call(target_dropdown.value or "", False)),
                                ),
                                ft.Button(
                                    content=ft.Text("اتصال فيديو 📹", size=12, weight="bold"),
                                    bgcolor=ft.Colors.INDIGO_700,
                                    color=ft.Colors.WHITE,
                                    expand=True,
                                    on_click=lambda ev: (_close_dlg(), _start_private_call(target_dropdown.value or "", True)),
                                ),
                            ],
                            spacing=8,
                        ),
                    ],
                    tight=True,
                    spacing=10,
                ),
            ),
            actions=[
                ft.TextButton(content=ft.Text("إلغاء ✖️", color=ft.Colors.AMBER), on_click=_close_dlg),
            ],
        )
        page.open(call_dlg)

    # ==========================================================
    # 3. جلب الصور وضغطها من الهاتف أو الحاسوب (يدعم bytes و path)
    # ==========================================================
    def _compress_image_bytes(raw_bytes):
        if not raw_bytes:
            return None
        try:
            import io
            from PIL import Image
            im = Image.open(io.BytesIO(raw_bytes))
            if im.mode in ("RGBA", "P", "LA"):
                im = im.convert("RGB")
            im.thumbnail((540, 540))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=62)
            raw_bytes = buf.getvalue()
        except Exception:
            if len(raw_bytes) > 750 * 1024:
                return None
        return base64.b64encode(raw_bytes).decode("ascii")

    def on_image_picked(e):
        files = getattr(e, "files", None) or []
        if not files:
            return
        f_obj = files[0]
        raw_data = getattr(f_obj, "bytes", None)
        f_path = getattr(f_obj, "path", None)

        if not raw_data and f_path and os.path.exists(f_path):
            try:
                raw_data = open(f_path, "rb").read()
            except Exception:
                raw_data = None

        if not raw_data:
            notify("تعذر قراءة بيانات الصورة من الجهاز! حاول اختيار صورة أخرى ⚠️", ft.Colors.RED_700)
            return

        notify("جاري ضغط وإرسال الصورة المشفرة... 📷", ft.Colors.BLUE_700)

        def _send_img_worker(data_bytes=raw_data):
            b64_str = _compress_image_bytes(data_bytes)
            if not b64_str:
                notify("حجم الصورة كبير جداً! يرجى اختيار صورة أصغر ⚠️", ft.Colors.RED_700)
                return
            payload = f"[IMG_B64]{b64_str}"
            db.add_chat_message(sender=user, msg_type="text", content=payload)
            render_local_messages()
            db.push_chat_to_cloud(sender=user, msg_type="text", content=payload)
            notify("تم إرسال الصورة إلى غرفة الفريق بنجاح ✅", ft.Colors.GREEN_700)

        threading.Thread(target=_send_img_worker, daemon=True).start()

    image_picker = None
    try:
        image_picker = ft.FilePicker()
        image_picker.on_result = on_image_picked
        if hasattr(page, "services") and image_picker not in page.services:
            page.services.append(image_picker)
        elif hasattr(page, "overlay") and image_picker not in page.overlay:
            page.overlay.append(image_picker)
    except Exception:
        image_picker = None

    async def open_image_picker(e):
        if image_picker is None:
            notify("منتقي الصور غير متاح على هذا الجهاز ⚠️", ft.Colors.ORANGE_800)
            return
        try:
            res = image_picker.pick_files(
                dialog_title="اختر صورة لإرسالها في الدردشة",
                allow_multiple=False,
                file_type=ft.FilePickerFileType.IMAGE,
                with_data=True,
            )
            if inspect.isawaitable(res):
                await res
        except TypeError:
            try:
                res2 = image_picker.pick_files(
                    dialog_title="اختر صورة لإرسالها في الدردشة",
                    allow_multiple=False,
                    file_type=ft.FilePickerFileType.IMAGE,
                )
                if inspect.isawaitable(res2):
                    await res2
            except Exception as ex2:
                notify(f"تعذر فتح معرض الصور: {ex2}", ft.Colors.RED_700)
        except Exception as ex:
            notify(f"تعذر فتح معرض الصور: {ex}", ft.Colors.RED_700)

    def open_full_image(b64_data):
        dlg = ft.AlertDialog(
            modal=True,
            content=ft.Container(
                content=ft.Image(src_base64=b64_data, fit=ft.BoxFit.CONTAIN, border_radius=12),
                width=305,
                height=360,
            ),
            actions=[
                ft.TextButton(content=ft.Text("إغلاق ✖️", weight="bold"), on_click=lambda e: page.close(dlg)),
            ],
        )
        page.open(dlg)

    # ==========================================================
    # 4. المسجل الصوتي ومشغل الرسائل الصوتية
    # ==========================================================
    audio_recorder = None
    rec_err = ""
    rec_cls = getattr(ftar, "AudioRecorder", None) if ftar else getattr(ft, "AudioRecorder", None)
    if rec_cls is not None:
        try:
            sig = inspect.signature(rec_cls.__init__)
            kwargs = {}
            if "audio_encoder" in sig.parameters and ftar and hasattr(ftar, "AudioEncoder"):
                kwargs["audio_encoder"] = getattr(ftar.AudioEncoder, "WAV", None) or list(ftar.AudioEncoder)[0]
            audio_recorder = rec_cls(**kwargs)
            if hasattr(page, "services") and audio_recorder not in page.services:
                page.services.append(audio_recorder)
            elif hasattr(page, "overlay") and audio_recorder not in page.overlay:
                page.overlay.append(audio_recorder)
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
                notify("مشغل الصوت غير متاح على هذا الجهاز", ft.Colors.ORANGE_800)
                return

            if hasattr(page, "services"):
                if state["active_audio"] and state["active_audio"] in page.services:
                    try:
                        self_rem = page.services.remove(state["active_audio"])
                    except Exception:
                        pass
                player = audio_cls(src=file_path, autoplay=True)
                state["active_audio"] = player
                page.services.append(player)
                page.update()
                notify("جاري تشغيل الرسالة الصوتية 🔊", ft.Colors.TEAL_700)
        except Exception as ex:
            notify(f"تعذر تشغيل الصوت: {ex}", ft.Colors.RED_700)

    def build_message_bubble(msg):
        sender = (msg.get("sender") or "عضو").strip()
        msg_type = msg.get("msg_type") or msg.get("type") or "text"
        content = msg.get("content") or msg.get("message") or ""
        audio_path = msg.get("audio_path") or msg.get("audio_data") or ""
        timestamp = msg.get("timestamp") or ""

        is_me = (sender == user)
        bubble_color = ft.Colors.BLUE_GREY_800 if is_me else ft.Colors.GREY_900
        align = ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START

        # 1) مكالمة فردية خاصة [PRIV_CALL|target|mode|url] -> تظهر للطرفين فقط!
        if content.startswith("[PRIV_CALL|"):
            parts = content.split("|", 3)
            if len(parts) == 4:
                _, target_name, c_mode, c_url = parts
                target_name = target_name.strip()
                c_url = c_url.rstrip("]")
                if user not in (sender, target_name):
                    return None
                bubble_color = ft.Colors.INDIGO_900
                mode_label = "مكالمة فيديو خاصة 📹" if c_mode == "video" else "مكالمة صوتية خاصة 🎙️"
                sub_label = f"مع: {target_name}" if is_me else f"مكالمة خاصة لك من: {sender}"
                body_control = ft.Column(
                    [
                        ft.Text(mode_label, size=13, weight="bold", color=ft.Colors.WHITE),
                        ft.Text(sub_label, size=11, color=ft.Colors.LIGHT_BLUE_200),
                        ft.Button(
                            content=ft.Text("دخول المكالمة الخاصة 🟢", size=12, weight="bold"),
                            on_click=lambda e, u=c_url: launch_call_room(u),
                            bgcolor=ft.Colors.GREEN_600,
                            color=ft.Colors.WHITE,
                        ),
                    ],
                    spacing=5,
                    tight=True,
                )
        # 2) مكالمة جماعية [GRP_CALL|mode|url]
        elif content.startswith("[GRP_CALL|"):
            parts = content.split("|", 2)
            c_mode = parts[1] if len(parts) >= 2 else "video"
            c_url = (parts[2] if len(parts) == 3 else "").rstrip("]")
            bubble_color = ft.Colors.GREEN_900
            mode_label = "مكالمة فيديو جماعية 📹" if c_mode == "video" else "مكالمة صوتية جماعية 🎙️"
            body_control = ft.Column(
                [
                    ft.Text(mode_label, size=13, weight="bold", color=ft.Colors.WHITE),
                    ft.Button(
                        content=ft.Text("انضمام للمكالمة الجماعية 🟢", size=12, weight="bold"),
                        on_click=lambda e, u=c_url: launch_call_room(u),
                        bgcolor=ft.Colors.GREEN_600,
                        color=ft.Colors.WHITE,
                    ),
                ],
                spacing=5,
                tight=True,
            )
        elif content.startswith("[CALL_URL]"):
            c_url = content.replace("[CALL_URL]", "", 1).strip()
            bubble_color = ft.Colors.GREEN_900
            body_control = ft.Column(
                [
                    ft.Text("مخابرة مباشرة (صوت وصورة) 📞", size=13, weight="bold", color=ft.Colors.WHITE),
                    ft.Button(
                        content=ft.Text("انضمام للمكالمة الآن 🟢", size=12, weight="bold"),
                        on_click=lambda e, u=c_url: launch_call_room(u),
                        bgcolor=ft.Colors.GREEN_600,
                        color=ft.Colors.WHITE,
                    ),
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
                        ft.Image(
                            src_base64=b64_img,
                            width=205,
                            height=180,
                            fit=ft.BoxFit.COVER,
                            border_radius=10,
                        ),
                        ft.Text("اضغط لتكبير الصورة 🔍", size=10, color=ft.Colors.AMBER_200),
                    ],
                    spacing=3,
                    tight=True,
                ),
            )
        elif msg_type == "audio":
            body_control = ft.Row(
                [
                    ft.IconButton(
                        icon=ft.Icons.PLAY_CIRCLE_FILL,
                        icon_color=ft.Colors.AMBER,
                        icon_size=34,
                        tooltip="تشغيل التسجيل الصوتي",
                        on_click=lambda e, p=audio_path: play_voice_note(p),
                    ),
                    ft.Text("رسالة صوتية مشفرة 🎙️", size=13, weight="w500"),
                ],
                tight=True,
            )
        else:
            body_control = ft.Text(content, size=15, selectable=True)

        bubble = ft.Container(
            bgcolor=bubble_color,
            padding=ft.Padding.symmetric(horizontal=12, vertical=9),
            border_radius=15,
            width=245,
            content=ft.Column(
                [
                    ft.Text(
                        "أنت" if is_me else sender,
                        size=11,
                        weight="bold",
                        color=ft.Colors.AMBER if is_me else ft.Colors.LIGHT_BLUE_300,
                    ),
                    body_control,
                    ft.Text(timestamp, size=10, color=ft.Colors.GREY_400),
                ],
                spacing=4,
                tight=True,
            ),
        )
        return ft.Row([bubble], alignment=align)

    def render_local_messages(is_init=False):
        chat_list.controls.clear()
        messages = db.get_chat_messages()
        visible_bubbles = []
        for m in messages:
            b = build_message_bubble(m)
            if b is not None:
                visible_bubbles.append(b)

        if not visible_bubbles:
            chat_list.controls.append(
                ft.Container(
                    content=ft.Text("غرفة الدردشة والمخابرة جاهزة. ابدأ المحادثة أو الاتصال! 🔒", color=ft.Colors.GREY_500),
                    alignment=ft.Alignment.CENTER,
                    padding=30,
                )
            )
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
                        notify("يرجى منح إذن الميكروفون للتطبيق من إعدادات الهاتف 🎙️", ft.Colors.RED_700)
                        return

                res = audio_recorder.start_recording(out_path)
                if inspect.isawaitable(res):
                    res = await res

                if res is False:
                    notify("لم يبدأ التسجيل الصوتي، تأكد من إذن الميكروفون ⚠️", ft.Colors.RED_700)
                    return

                state["recording"] = True
                mic_btn.icon = ft.Icons.STOP_CIRCLE
                mic_btn.icon_color = ft.Colors.RED_500
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
            except Exception as ex:
                notify(f"خطأ أثناء إيقاف التسجيل: {ex}", ft.Colors.ORANGE_800)

            state["recording"] = False
            mic_btn.icon = ft.Icons.MIC
            mic_btn.icon_color = ft.Colors.AMBER
            page.update()

            final_path = ret_path if (isinstance(ret_path, str) and os.path.exists(ret_path)) else state["record_path"]
            if final_path and os.path.exists(final_path):
                db.add_chat_message(sender=user, msg_type="audio", content="", audio_path=final_path)
                render_local_messages()
                notify("تم إرسال الرسالة الصوتية ✔️", ft.Colors.GREEN_700)
                threading.Thread(
                    target=lambda: db.push_chat_to_cloud(sender=user, msg_type="audio", content="", audio_path=final_path),
                    daemon=True,
                ).start()
            else:
                notify("لم يتم العثور على الملف الصوتي المسجل ⚠️", ft.Colors.ORANGE_800)

    def sync_chat_messages(e=None):
        if e is not None:
            notify("جاري مزامنة الرسائل من السحابة... 🔄", ft.Colors.BLUE_700)

        def worker():
            added = db.pull_chat_from_cloud()
            if added > 0 or e is not None:
                render_local_messages()
                if added > 0:
                    notify(f"وصلت ({added}) رسالة جديدة 💬", ft.Colors.GREEN_700)

        threading.Thread(target=worker, daemon=True).start()

    def auto_poll_chat():
        while state["alive"]:
            time.sleep(3)
            try:
                if page.route != "/dashboard":
                    break
                if db.pull_chat_from_cloud() > 0:
                    render_local_messages()
            except Exception:
                pass

    threading.Thread(target=auto_poll_chat, daemon=True).start()

    img_btn = ft.IconButton(icon=ft.Icons.IMAGE, icon_color=ft.Colors.LIGHT_BLUE_300, tooltip="إرسال صورة", on_click=open_image_picker)
    mic_btn = ft.IconButton(icon=ft.Icons.MIC, icon_color=ft.Colors.AMBER, tooltip="تسجيل صوتي", on_click=toggle_recording)
    send_btn = ft.IconButton(icon=ft.Icons.SEND, icon_color=ft.Colors.GREEN_400, tooltip="إرسال", on_click=send_text_msg)

    call_btn = ft.Button(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.VIDEO_CALL, color=ft.Colors.WHITE, size=18),
                ft.Text("مخابرة 📞", size=12, weight="bold", color=ft.Colors.WHITE),
            ],
            spacing=4,
            tight=True,
        ),
        bgcolor=ft.Colors.GREEN_700,
        height=34,
        on_click=open_call_center_dialog,
    )

    header = ft.Row(
        [
            ft.Text("الدردشة والمخابرة 🔒", size=16, weight="bold", color=ft.Colors.AMBER),
            ft.Row(
                [
                    call_btn,
                    ft.IconButton(icon=ft.Icons.SYNC, icon_color=ft.Colors.AMBER, tooltip="مزامنة الرسائل", on_click=sync_chat_messages),
                ],
                spacing=2,
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    render_local_messages(is_init=True)
    sync_chat_messages()

    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        expand=True,
        content=ft.Column(
            [
                header,
                ft.Divider(height=1),
                chat_list,
                ft.Row([img_btn, mic_btn, msg_input, send_btn], spacing=2),
            ],
            expand=True,
        ),
    )