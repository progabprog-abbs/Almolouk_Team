import os
import sys
import sqlite3
import hashlib
import base64
import itertools
import json
import urllib.request
from datetime import datetime, timedelta

_SECRET_KEY = hashlib.sha256(b"Almolouk_Team_2026_Moola_SecureKey").digest()
DEFAULT_FIREBASE_URL = "https://kingsteam-671a6-default-rtdb.asia-southeast1.firebasedatabase.app/"


def get_persistent_storage_dir():
    if sys.platform == "win32":
        base = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.path.dirname(os.path.abspath(__file__))
    else:
        base = os.getenv("FLET_APP_STORAGE_DATA") or os.path.expanduser("~")
    os.makedirs(base, exist_ok=True)
    return base


class DatabaseManager:
    def __init__(self, db_name="almolouk_pro.db"):
        self.storage_dir = get_persistent_storage_dir()
        self.db_path = db_name if os.path.isabs(db_name) else os.path.join(self.storage_dir, db_name)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.init_db()

    @property
    def cursor(self):
        return self.conn.cursor()

    def get_connection(self):
        return sqlite3.connect(self.db_path, check_same_thread=False)

    def encrypt_text(self, plain_text: str) -> str:
        if not plain_text:
            return ""
        raw = str(plain_text).encode("utf-8")
        xored = bytes(b ^ k for b, k in zip(raw, itertools.cycle(_SECRET_KEY)))
        return base64.urlsafe_b64encode(xored).decode("utf-8")

    def decrypt_text(self, cipher_text: str) -> str:
        if not cipher_text:
            return ""
        try:
            xored = base64.urlsafe_b64decode(str(cipher_text).encode("utf-8"))
            raw = bytes(b ^ k for b, k in zip(xored, itertools.cycle(_SECRET_KEY)))
            return raw.decode("utf-8")
        except Exception:
            return str(cipher_text)

    def init_db(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                address TEXT DEFAULT '',
                facebook TEXT DEFAULT '',
                position TEXT DEFAULT '',
                jersey_number TEXT DEFAULT '',
                age TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                created_at TEXT DEFAULT ''
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                address TEXT DEFAULT '',
                facebook TEXT DEFAULT '',
                role TEXT DEFAULT 'admin',
                created_at TEXT DEFAULT ''
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cloud_id TEXT DEFAULT '',
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                notif_type TEXT DEFAULT 'عام',
                sender TEXT DEFAULT 'الإدارة',
                created_at TEXT DEFAULT ''
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cloud_id TEXT DEFAULT '',
                sender TEXT NOT NULL,
                message TEXT DEFAULT '',
                audio_data TEXT DEFAULT '',
                msg_type TEXT DEFAULT 'text',
                created_at TEXT DEFAULT ''
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                setting_key TEXT PRIMARY KEY,
                setting_value TEXT
            )
        """)

        for tbl, cols_needed in [
            ("members", ["address", "facebook", "position", "jersey_number", "age", "notes", "created_at"]),
            ("admins", ["address", "facebook", "role", "created_at"]),
            ("notifications", ["cloud_id", "notif_type", "sender", "created_at"]),
            ("chat_messages", ["cloud_id", "audio_data", "msg_type", "created_at"]),
        ]:
            existing = [c[1] for c in cur.execute(f"PRAGMA table_info({tbl})").fetchall()]
            for col in cols_needed:
                if col not in existing:
                    try:
                        cur.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} TEXT DEFAULT ''")
                    except Exception:
                        pass

        cur.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
        if cur.fetchone()[0] == 0:
            cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", ("admin", "1234", "admin"))

        cur.execute("INSERT OR IGNORE INTO app_settings (setting_key, setting_value) VALUES ('sync_enabled', '1')")
        cur.execute("INSERT OR IGNORE INTO app_settings (setting_key, setting_value) VALUES ('api_url', ?)", (DEFAULT_FIREBASE_URL,))
        self.conn.commit()
        try:
            self.ensure_developer_and_clean_dummies()
        except Exception:
            pass

    def set_setting(self, key: str, value: str):
        cur = self.conn.cursor()
        cur.execute("INSERT OR REPLACE INTO app_settings (setting_key, setting_value) VALUES (?, ?)", (key, str(value)))
        self.conn.commit()

    def get_setting(self, key: str, default: str = ""):
        cur = self.conn.cursor()
        cur.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default

    def _firebase_url(self):
        return (self.get_setting("api_url") or DEFAULT_FIREBASE_URL).strip().rstrip("/")

    # --- السجلات والبيانات (الأعضاء والمخولين) + مزامنة سحابية ثنائية الاتجاه ---
    # --- نظام المطور الرئيسي وصلاحيات المخولين الثانويين ---
    DEV_NAME = "Abbas Almoola"
    DEV_PHONE = "07707841925"

    def is_developer(self, name: str = "", phone: str = "") -> bool:
        n_clean = str(name or "").strip().lower()
        p_clean = str(phone or "").strip()
        return (n_clean == self.DEV_NAME.lower()) or (p_clean == self.DEV_PHONE)

    def ensure_developer_and_clean_dummies(self):
        cur = self.conn.cursor()
        # حذف أي سجلات تجريبية قديمة ومنع عودتها
        dummy_names = ("حسن العضو", "أحمد اللاعب", "لاعب تجريبي", "علي المخول", "مدير تجريبي")
        for dn in dummy_names:
            cur.execute("DELETE FROM members WHERE TRIM(name) = ?", (dn,))
            cur.execute("DELETE FROM admins WHERE TRIM(name) = ?", (dn,))
        # تثبيت حساب المطور الرئيسي كأول مخول مطلق
        cur.execute("SELECT id FROM admins WHERE TRIM(phone) = ? OR LOWER(TRIM(name)) = ?", (self.DEV_PHONE, self.DEV_NAME.lower()))
        row = cur.fetchone()
        if not row:
            cur.execute(
                "INSERT INTO admins (name, phone, address, facebook) VALUES (?, ?, ?, ?)",
                (self.DEV_NAME, self.DEV_PHONE, "المطور والمخول الرئيسي للنظام", ""),
            )
        else:
            cur.execute("UPDATE admins SET name = ?, phone = ? WHERE id = ?", (self.DEV_NAME, self.DEV_PHONE, row[0]))
        self.conn.commit()
        self.set_setting("seed_done", "1")

    def get_admin_permissions(self, admin_name: str, admin_phone: str = "") -> dict:
        if self.is_developer(admin_name, admin_phone):
            return {"data": True, "notif": True, "chat": True, "sync": True, "is_dev": True}
        key = f"perm_{str(admin_name).strip()}"
        raw = self.get_setting(key)
        if not raw:
            # الصلاحيات الافتراضية للمخول الثانوي (ممنوع من البيانات نهائياً، وله الإشعارات والدردشة والمزامنة)
            return {"data": False, "notif": True, "chat": True, "sync": True, "is_dev": False}
        try:
            d = json.loads(raw)
            return {
                "data": False,  # محجوب دائماً عن المخول الثانوي
                "notif": bool(d.get("notif", True)),
                "chat": bool(d.get("chat", True)),
                "sync": bool(d.get("sync", True)),
                "is_dev": False,
            }
        except Exception:
            return {"data": False, "notif": True, "chat": True, "sync": True, "is_dev": False}

    def set_admin_permissions(self, admin_name: str, notif: bool = True, chat: bool = True, sync: bool = True):
        key = f"perm_{str(admin_name).strip()}"
        payload = json.dumps({"data": False, "notif": bool(notif), "chat": bool(chat), "sync": bool(sync)})
        self.set_setting(key, payload)
        # رفع الصلاحيات إلى السحابة لتنطبق على هاتف المخول الثانوي فوراً
        try:
            safe_k = urllib.parse.quote(str(admin_name).strip()) if "urllib.parse" in globals() else str(admin_name).strip().replace(" ", "_")
            endpoint = f"{self._firebase_url()}/admin_perms/{safe_k}.json"
            req = urllib.request.Request(endpoint, data=payload.encode("utf-8"), headers={"Content-Type": "application/json"}, method="PUT")
            urllib.request.urlopen(req, timeout=6)
        except Exception:
            pass

    def sync_admin_permissions_from_cloud(self, admin_name: str):
        try:
            safe_k = str(admin_name).strip().replace(" ", "_")
            endpoint = f"{self._firebase_url()}/admin_perms/{safe_k}.json"
            with urllib.request.urlopen(endpoint, timeout=5) as resp:
                raw = resp.read().decode("utf-8")
            if raw and raw != "null":
                self.set_setting(f"perm_{str(admin_name).strip()}", raw)
        except Exception:
            pass

    def get_records(self, table="members", search_term=""):
        tbl = "admins" if table == "admins" else "members"
        cur = self.conn.cursor()
        if (search_term or "").strip():
            q = f"%{search_term.strip()}%"
            cur.execute(f"SELECT id, name, phone, address, facebook FROM {tbl} WHERE name LIKE ? OR phone LIKE ? ORDER BY id DESC", (q, q))
        else:
            cur.execute(f"SELECT id, name, phone, address, facebook FROM {tbl} ORDER BY id DESC")
        return cur.fetchall()

    def add_record(self, table, name, phone, address="", facebook=""):
        tbl = "admins" if table == "admins" else "members"
        cur = self.conn.cursor()
        cur.execute(f"SELECT id FROM {tbl} WHERE TRIM(phone) = ? AND TRIM(phone) != ''", (phone.strip(),))
        if cur.fetchone():
            return False, "رقم الهاتف مسجل مسبقاً في هذا الجدول!"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        cur.execute(
            f"INSERT INTO {tbl} (name, phone, address, facebook, created_at) VALUES (?, ?, ?, ?, ?)",
            (name.strip(), phone.strip(), address.strip(), facebook.strip(), now),
        )
        self.conn.commit()
        return True, "تمت الإضافة والحفظ بنجاح ✔️"

    def update_record(self, table, rec_id, name, phone, address="", facebook=""):
        tbl = "admins" if table == "admins" else "members"
        cur = self.conn.cursor()
        cur.execute(
            f"UPDATE {tbl} SET name=?, phone=?, address=?, facebook=? WHERE id=?",
            (name.strip(), phone.strip(), address.strip(), facebook.strip(), rec_id),
        )
        self.conn.commit()
        return True, "تم تعديل السجل بنجاح ✔️"

    def delete_record(self, table, rec_id):
        tbl = "admins" if table == "admins" else "members"
        cur = self.conn.cursor()
        cur.execute(f"DELETE FROM {tbl} WHERE id=?", (rec_id,))
        self.conn.commit()
        return True, "تم حذف السجل 🗑️"

    def push_records_to_cloud(self, table="members"):
        tbl = "admins" if table == "admins" else "members"
        endpoint = f"{self._firebase_url()}/{tbl}.json"
        try:
            local_rows = self.get_records(tbl)
            payload = {
                f"rec_{r[0]}": {"name": r[1], "phone": r[2], "address": r[3], "facebook": r[4]}
                for r in local_rows
            }
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="PUT",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status == 200:
                    return True, f"تم رفع ({len(local_rows)}) سجل للسحابة ✔️"
            return False, "تعذر الرفع السحابي."
        except Exception as ex:
            return False, f"تعذر الاتصال بالسحابة: {ex}"

    def pull_records_from_cloud(self, table=None):
        tables_to_pull = [table] if table in ("members", "admins") else ["members", "admins"]
        total_pulled = 0
        cur = self.conn.cursor()
        for tbl in tables_to_pull:
            endpoint = f"{self._firebase_url()}/{tbl}.json"
            try:
                with urllib.request.urlopen(endpoint, timeout=8) as resp:
                    raw = json.loads(resp.read().decode("utf-8") or "{}")
                if not raw:
                    continue
                items = raw.values() if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    n = str(item.get("name") or "").strip()
                    p = str(item.get("phone") or "").strip()
                    addr = str(item.get("address") or "").strip()
                    fb = str(item.get("facebook") or "").strip()
                    if not n:
                        continue
                    cur.execute(f"SELECT id FROM {tbl} WHERE TRIM(name)=? AND TRIM(phone)=?", (n, p))
                    if not cur.fetchone():
                        cur.execute(
                            f"INSERT INTO {tbl} (name, phone, address, facebook, created_at) VALUES (?, ?, ?, ?, ?)",
                            (n, p, addr, fb, datetime.now().strftime("%Y-%m-%d %H:%M")),
                        )
                        total_pulled += 1
            except Exception:
                pass
        self.conn.commit()
        return total_pulled

    def sync_records_with_cloud(self, table="members"):
        pulled = self.pull_records_from_cloud(table)
        ok, msg = self.push_records_to_cloud(table)
        if ok:
            return True, f"تمت المزامنة: جُلب ({pulled}) ورُفع المحدث ✔️"
        return False, msg

    # --- الإشعارات المشفرة ---
    def add_notification(self, title: str, body: str, notif_type: str = "عام", sender: str = "الإدارة", cloud_id: str = ""):
        cur = self.conn.cursor()
        if cloud_id:
            cur.execute("SELECT id FROM notifications WHERE cloud_id = ?", (cloud_id,))
            if cur.fetchone():
                return False
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        cur.execute(
            "INSERT INTO notifications (cloud_id, title, body, notif_type, sender, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cloud_id, self.encrypt_text(title), self.encrypt_text(body), notif_type, sender, now),
        )
        self.conn.commit()
        return True

    def get_notifications(self):
        cur = self.conn.cursor()
        cur.execute("SELECT id, title, body, notif_type, sender, created_at FROM notifications ORDER BY id DESC")
        rows = cur.fetchall()
        return [
            (r[0], self.decrypt_text(r[1]), self.decrypt_text(r[2]), r[3] or "عام", r[4] or "الإدارة", r[5] or "")
            for r in rows
        ]

    def delete_notification(self, notif_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM notifications WHERE id = ?", (notif_id,))
        self.conn.commit()

    def push_notification_to_cloud(self, notif_type, content, sender="الإدارة"):
        try:
            endpoint = f"{self._firebase_url()}/notifications.json"
            data = {
                "type": notif_type,
                "content": self.encrypt_text(content),
                "sender": sender,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            req = urllib.request.Request(endpoint, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            urllib.request.urlopen(req, timeout=8)
            return True
        except Exception:
            return False

    def pull_notifications_from_cloud(self):
        new_count = 0
        try:
            endpoint = f"{self._firebase_url()}/notifications.json"
            with urllib.request.urlopen(endpoint, timeout=8) as resp:
                raw = json.loads(resp.read().decode("utf-8") or "{}")
            if not isinstance(raw, dict):
                return 0
            for cid, v in raw.items():
                if not isinstance(v, dict):
                    continue
                ntype = v.get("type", "عام")
                body = self.decrypt_text(v.get("content", ""))
                sender = v.get("sender", "الإدارة")
                if body and self.add_notification(title=ntype, body=body, notif_type=ntype, sender=sender, cloud_id=str(cid)):
                    new_count += 1
        except Exception:
            pass
        return new_count

    # --- الدردشة النصية والصوتية ثنائية الاتجاه (Firebase <-> SQLite) ---
    def delete_chat_message(self, msg_id: int, cloud_id: str = ""):
        cur = self.conn.cursor()
        if not cloud_id and msg_id:
            cur.execute("SELECT cloud_id FROM chat_messages WHERE id = ?", (msg_id,))
            row = cur.fetchone()
            if row and row[0]:
                cloud_id = str(row[0])
        if msg_id:
            cur.execute("DELETE FROM chat_messages WHERE id = ?", (msg_id,))
        if cloud_id:
            cur.execute("DELETE FROM chat_messages WHERE cloud_id = ?", (cloud_id,))
        self.conn.commit()
        if cloud_id:
            try:
                endpoint = f"{self._firebase_url()}/chat_messages/{cloud_id}.json"
                req = urllib.request.Request(endpoint, method="DELETE")
                urllib.request.urlopen(req, timeout=6)
            except Exception:
                pass

    def cleanup_expired_chat_media(self, max_age_hours: int):
        if max_age_hours <= 0:
            return 0
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(hours=max_age_hours)
        cur = self.conn.cursor()
        cur.execute("SELECT id, cloud_id, message, msg_type, created_at FROM chat_messages")
        rows = cur.fetchall()
        deleted = 0
        for r_id, c_id, enc_msg, m_type, c_at in rows:
            dec = self.decrypt_text(enc_msg or "")
            is_media = (m_type == "audio") or dec.startswith("[IMG_B64]") or dec.startswith("[FILE_B64|") or dec.startswith("[GRP_CALL|") or dec.startswith("[PRIV_CALL|")
            if not is_media:
                continue
            try:
                dt = datetime.strptime(str(c_at)[:16], "%Y-%m-%d %H:%M")
                if dt < cutoff:
                    self.delete_chat_message(r_id, str(c_id or ""))
                    deleted += 1
            except Exception:
                pass
        return deleted

    def add_chat_message(self, sender="عضو", message="", content=None, audio_data="", audio_path=None, msg_type="text", cloud_id="", timestamp=None, **kwargs):
        final_text = content if content is not None else (message or "")
        final_audio = audio_path if audio_path is not None else (audio_data or "")
        cur = self.conn.cursor()
        if cloud_id:
            cur.execute("SELECT id FROM chat_messages WHERE cloud_id = ?", (cloud_id,))
            if cur.fetchone():
                return False
        now = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M")
        cur.execute(
            "INSERT INTO chat_messages (cloud_id, sender, message, audio_data, msg_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (cloud_id, sender, self.encrypt_text(final_text), final_audio, msg_type, now),
        )
        self.conn.commit()
        return True

    def get_chat_messages(self, limit: int = 150):
        cur = self.conn.cursor()
        cur.execute("SELECT id, sender, message, audio_data, msg_type, created_at FROM chat_messages ORDER BY id ASC LIMIT ?", (limit,))
        rows = cur.fetchall()
        out = []
        for r in rows:
            dec_text = self.decrypt_text(r[2])
            out.append({
                "id": r[0],
                "sender": r[1],
                "content": dec_text,
                "message": dec_text,
                "audio_path": r[3],
                "audio_data": r[3],
                "type": r[4] or "text",
                "msg_type": r[4] or "text",
                "timestamp": r[5] or "",
            })
        return out

    def push_chat_to_cloud(self, sender, msg_type="text", content="", audio_path=""):
        try:
            audio_b64 = ""
            if msg_type == "audio" and audio_path and os.path.exists(audio_path):
                with open(audio_path, "rb") as af:
                    audio_b64 = base64.b64encode(af.read()).decode("utf-8")
            endpoint = f"{self._firebase_url()}/chat_messages.json"
            data = {
                "sender": sender,
                "type": msg_type,
                "content": self.encrypt_text(content),
                "audio_b64": audio_b64,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            req = urllib.request.Request(endpoint, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                res_obj = json.loads(resp.read().decode("utf-8") or "{}")
                cid = res_obj.get("name", "")
                if cid:
                    cur = self.conn.cursor()
                    cur.execute("UPDATE chat_messages SET cloud_id = ? WHERE id = (SELECT MAX(id) FROM chat_messages)", (cid,))
                    self.conn.commit()
            return True
        except Exception:
            return False

    def pull_chat_from_cloud(self):
        new_count = 0
        audio_dir = os.path.join(self.storage_dir, "cloud_audio")
        os.makedirs(audio_dir, exist_ok=True)
        try:
            endpoint = f"{self._firebase_url()}/chat_messages.json"
            with urllib.request.urlopen(endpoint, timeout=8) as resp:
                raw = json.loads(resp.read().decode("utf-8") or "{}")
            if not isinstance(raw, dict):
                return 0
            for cid, v in raw.items():
                if not isinstance(v, dict):
                    continue
                sender = v.get("sender", "عضو")
                mtype = v.get("type", "text")
                text = self.decrypt_text(v.get("content", ""))
                ts = v.get("timestamp", "")
                audio_b64 = v.get("audio_b64", "")
                saved_audio = ""
                if mtype == "audio" and audio_b64:
                    saved_audio = os.path.join(audio_dir, f"cloud_{cid}.wav")
                    if not os.path.exists(saved_audio):
                        try:
                            with open(saved_audio, "wb") as af:
                                af.write(base64.b64decode(audio_b64))
                        except Exception:
                            saved_audio = ""
                if self.add_chat_message(sender=sender, content=text, audio_path=saved_audio, msg_type=mtype, cloud_id=str(cid), timestamp=ts):
                    new_count += 1
        except Exception:
            pass
        return new_count
