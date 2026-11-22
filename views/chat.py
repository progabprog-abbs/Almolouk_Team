import os
import time
import inspect
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

    def notify(msg, color=ft.Colors.GREEN_700):
        page.open(ft.SnackBar(content=ft.Text(msg, color=ft.Colors.WHITE), bgcolor=color, duration=3000))

    chat_list = ft.ListView(expand=True, spacing=10, auto_scroll=True, padding=10)
    msg_input = ft.TextField(
        hint_text="اكتب رسالة مشفرة للفريق...",
        expand=True,
        border_radius=20,
        filled=True,
    )

    state = {"recording": False, "record_path": None, "active_audio": None, "alive": True}

    # تهيئة مسجل الصوت متوافقاً مع توقيع Flet 1.1.2 وتسجيله في page.services
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
            if hasattr(page, "services"):
                if audio_recorder not in page.services:
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

    def build_message_bubble(msg):
        sender = msg.get("sender") or "عضو"
        msg_type = msg.get("msg_type") or msg.get("type") or "text"
        content = msg.get("content") or msg.get("message") or ""
        audio_path = msg.get("audio_path") or msg.get("audio_data") or ""
        timestamp = msg.get("timestamp") or ""

        is_me = (sender == user)
        bubble_color = ft.Colors.BLUE_GREY_800 if is_me else ft.Colors.GREY_900
        align = ft.MainAxisAlignment.END if is_me else ft.MainAxisAlignment.START

        if msg_type == "audio":
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
            padding=ft.Padding.symmetric(horizontal=14, vertical=10),
            border_radius=15,
            width=235,
            content=ft.Column(
                [
                    ft.Text(
                        "أنت" if is_me else sender,
                        size=11,
                        weight="bold",
                        color=ft.Colors.AMBER if is_me else ft.Colors.LIGHT_BLUE_300,
                    ),
                    body_control,
                    ft.Text(timestamp, size=10, color=ft.Colors.GREY_500),
                ],
                spacing=4,
                tight=True,
            ),
        )
        return ft.Row([bubble], alignment=align)

    def render_local_messages(is_init=False):
        chat_list.controls.clear()
        messages = db.get_chat_messages()
        if not messages:
            chat_list.controls.append(
                ft.Container(
                    content=ft.Text("غرفة الدردشة المشفرة جاهزة. ابدأ المحادثة! 🔒", color=ft.Colors.GREY_500),
                    alignment=ft.Alignment.CENTER,
                    padding=30,
                )
            )
        else:
            for m in messages:
                chat_list.controls.append(build_message_bubble(m))

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
                # دعم الدوال المتزامنة وغير المتزامنة (async/sync) في Flet 1.1.2
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
            time.sleep(5)
            try:
                if page.route != "/dashboard":
                    break
                if db.pull_chat_from_cloud() > 0:
                    render_local_messages()
            except Exception:
                pass

    threading.Thread(target=auto_poll_chat, daemon=True).start()

    mic_btn = ft.IconButton(icon=ft.Icons.MIC, icon_color=ft.Colors.AMBER, tooltip="تسجيل صوتي", on_click=toggle_recording)
    send_btn = ft.IconButton(icon=ft.Icons.SEND, icon_color=ft.Colors.GREEN_400, tooltip="إرسال", on_click=send_text_msg)

    header = ft.Row(
        [
            ft.Text("غرفة الدردشة المشفرة 🔒", size=18, weight="bold", color=ft.Colors.AMBER),
            ft.IconButton(icon=ft.Icons.SYNC, icon_color=ft.Colors.AMBER, tooltip="مزامنة الرسائل", on_click=sync_chat_messages),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )

    render_local_messages(is_init=True)
    sync_chat_messages()

    return ft.Container(
        padding=ft.Padding.symmetric(horizontal=12, vertical=6),
        expand=True,
        content=ft.Column(
            [
                header,
                ft.Divider(height=1),
                chat_list,
                ft.Row([mic_btn, msg_input, send_btn], spacing=5),
            ],
            expand=True,
        ),
    )
