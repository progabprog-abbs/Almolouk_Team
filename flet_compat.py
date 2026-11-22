import flet as ft

def apply_flet_compat():
    # أ. استعادة الوحدات والثوابت القديمة بأحرف صغيرة
    if not hasattr(ft, "icons") and hasattr(ft, "Icons"):
        ft.icons = ft.Icons
    if not hasattr(ft, "colors") and hasattr(ft, "Colors"):
        ft.colors = ft.Colors
    if not hasattr(ft, "ElevatedButton") and hasattr(ft, "Button"):
        ft.ElevatedButton = ft.Button
    if not hasattr(ft, "FilledButton") and hasattr(ft, "Button"):
        ft.FilledButton = ft.Button
    if not hasattr(ft, "NavigationDestination") and hasattr(ft, "NavigationBarDestination"):
        ft.NavigationDestination = ft.NavigationBarDestination
    if not hasattr(ft, "UserControl") and hasattr(ft, "Control"):
        ft.UserControl = ft.Control

    # ب. ربط دوال التنسيق والهوامش (padding, border, border_radius, margin, alignment)
    for old_name, new_name in [
        ("padding", "Padding"),
        ("border", "Border"),
        ("border_radius", "BorderRadius"),
        ("margin", "Margin"),
        ("alignment", "Alignment"),
    ]:
        if hasattr(ft, new_name):
            new_cls = getattr(ft, new_name)
            old_mod = getattr(ft, old_name, None)
            if old_mod is None:
                setattr(ft, old_name, new_cls)
            else:
                for attr in dir(new_cls):
                    if not attr.startswith("_") and not hasattr(old_mod, attr):
                        try:
                            setattr(old_mod, attr, getattr(new_cls, attr))
                        except Exception:
                            pass
                # دعم دوال محاذاة السطر الصغير مثل ft.alignment.center
                if old_name == "alignment":
                    for low, up in [
                        ("center", "CENTER"),
                        ("top_center", "TOP_CENTER"),
                        ("bottom_center", "BOTTOM_CENTER"),
                        ("center_left", "CENTER_LEFT"),
                        ("center_right", "CENTER_RIGHT"),
                    ]:
                        if hasattr(new_cls, up) and not hasattr(old_mod, low):
                            try:
                                setattr(old_mod, low, getattr(new_cls, up))
                            except Exception:
                                pass

    # ج. ربط ImageFit إلى BoxFit
    if not hasattr(ft, "ImageFit") and hasattr(ft, "BoxFit"):
        ft.ImageFit = ft.BoxFit

    # د. غلاف ذكي لـ ft.Container لدعم معاملات الخلفية القديمة (image_src, image_src_base64, image_fit)
    _OrigContainer = ft.Container
    class CompatContainer(_OrigContainer):
        def __init__(self, *args, **kwargs):
            img_src = kwargs.pop("image_src", None)
            img_b64 = kwargs.pop("image_src_base64", None)
            img_fit = kwargs.pop("image_fit", None)
            if (img_src or img_b64) and "image" not in kwargs and hasattr(ft, "DecorationImage"):
                dec_kwargs = {}
                if img_src:
                    dec_kwargs["src"] = img_src
                if img_b64:
                    dec_kwargs["src"] = img_b64
                if img_fit:
                    dec_kwargs["fit"] = img_fit
                kwargs["image"] = ft.DecorationImage(**dec_kwargs)
            super().__init__(*args, **kwargs)
    ft.Container = CompatContainer

    # هـ. ربط ft.app إلى ft.run
    if not hasattr(ft, "app") and hasattr(ft, "run"):
        def _compat_app(target=None, *args, **kwargs):
            return ft.run(target, *args, **kwargs)
        ft.app = _compat_app

    if hasattr(ft, "Colors") and not hasattr(ft.Colors, "SURFACE_VARIANT"):
        ft.Colors.SURFACE_VARIANT = getattr(ft.Colors, "SURFACE_CONTAINER_HIGHEST", ft.Colors.BLUE_GREY_900)

    if hasattr(ft, "DecorationImage"):
        _OrigDecorationImage = ft.DecorationImage
        class CompatDecorationImage(_OrigDecorationImage):
            def __init__(self, *args, **kwargs):
                b64 = kwargs.pop("src_base64", None)
                if b64 and "src" not in kwargs:
                    kwargs["src"] = b64
                super().__init__(*args, **kwargs)
        ft.DecorationImage = CompatDecorationImage

    _OrigImage = ft.Image
    class CompatImage(_OrigImage):
        def __init__(self, *args, **kwargs):
            b64 = kwargs.pop("src_base64", None)
            if b64 and "src" not in kwargs:
                kwargs["src"] = b64
            super().__init__(*args, **kwargs)
    ft.Image = CompatImage

    # و. استعادة دوال Session القديمة (set, get, remove, clear, contains_key) في Flet 1.1.2
    try:
        from flet.messaging.session import Session as _FletSession
        if not hasattr(_FletSession, "set"):
            def _sess_set(self, key, value):
                if not hasattr(self, "_custom_store"):
                    self._custom_store = {}
                self._custom_store[key] = value
                if hasattr(self, "store") and isinstance(self.store, dict):
                    self.store[key] = value
            def _sess_get(self, key, default=None):
                if hasattr(self, "_custom_store") and key in self._custom_store:
                    return self._custom_store.get(key, default)
                if hasattr(self, "store") and isinstance(self.store, dict):
                    return self.store.get(key, default)
                return default
            def _sess_remove(self, key):
                if hasattr(self, "_custom_store"):
                    self._custom_store.pop(key, None)
                if hasattr(self, "store") and isinstance(self.store, dict):
                    self.store.pop(key, None)
            def _sess_clear(self):
                if hasattr(self, "_custom_store"):
                    self._custom_store.clear()
                if hasattr(self, "store") and isinstance(self.store, dict):
                    self.store.clear()
            def _sess_contains(self, key):
                return (hasattr(self, "_custom_store") and key in self._custom_store) or (
                    hasattr(self, "store") and isinstance(self.store, dict) and key in self.store
                )
            _FletSession.set = _sess_set
            _FletSession.get = _sess_get
            _FletSession.remove = _sess_remove
            _FletSession.clear = _sess_clear
            _FletSession.contains_key = _sess_contains
    except Exception:
        pass

    # ز. تأمين ft.AudioRecorder و ft.Audio في Flet 1.1.2 كعناصر Container مخفية متوافقة 100% مع page.overlay
    if not hasattr(ft, "AudioRecorder"):
        try:
            from flet_audio_recorder import AudioRecorder as _ExtAudioRecorder
            ft.AudioRecorder = _ExtAudioRecorder
        except Exception:
            class _SafeAudioRecorder(ft.Container):
                def __init__(self, *args, **kwargs):
                    self.audio_encoder = kwargs.pop("audio_encoder", None)
                    self.on_state_changed = kwargs.pop("on_state_changed", None)
                    super().__init__(width=0, height=0, visible=False)
                def start_recording(self, output_path=None):
                    return False
                def stop_recording(self):
                    return None
                def is_recording(self):
                    return False
                def has_permission(self):
                    return False
            ft.AudioRecorder = _SafeAudioRecorder

    if not hasattr(ft, "AudioEncoder"):
        class _SafeAudioEncoder:
            WAV = "wav"
            AACLC = "aacLc"
            AACLD = "aacLd"
            AACHE = "aacHe"
            AMRWB = "amrWb"
            FLAC = "flac"
            OPUS = "opus"
        ft.AudioEncoder = _SafeAudioEncoder

    if not hasattr(ft, "Audio"):
        try:
            from flet_audio import Audio as _ExtAudio
            ft.Audio = _ExtAudio
        except Exception:
            class _SafeAudio(ft.Container):
                def __init__(self, *args, **kwargs):
                    self.src = kwargs.pop("src", "")
                    self.autoplay = kwargs.pop("autoplay", False)
                    self.volume = kwargs.pop("volume", 1.0)
                    self.on_state_changed = kwargs.pop("on_state_changed", None)
                    self.on_position_changed = kwargs.pop("on_position_changed", None)
                    self.on_duration_changed = kwargs.pop("on_duration_changed", None)
                    super().__init__(width=0, height=0, visible=False)
                def play(self): pass
                def pause(self): pass
                def resume(self): pass
                def stop(self): pass
                def seek(self, position_milliseconds): pass
                def release(self): pass
            ft.Audio = _SafeAudio

    # ح. تحويل on_change إلى on_select تلقائياً في ft.Dropdown لـ Flet 1.1.2
    if hasattr(ft, "Dropdown") and not getattr(ft.Dropdown, "_compat_patched", False):
        _OrigDropdown = ft.Dropdown
        class CompatDropdown(_OrigDropdown):
            _compat_patched = True
            def __init__(self, *args, **kwargs):
                if "on_change" in kwargs and "on_select" not in kwargs:
                    kwargs["on_select"] = kwargs.pop("on_change")
                super().__init__(*args, **kwargs)
        ft.Dropdown = CompatDropdown
