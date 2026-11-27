import os
import time
import inspect
import threading
import flet as ft

try:
    import flet_audio as fta
except Exception:
    fta = None

try:
    import flet_notifications as fn_mod
except Exception:
    fn_mod = None


class AndroidSystemNotifier:
    """محرك إشعارات نظام أندرويد العصرية بالصوت والنص وإيقاظ الشاشة"""

    def __init__(self, page: ft.Page, db):
        self.page = page
        self.db = db
        self.running = True
        self.sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify.wav")
        if not os.path.exists(self.sound_path):
            self.sound_path = "notify.wav"
        self._notifier = self._init_plugin()

    def _init_plugin(self):
        if not fn_mod:
            return None
        for cls_name in ("LocalNotifications", "Notifications", "FletNotifications"):
            cls = getattr(fn_mod, cls_name, None)
            if cls:
                try:
                    inst = cls()
                    if hasattr(self.page, "services") and inst not in self.page.services:
                        self.page.services.append(inst)
                    return inst
                except Exception:
                    pass
        return None

    async def _async_request_perm(self):
        if not self._notifier:
            return
        for m in ("request_permission", "request_permissions"):
            if hasattr(self._notifier, m):
                try:
                    res = getattr(self._notifier, m)()
                    if inspect.isawaitable(res):
                        await res
                except Exception:
                    pass

    def play_ringtone(self):
        try:
            if fta and os.path.exists(self.sound_path) and hasattr(fta, "Audio") and hasattr(self.page, "services"):
                for s in list(self.page.services):
                    if isinstance(s, fta.Audio):
                        try:
                            self.page.services.remove(s)
                        except Exception:
                            pass
                player = fta.Audio(src=self.sound_path, autoplay=True, volume=1.0)
                self.page.services.append(player)
                self.page.update()
        except Exception:
            pass

    def show_system_notification(self, title: str, body: str, notif_id: int = 1001, accent_color=ft.Colors.AMBER_900):
        clean_body = body.split("]\n", 1)[1] if (body.startswith("[DUR:") and "]\n" in body) else body

        # 1. إطلاق إشعار النظام العلوي وشاشة القفل بأولوية قصوى وصوت
        if self._notifier:
            for fn_name in ("show_notification", "show", "send"):
                if hasattr(self._notifier, fn_name):
                    fn = getattr(self._notifier, fn_name)
                    try:
                        sig = inspect.signature(fn)
                        kw = {"id": notif_id, "title": f"⚽ فريق الملوك: {title}", "body": clean_body}
                        if "channel_id" in sig.parameters:
                            kw["channel_id"] = "almolouk_urgent_channel"
                        if "channel_name" in sig.parameters:
                            kw["channel_name"] = "تنبيهات فريق الملوك العاجلة"
                        if "importance" in sig.parameters:
                            kw["importance"] = "max"
                        if "priority" in sig.parameters:
                            kw["priority"] = "high"
                        res = fn(**kw)
                        if inspect.isawaitable(res):
                            async def _runner(coro=res):
                                try:
                                    await coro
                                except Exception:
                                    pass
                            self.page.run_task(_runner)
                        break
                    except Exception:
                        try:
                            res2 = fn(title=f"⚽ فريق الملوك: {title}", body=clean_body)
                            if inspect.isawaitable(res2):
                                async def _runner2(coro=res2):
                                    try:
                                        await coro
                                    except Exception:
                                        pass
                                self.page.run_task(_runner2)
                            break
                        except Exception:
                            pass

        # 2. تشغيل نغمة الرنين المسموعة
        self.play_ringtone()

        # 3. إظهار بطاقة تنبيه عصرية عائمة داخل التطبيق
        try:
            banner = ft.SnackBar(
                bgcolor=accent_color,
                duration=8000,
                behavior=ft.SnackBarBehavior.FLOATING,
                shape=ft.RoundedRectangleBorder(radius=14),
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, color=ft.Colors.WHITE, size=24),
                            bgcolor=ft.Colors.with_opacity(0.25, ft.Colors.BLACK),
                            padding=8,
                            border_radius=10,
                        ),
                        ft.Column(
                            [
                                ft.Text(f"🔔 {title}", weight="bold", color=ft.Colors.WHITE, size=13),
                                ft.Text(clean_body[:90], color=ft.Colors.WHITE, size=12),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    spacing=10,
                ),
            )
            self.page.open(banner)
            self.page.update()
        except Exception:
            pass

    def start_background_listener(self):
        try:
            self.page.run_task(self._async_request_perm)
        except Exception:
            pass

        def poll_loop():
            time.sleep(1.5)
            while self.running:
                try:
                    cur_user = (self.page.session.get("user") or self.db.get_setting("last_logged_user") or "").strip()

                    # أ) فحص الإشعارات الإدارية وحفظ آخر معرّف على القرص لمنع التكرار أو الضياع عند الإغلاق
                    before_ids = {r[0] for r in self.db.get_notifications()}
                    added_notifs = self.db.pull_notifications_from_cloud()
                    if added_notifs > 0:
                        new_items = [r for r in self.db.get_notifications() if r[0] not in before_ids]
                        if new_items:
                            latest = new_items[0]
                            nid = str(latest[0])
                            if self.db.get_setting("last_seen_notif_id") != nid:
                                self.db.set_setting("last_seen_notif_id", nid)
                                raw_b = latest[2] or ""
                                clean_b = raw_b.split("]\n", 1)[1] if (raw_b.startswith("[DUR:") and "]\n" in raw_b) else raw_b
                                allowed = True
                                if clean_b.startswith("[TARGET:") and "]\n" in clean_b:
                                    t_hdr, clean_b = clean_b.split("]\n", 1)
                                    t_names = [x.strip() for x in t_hdr.replace("[TARGET:", "").split(",") if x.strip()]
                                    cur_role = (self.page.session.get("role") or "").strip()
                                    if t_names and cur_role != "admin" and cur_user not in t_names:
                                        allowed = False
                                if allowed:
                                    self.show_system_notification(
                                        title=latest[3] or latest[1] or "إشعار إداري جديد",
                                        body=clean_b,
                                        notif_id=int(latest[0]) + 1000,
                                        accent_color=ft.Colors.AMBER_900,
                                    )

                    # ب) فحص رسائل الدردشة والمكالمات الفردية والجماعية والصور
                    added_chat = self.db.pull_chat_from_cloud()
                    if added_chat > 0:
                        msgs = self.db.get_chat_messages()
                        if msgs:
                            last = msgs[-1]
                            sig = f"{last.get('id', '')}:{last.get('timestamp', '')}:{last.get('sender', '')}"
                            sender = (last.get("sender") or "عضو").strip()
                            saved_sig = self.db.get_setting("last_seen_chat_sig") or ""
                            if sig != saved_sig:
                                self.db.set_setting("last_seen_chat_sig", sig)
                                if sender != cur_user:
                                    raw_content = last.get("content") or ""
                                    msg_type = last.get("msg_type") or "text"

                                    # معالجة المكالمات الفردية [PRIV_CALL|target|mode|url]
                                    if raw_content.startswith("[PRIV_CALL|"):
                                        parts = raw_content.split("|", 3)
                                        if len(parts) == 4:
                                            _, target_name, c_mode, _ = parts
                                            if cur_user == target_name.strip():
                                                mode_ar = "فيديو وصوت 📹" if c_mode == "video" else "صوتية 🎙️"
                                                self.show_system_notification(
                                                    title=f"📞 مكالمة خاصة واردة من {sender}",
                                                    body=f"يتصل بك الآن ({mode_ar}) — افتح الدردشة للرد!",
                                                    notif_id=9910,
                                                    accent_color=ft.Colors.GREEN_800,
                                                )
                                    # معالجة المكالمات الجماعية [GRP_CALL|mode|url]
                                    elif raw_content.startswith("[GRP_CALL|") or raw_content.startswith("[CALL_URL]"):
                                        self.show_system_notification(
                                            title=f"🌐 مكالمة جماعية من {sender}",
                                            body="دعوة للانضمام إلى مكالمة الفريق المباشرة الآن!",
                                            notif_id=9911,
                                            accent_color=ft.Colors.TEAL_800,
                                        )
                                    elif raw_content.startswith("[IMG_B64]") or msg_type == "image":
                                        self.show_system_notification(
                                            title=f"📷 صورة جديدة من {sender}",
                                            body="أرسل صورة جديدة في غرفة الدردشة",
                                            notif_id=9912,
                                            accent_color=ft.Colors.BLUE_800,
                                        )
                                    elif msg_type == "audio":
                                        self.show_system_notification(
                                            title=f"🎙️ رسالة صوتية من {sender}",
                                            body="أرسل تسجيلاً صوتياً جديداً في الدردشة",
                                            notif_id=9913,
                                            accent_color=ft.Colors.CYAN_800,
                                        )
                                    else:
                                        self.show_system_notification(
                                            title=f"💬 رسالة جديدة من {sender}",
                                            body=raw_content,
                                            notif_id=9914,
                                            accent_color=ft.Colors.INDIGO_800,
                                        )
                except Exception:
                    pass
                time.sleep(1.2)

        threading.Thread(target=poll_loop, daemon=True).start()