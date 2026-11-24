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
    """محرك إشعارات نظام أندرويد العصرية بالصوت والنص للشاشة المفتوحة والمقفلة"""

    def __init__(self, page: ft.Page, db):
        self.page = page
        self.db = db
        self.running = True
        self.sound_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify.wav")
        if not os.path.exists(self.sound_path):
            self.sound_path = "notify.wav"
        self._notifier = self._init_plugin()
        self._last_chat_sig = self._get_latest_chat_sig()

    def _get_latest_chat_sig(self):
        try:
            msgs = self.db.get_chat_messages()
            if msgs:
                last = msgs[-1]
                return f"{last.get('id', '')}:{last.get('timestamp', '')}:{last.get('sender', '')}"
        except Exception:
            pass
        return ""

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

        # 1. إطلاق إشعار شريط الحالة وشاشة القفل عبر flet_notifications
        if self._notifier:
            for fn_name in ("show_notification", "show", "send"):
                if hasattr(self._notifier, fn_name):
                    fn = getattr(self._notifier, fn_name)
                    try:
                        res = fn(id=notif_id, title=f"⚽ فريق الملوك: {title}", body=clean_body)
                        if inspect.isawaitable(res):
                            async def _runner(coro=res):
                                try:
                                    await coro
                                except Exception:
                                    pass
                            self.page.run_task(_runner)
                        break
                    except TypeError:
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
                    except Exception:
                        pass

        # 2. تشغيل نغمة الرنين المسموعة
        self.play_ringtone()

        # 3. إظهار بطاقة تنبيه عصرية داخل التطبيق إن كان مفتوحاً
        try:
            banner = ft.SnackBar(
                bgcolor=accent_color,
                duration=7500,
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
                                ft.Text(clean_body[:85], color=ft.Colors.WHITE, size=12),
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
            time.sleep(2)
            while self.running:
                try:
                    # أ) مراقبة الإشعارات الإدارية السحابية
                    before_ids = {r[0] for r in self.db.get_notifications()}
                    added_notifs = self.db.pull_notifications_from_cloud()
                    if added_notifs > 0:
                        new_items = [r for r in self.db.get_notifications() if r[0] not in before_ids]
                        if new_items:
                            latest = new_items[0]
                            self.show_system_notification(
                                title=latest[3] or latest[1] or "إشعار إداري جديد",
                                body=latest[2] or "",
                                notif_id=int(latest[0]) + 1000,
                                accent_color=ft.Colors.AMBER_900,
                            )

                    # ب) مراقبة رسائل الدردشة والمكالمات المباشرة والصور
                    added_chat = self.db.pull_chat_from_cloud()
                    if added_chat > 0:
                        msgs = self.db.get_chat_messages()
                        if msgs:
                            last = msgs[-1]
                            sig = f"{last.get('id', '')}:{last.get('timestamp', '')}:{last.get('sender', '')}"
                            cur_user = self.page.session.get("user") or ""
                            sender = last.get("sender") or "عضو"
                            if sig != self._last_chat_sig and sender != cur_user:
                                self._last_chat_sig = sig
                                raw_content = last.get("content") or ""
                                msg_type = last.get("msg_type") or "text"
                                if raw_content.startswith("[CALL_URL]"):
                                    self.show_system_notification(
                                        title=f"📞 مخابرة مباشرة من {sender}",
                                        body="يدعوك للانضمام إلى مكالمة الفريق الصوتية/المرئية الآن!",
                                        notif_id=9901,
                                        accent_color=ft.Colors.GREEN_800,
                                    )
                                elif raw_content.startswith("[IMG_B64]") or msg_type == "image":
                                    self.show_system_notification(
                                        title=f"📷 صورة جديدة من {sender}",
                                        body="أرسل صورة جديدة في غرفة الدردشة",
                                        notif_id=9902,
                                        accent_color=ft.Colors.BLUE_800,
                                    )
                                elif msg_type == "audio":
                                    self.show_system_notification(
                                        title=f"🎙️ رسالة صوتية من {sender}",
                                        body="أرسل تسجيلاً صوتياً جديداً في الدردشة",
                                        notif_id=9903,
                                        accent_color=ft.Colors.TEAL_800,
                                    )
                                else:
                                    self.show_system_notification(
                                        title=f"💬 رسالة جديدة من {sender}",
                                        body=raw_content,
                                        notif_id=9904,
                                        accent_color=ft.Colors.INDIGO_800,
                                    )
                except Exception:
                    pass
                time.sleep(6)

        threading.Thread(target=poll_loop, daemon=True).start()