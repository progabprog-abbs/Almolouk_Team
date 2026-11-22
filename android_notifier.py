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
    """محرك إشعارات نظام أندرويد المنبثقة بالصوت والنص"""

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

    def show_system_notification(self, title: str, body: str, notif_id: int = 1001):
        clean_body = body.split("]\n", 1)[1] if (body.startswith("[DUR:") and "]\n" in body) else body

        # 1. إطلاق إشعار شريط الحالة وشاشة القفل عبر flet_notifications
        if self._notifier:
            for fn_name in ("show_notification", "show", "send"):
                if hasattr(self._notifier, fn_name):
                    fn = getattr(self._notifier, fn_name)
                    try:
                        res = fn(id=notif_id, title=f"⚽ فريق الملوك: {title}", body=clean_body)
                        if inspect.isawaitable(res):
                            self.page.run_task(lambda: res)
                        break
                    except TypeError:
                        try:
                            fn(title=f"⚽ فريق الملوك: {title}", body=clean_body)
                            break
                        except Exception:
                            pass
                    except Exception:
                        pass

        # 2. تشغيل نغمة الرنين المسموعة
        self.play_ringtone()

        # 3. إظهار تنبيه علوي/سفلي داخل التطبيق إن كان مفتوحاً
        try:
            banner = ft.SnackBar(
                bgcolor=ft.Colors.AMBER_900,
                duration=7000,
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.NOTIFICATIONS_ACTIVE, color=ft.Colors.WHITE, size=24),
                        ft.Column(
                            [
                                ft.Text(f"إشعار جديد من الإدارة ({title}) 🔔", weight="bold", color=ft.Colors.WHITE, size=13),
                                ft.Text(clean_body[:75], color=ft.Colors.AMBER_100, size=12),
                            ],
                            spacing=2,
                            expand=True,
                        ),
                    ]
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
                    if self.db.get_setting("sync_enabled") == "1":
                        before_ids = {r[0] for r in self.db.get_notifications()}
                        added = self.db.pull_notifications_from_cloud()
                        if added > 0:
                            new_items = [r for r in self.db.get_notifications() if r[0] not in before_ids]
                            if new_items:
                                latest = new_items[0]
                                self.show_system_notification(
                                    title=latest[3] or latest[1] or "تنبيه إداري",
                                    body=latest[2] or "",
                                    notif_id=int(latest[0]) + 1000,
                                )
                except Exception:
                    pass
                time.sleep(8)

        threading.Thread(target=poll_loop, daemon=True).start()
