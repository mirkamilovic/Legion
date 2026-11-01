#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║  DARK UTAG BOT  —  bitta faylli to'liq loyiha                ║
║  aiogram 3 (bot) + Telethon (userbot) + SQLite               ║
╚══════════════════════════════════════════════════════════════╝

O'RNATISH
    pip install "aiogram>=3.7" "telethon>=1.34" aiosqlite cryptography "qrcode[pil]"

SOZLASH  (shu papkada .env fayl yarating yoki muhit o'zgaruvchisi qilib bering)
    BOT_TOKEN=123456:ABC...          # @BotFather dan
    API_ID=1234567                   # https://my.telegram.org dan
    API_HASH=abcdef0123456789...     # https://my.telegram.org dan
    OWNER_ID=5588583777              # sizning Telegram ID raqamingiz
    OWNER_USERNAME=Alikhanov_fx      # "Karta orqali to'lov" tugmasi shu lichkaga olib boradi
    # ixtiyoriy:
    # ENCRYPTION_KEY=...             # bo'lmasa .utag_key fayli avtomatik yaratiladi
    # DB_PATH=utag.db

ISHGA TUSHIRISH
    python utag_bot.py

ESLATMA
    * .utag_key faylini va utag.db ni yo'qotmang (sessiyalar shu kalit bilan shifrlangan).
    * Papkaga logo.jpg qo'ysangiz, /start da rasm bilan chiqadi (ixtiyoriy).
    * Majburiy obuna kanallarida bot ADMIN bo'lishi kerak.
"""
from __future__ import annotations

import asyncio
import csv
import html
import io
import logging
import os
import random
import re
import shutil
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote


def _load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

import aiosqlite  # noqa: E402
from cryptography.fernet import Fernet  # noqa: E402

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter  # noqa: E402
from aiogram.filters import CommandStart  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.state import State, StatesGroup  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.types import (  # noqa: E402
    BufferedInputFile, CallbackQuery, ErrorEvent, FSInputFile, InlineKeyboardButton,
    InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup,
)

from telethon import TelegramClient, events  # noqa: E402
from telethon.errors import (  # noqa: E402
    AuthKeyUnregisteredError, ChannelPrivateError, ChatAdminRequiredError, ChatWriteForbiddenError,
    FloodWaitError, InviteHashExpiredError, InviteHashInvalidError, PasswordHashInvalidError,
    PhoneCodeExpiredError, PhoneCodeInvalidError, PhoneNumberBannedError, PhoneNumberInvalidError,
    SessionExpiredError, SessionPasswordNeededError, SessionRevokedError, SlowModeWaitError,
    UserBannedInChannelError, UserDeactivatedBanError, UserDeactivatedError,
    UsernameInvalidError, UsernameNotOccupiedError,
)
from telethon.sessions import StringSession  # noqa: E402
from telethon.tl.functions.channels import JoinChannelRequest  # noqa: E402
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest  # noqa: E402
from telethon.tl.types import (  # noqa: E402
    Channel, ChannelParticipantsAdmins, ChatInviteAlready, User, UserStatusOnline, UserStatusRecently,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("utag")

# ══════════════════════════ SOZLAMALAR ══════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "0") or 0)
OWNER_USERNAME = os.getenv("OWNER_USERNAME", "Alikhanov_fx").lstrip("@")
DB_PATH = os.getenv("DB_PATH", "utag.db")
KEY_FILE = ".utag_key"
LOGO_FILE = "logo.jpg"
MAX_SCRAPE = int(os.getenv("MAX_SCRAPE", "20000"))                  # bir marta yig'iladigan maks. user
MAX_MENTION_MEMBERS = int(os.getenv("MAX_MENTION_MEMBERS", "5000"))  # bir marta mention qilinadigan maks. a'zo
MENTION_BATCH = 5                                                    # bitta xabarda nechta mention
TZ = timezone(timedelta(hours=5))                                    # Toshkent vaqti
BOT_USERNAME = ""
BOT: Bot = None  # type: ignore

GIFT_TIERS = [
    (8, "🎁 <b>Gift 15 talik</b>", "Do'stlaringizni taklif qiling va 15 talik giftni yutib oling!"),
    (20, "🎁 <b>Katta gift</b>", "Do'stlaringizni taklif qiling va katta giftga ega bo'ling!"),
]

DEFAULT_RANDOM_TEXTS = ["Salom", "Qalaysiz", "Nima gap", "Mana bu yerda", "Kiring", "Diqqat", "Tez keling", "Eshityapsizmi"]

# (key, title, price, days, max_accounts, can_export, scrape_daily, mention_daily, active, sort)
DEFAULT_PLANS = [
    ("free", "DARK FAMILY UCHUN", 0, 30, 1, 0, -1, 300, 1, 0),
    ("start", "START", 29000, 30, 2, 1, -1, 2000, 1, 1),
    ("pro", "PRO", 59000, 30, 5, 1, -1, 10000, 1, 2),
    ("vip", "VIP", 99000, 30, 10, 1, -1, -1, 1, 3),
]
OWNER_PLAN = dict(key="owner", title="OWNER", price=0, days=0, max_accounts=100, can_export=1,
                  scrape_daily=-1, mention_daily=-1, active=1, sort=-1)


def load_fernet() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY", "").strip()
    if not key:
        if os.path.exists(KEY_FILE):
            key = open(KEY_FILE, encoding="utf-8").read().strip()
        else:
            key = Fernet.generate_key().decode()
            with open(KEY_FILE, "w", encoding="utf-8") as f:
                f.write(key)
            try:
                os.chmod(KEY_FILE, 0o600)
            except OSError:
                pass
    return Fernet(key.encode())


FERNET = load_fernet()

# ══════════════════════════ YORDAMCHILAR ══════════════════════════
esc = html.escape


def today() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d")


def lim(n: int) -> str:
    return "∞" if n < 0 else str(n)


def fmt_left(ts: float) -> str:
    s = int(ts - time.time())
    if s <= 0:
        return "tugagan"
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    if d:
        return f"{d} kun {h} soat"
    return f"{h} soat {m} daqiqa"


def fmt_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, TZ).strftime("%d.%m.%Y %H:%M")


def yn(v) -> str:
    return "✅" if v else "❌"


def ikb(*rows) -> InlineKeyboardMarkup:
    """ikb([("Matn","callback")], [("Havola","https://...")])"""
    out = []
    for r in rows:
        line = []
        for t, v in r:
            if v.startswith(("http://", "https://", "tg://")):
                line.append(InlineKeyboardButton(text=t, url=v))
            else:
                line.append(InlineKeyboardButton(text=t, callback_data=v))
        out.append(line)
    return InlineKeyboardMarkup(inline_keyboard=out)


def mention_html(uid: int, username: str | None, name: str) -> str:
    if username:
        return f"@{username}"
    return f'<a href="tg://user?id={uid}">{esc(name or "user")}</a>'


# ══════════════════════════ BAZA ══════════════════════════
DB: aiosqlite.Connection = None  # type: ignore

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
    id INTEGER PRIMARY KEY, username TEXT, full_name TEXT, joined REAL, banned INTEGER DEFAULT 0,
    plan_key TEXT DEFAULT '', plan_until REAL DEFAULT 0, free_used INTEGER DEFAULT 0,
    exp_notified INTEGER DEFAULT 0, ref_used INTEGER DEFAULT 0,
    mention_on INTEGER DEFAULT 1, mention_delay INTEGER DEFAULT 2);
CREATE TABLE IF NOT EXISTS plans(
    key TEXT PRIMARY KEY, title TEXT, price INTEGER, days INTEGER, max_accounts INTEGER,
    can_export INTEGER, scrape_daily INTEGER, mention_daily INTEGER, active INTEGER, sort INTEGER);
CREATE TABLE IF NOT EXISTS accounts(
    id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, phone TEXT, tg_id INTEGER, name TEXT,
    username TEXT, session TEXT, status TEXT DEFAULT 'active', created REAL);
CREATE TABLE IF NOT EXISTS sources(
    id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id INTEGER, title TEXT, link TEXT, mode TEXT,
    cnt INTEGER, created REAL);
CREATE TABLE IF NOT EXISTS collected(
    source_id INTEGER, owner_id INTEGER, tg_id INTEGER, username TEXT, name TEXT,
    UNIQUE(source_id, tg_id));
CREATE TABLE IF NOT EXISTS usage(
    user_id INTEGER, day TEXT, scrapes INTEGER DEFAULT 0, mentions INTEGER DEFAULT 0,
    PRIMARY KEY(user_id, day));
CREATE TABLE IF NOT EXISTS referrals(
    invited_id INTEGER PRIMARY KEY, referrer_id INTEGER, created REAL);
CREATE TABLE IF NOT EXISTS channels(
    chat_id INTEGER PRIMARY KEY, title TEXT, link TEXT);
CREATE INDEX IF NOT EXISTS idx_coll_owner ON collected(owner_id);
CREATE INDEX IF NOT EXISTS idx_acc_owner ON accounts(owner_id);
"""


async def init_db() -> None:
    global DB
    DB = await aiosqlite.connect(DB_PATH)
    DB.row_factory = aiosqlite.Row
    await DB.execute("PRAGMA journal_mode=WAL")
    await DB.executescript(SCHEMA)
    cnt = await db_one("SELECT COUNT(*) c FROM plans")
    if cnt["c"] == 0:
        await DB.executemany("INSERT INTO plans VALUES(?,?,?,?,?,?,?,?,?,?)", DEFAULT_PLANS)
    await DB.commit()


async def db_exec(sql: str, args: tuple = ()):
    cur = await DB.execute(sql, args)
    await DB.commit()
    return cur


async def db_many(sql: str, rows: list):
    await DB.executemany(sql, rows)
    await DB.commit()


async def db_one(sql: str, args: tuple = ()):
    async with DB.execute(sql, args) as cur:
        return await cur.fetchone()


async def db_all(sql: str, args: tuple = ()):
    async with DB.execute(sql, args) as cur:
        return await cur.fetchall()


async def get_user(uid: int):
    return await db_one("SELECT * FROM users WHERE id=?", (uid,))


async def get_plan_row(key: str):
    return await db_one("SELECT * FROM plans WHERE key=?", (key,))


async def get_active_plan(uid: int) -> dict | None:
    if uid == OWNER_ID:
        return dict(OWNER_PLAN)
    u = await get_user(uid)
    if not u or not u["plan_key"] or u["plan_until"] < time.time():
        return None
    p = await get_plan_row(u["plan_key"])
    return dict(p) if p else None


async def activate_plan(uid: int, key: str, days: int) -> float:
    u = await get_user(uid)
    now = time.time()
    start = u["plan_until"] if (u["plan_key"] == key and u["plan_until"] > now) else now
    until = start + days * 86400
    await db_exec("UPDATE users SET plan_key=?, plan_until=?, exp_notified=0 WHERE id=?", (key, until, uid))
    return until


async def usage_get(uid: int) -> tuple[int, int]:
    r = await db_one("SELECT scrapes, mentions FROM usage WHERE user_id=? AND day=?", (uid, today()))
    return (r["scrapes"], r["mentions"]) if r else (0, 0)


async def usage_add(uid: int, scrapes: int = 0, mentions: int = 0) -> None:
    await db_exec(
        "INSERT INTO usage(user_id,day,scrapes,mentions) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id,day) DO UPDATE SET scrapes=scrapes+?, mentions=mentions+?",
        (uid, today(), scrapes, mentions, scrapes, mentions))


_notify_last: dict[int, float] = {}


async def notify_user(uid: int, text: str, cooldown: float = 0, **kw) -> None:
    """Foydalanuvchiga bot orqali xabar (cooldown — takrorlanmasligi uchun)."""
    now = time.time()
    if cooldown and now - _notify_last.get(uid, 0) < cooldown:
        return
    _notify_last[uid] = now
    try:
        await BOT.send_message(uid, text, **kw)
    except Exception as e:  # noqa: BLE001
        log.debug("notify fail %s: %s", uid, e)


# ══════════════════════════ TELETHON (USERBOT) ══════════════════════════
CLIENTS: dict[int, TelegramClient] = {}          # account_id -> client
RUNNING: dict[tuple[int, int], asyncio.Event] = {}  # (account_id, chat_id) -> stop flag
BG_TASKS: set = set()


def spawn(coro) -> asyncio.Task:
    t = asyncio.create_task(coro)
    BG_TASKS.add(t)
    t.add_done_callback(BG_TASKS.discard)
    return t


def new_client(session: str = "") -> TelegramClient:
    return TelegramClient(StringSession(session), API_ID, API_HASH,
                          device_model="Desktop", system_version="Windows 10", app_version="5.0.1")


def is_online(u) -> bool:
    return isinstance(getattr(u, "status", None), (UserStatusOnline, UserStatusRecently))


def user_title(u) -> str:
    name = " ".join(x for x in [getattr(u, "first_name", None), getattr(u, "last_name", None)] if x)
    return name or getattr(u, "username", None) or "user"


def calc_delay(base: int) -> float:
    """Juda tez ham, juda sekin ham emas: asos + tasodifiy qo'shimcha (1.5s…12s oralig'ida)."""
    d = base + random.uniform(0.2, 0.5 * base + 0.8)
    return min(max(d, 1.5), 12.0)


async def mark_dead(acc_id: int, reason: str) -> None:
    acc = await db_one("SELECT * FROM accounts WHERE id=?", (acc_id,))
    if not acc or acc["status"] == "dead":
        return
    await db_exec("UPDATE accounts SET status='dead' WHERE id=?", (acc_id,))
    cl = CLIENTS.pop(acc_id, None)
    if cl:
        try:
            await cl.disconnect()
        except Exception:  # noqa: BLE001
            pass
    label = f"{acc['name']} ({acc['phone']})"
    await notify_user(acc["owner_id"], f"⚠️ <b>Akkaunt uzildi:</b> {esc(label)}\nSabab: {esc(reason)}\n\n"
                                       f"Qayta ulash uchun «👤 Akkauntlarim» bo'limiga kiring.")
    if acc["owner_id"] != OWNER_ID:
        await notify_user(OWNER_ID, f"🛡 Akkaunt o'ldi: {esc(label)} | user <code>{acc['owner_id']}</code> | {esc(reason)}")


AUTH_ERRORS = (AuthKeyUnregisteredError, UserDeactivatedError, UserDeactivatedBanError,
               SessionRevokedError, SessionExpiredError)


async def start_account(acc) -> bool:
    """Saqlangan sessiyani ishga tushiradi va handlerlarni ulaydi."""
    acc_id = acc["id"]
    if acc_id in CLIENTS:
        return True
    try:
        sess = FERNET.decrypt(acc["session"].encode()).decode()
        client = new_client(sess)
        await client.connect()
        if not await client.is_user_authorized():
            await client.disconnect()
            await mark_dead(acc_id, "sessiya yaroqsiz")
            return False
        attach_handlers(client, acc_id, acc["owner_id"])
        CLIENTS[acc_id] = client
        return True
    except AUTH_ERRORS as e:
        await mark_dead(acc_id, type(e).__name__)
    except Exception as e:  # noqa: BLE001
        log.warning("start_account %s: %s", acc_id, e)
    return False


async def get_client(acc_id: int) -> TelegramClient | None:
    if acc_id in CLIENTS:
        return CLIENTS[acc_id]
    acc = await db_one("SELECT * FROM accounts WHERE id=? AND status='active'", (acc_id,))
    if acc and await start_account(acc):
        return CLIENTS.get(acc_id)
    return None


async def health_check() -> tuple[int, int]:
    ok = dead = 0
    for acc_id, cl in list(CLIENTS.items()):
        try:
            me = await cl.get_me()
            if me is None:
                raise AuthKeyUnregisteredError(None)
            ok += 1
        except AUTH_ERRORS as e:
            await mark_dead(acc_id, type(e).__name__)
            dead += 1
        except Exception as e:  # noqa: BLE001
            log.debug("health %s: %s", acc_id, e)
    return ok, dead


def attach_handlers(client: TelegramClient, acc_id: int, owner_id: int) -> None:
    async def on_msg(event):
        try:
            await on_outgoing(event, client, acc_id, owner_id)
        except Exception as e:  # noqa: BLE001
            log.warning("mention handler: %s", e)

    client.add_event_handler(on_msg, events.NewMessage(outgoing=True, pattern=r"^\.(?:uo|u|r|su)(?:\s|$)"))


async def on_outgoing(event, client: TelegramClient, acc_id: int, owner_id: int) -> None:
    if not event.is_group:
        return
    m = re.match(r"^\.(uo|u|r|su)(?:\s+(.*))?$", (event.raw_text or "").strip(), re.S)
    if not m:
        return
    cmd, arg = m.group(1), (m.group(2) or "").strip()
    key = (acc_id, event.chat_id)

    if cmd == "su":
        ev = RUNNING.get(key)
        if ev:
            ev.set()
        try:
            await event.delete()
        except Exception:  # noqa: BLE001
            pass
        return

    u = await get_user(owner_id)
    if owner_id != OWNER_ID and (not u or u["banned"]):
        return
    if u and not u["mention_on"]:
        return
    plan = await get_active_plan(owner_id)
    if not plan:
        await notify_user(owner_id, "⛔ Mention ishlamadi: faol tarifingiz yo'q.\n«💳 Tarif sotib olish» bo'limiga kiring.", cooldown=600)
        return
    if key in RUNNING:
        return
    stop = asyncio.Event()
    RUNNING[key] = stop
    spawn(run_mention(client, event, acc_id, owner_id, cmd, arg, stop))


async def run_mention(client, event, acc_id, owner_id, cmd, arg, stop: asyncio.Event) -> None:
    key = (acc_id, event.chat_id)
    try:
        chat = await event.get_input_chat()
        try:
            await event.delete()
        except Exception:  # noqa: BLE001
            pass
        me = await client.get_me()
        members = []
        async for u in client.iter_participants(chat, limit=MAX_MENTION_MEMBERS):
            if stop.is_set():
                return
            if u.bot or u.deleted or u.id == me.id:
                continue
            if cmd == "uo" and not is_online(u):
                continue
            members.append(u)
        if not members:
            await notify_user(owner_id, "ℹ️ Mention uchun mos a'zo topilmadi.", cooldown=60)
            return

        urow = await get_user(owner_id)
        base = min(max(int(urow["mention_delay"]) if urow else 2, 1), 10)
        n = len(members)
        if n > 500:
            base = max(base, 5)
        elif n > 100:
            base = max(base, 3)

        texts = []
        if cmd == "r":
            texts = [t.strip() for t in arg.split("|") if t.strip()] or DEFAULT_RANDOM_TEXTS

        i = 0
        while i < n and not stop.is_set():
            batch = members[i:i + MENTION_BATCH]
            plan = await get_active_plan(owner_id)
            if not plan:
                await notify_user(owner_id, "⛔ Tarifingiz tugadi, mention to'xtatildi.")
                break
            if plan["mention_daily"] >= 0:
                _, used = await usage_get(owner_id)
                if used + len(batch) > plan["mention_daily"]:
                    await notify_user(owner_id, f"📈 Kunlik mention limiti tugadi ({used}/{plan['mention_daily']}). "
                                                f"Ertaga davom ettiring yoki tarifni oshiring.")
                    break
            if cmd == "r":
                lines = [f"{esc(random.choice(texts))} {mention_html(u.id, u.username, user_title(u)[:14])}" for u in batch]
                text = "\n".join(lines)
            else:
                head = (esc(arg) + "\n") if arg else ""
                text = head + " ".join(mention_html(u.id, u.username, user_title(u)[:14]) for u in batch)
            try:
                await client.send_message(chat, text, parse_mode="html", link_preview=False)
                await usage_add(owner_id, mentions=len(batch))
                i += len(batch)
            except (FloodWaitError, SlowModeWaitError) as e:
                wait = int(getattr(e, "seconds", 30)) + 1
                if wait > 900:
                    await notify_user(owner_id, f"⏳ Telegram {wait} soniya kutishni talab qildi, mention to'xtatildi.")
                    break
                await asyncio.sleep(wait)
                continue
            except (ChatWriteForbiddenError, UserBannedInChannelError, ChatAdminRequiredError) as e:
                await notify_user(owner_id, f"🚫 Guruhga yozish mumkin emas: {type(e).__name__}")
                break
            except Exception as e:  # noqa: BLE001
                log.warning("mention send: %s", e)
                await notify_user(owner_id, f"⚠️ Mention xatosi: {esc(type(e).__name__)}")
                break
            await asyncio.sleep(calc_delay(base))
    except AUTH_ERRORS as e:
        await mark_dead(acc_id, type(e).__name__)
    except Exception as e:  # noqa: BLE001
        log.warning("run_mention: %s", e)
    finally:
        RUNNING.pop(key, None)


# ───────────── Scraper (odam yig'ish) ─────────────
class ScrapeError(Exception):
    pass


async def resolve_group(client: TelegramClient, raw: str):
    s = raw.strip()
    m = re.search(r"(?:t\.me|telegram\.me)/(?:\+|joinchat/)([\w-]+)", s)
    try:
        if m:
            h = m.group(1)
            r = await client(CheckChatInviteRequest(h))
            if isinstance(r, ChatInviteAlready):
                return r.chat
            upd = await client(ImportChatInviteRequest(h))
            return upd.chats[0]
        m = re.search(r"(?:t\.me|telegram\.me)/([A-Za-z]\w{3,})", s) or re.match(r"^@?([A-Za-z]\w{3,})$", s)
        if not m:
            raise ScrapeError("Link noto'g'ri. Masalan: https://t.me/+AbCd… yoki @guruh_nomi")
        ent = await client.get_entity(m.group(1))
        if isinstance(ent, User):
            raise ScrapeError("Bu guruh emas, oddiy foydalanuvchi.")
        return ent
    except (InviteHashExpiredError, InviteHashInvalidError):
        raise ScrapeError("Taklif linki yaroqsiz yoki muddati o'tgan.")
    except (UsernameNotOccupiedError, UsernameInvalidError):
        raise ScrapeError("Bunday guruh topilmadi.")
    except ValueError:
        raise ScrapeError("Guruh topilmadi. Linkni tekshiring.")


async def scrape_members(client: TelegramClient, ent, mode: str) -> list[dict]:
    if isinstance(ent, Channel) and ent.broadcast and not ent.megagroup:
        raise ScrapeError("Bu kanal, guruh emas. Kanal a'zolarini yig'ib bo'lmaydi.")
    try:
        admins: set[int] = set()
        if mode == "noadmin":
            try:
                async for a in client.iter_participants(ent, filter=ChannelParticipantsAdmins):
                    admins.add(a.id)
            except Exception:  # noqa: BLE001
                pass
        out: list[dict] = []
        async for u in client.iter_participants(ent, limit=MAX_SCRAPE):
            if u.bot or u.deleted:
                continue
            if mode == "username" and not u.username:
                continue
            if mode == "online" and not is_online(u):
                continue
            if mode == "noadmin" and u.id in admins:
                continue
            out.append(dict(id=u.id, username=u.username or "", name=user_title(u)))
        return out
    except ChannelPrivateError:
        if isinstance(ent, Channel):
            try:
                await client(JoinChannelRequest(ent))
                return await scrape_members(client, ent, mode)
            except Exception:  # noqa: BLE001
                pass
        raise ScrapeError("Guruhga kirish imkoni yo'q (yopiq guruh). Akkaunt guruhga a'zo bo'lishi kerak.")
    except ChatAdminRequiredError:
        raise ScrapeError("Bu guruhda a'zolar ro'yxati yashirilgan.")
    except FloodWaitError as e:
        raise ScrapeError(f"Telegram cheklovi: {e.seconds} soniya kuting va qayta urinib ko'ring.")


# ══════════════════════════ MATNLAR ══════════════════════════
B_SCRAPE = "🧲 Odam yig'ish"
B_COLL = "📁 Yig'ilgan userlar"
B_ACCS = "👤 Akkauntlarim"
B_PLANS = "💳 Tarif sotib olish"
B_REF = "🔗 Referal"
B_SET = "⚙️ Sozlamalar"
B_STAT = "📊 Statistika"
B_HELP = "ℹ️ Yordam"
B_ADMIN = "👑 Admin panel"
B_CANCEL = "❌ Bekor qilish"
B_BACK = "🔙 Bosh menyu"
B_ADD = "➕ Yangi akkaunt qo'shish"
B_LIST = "📋 Akkauntlarim ro'yxati"
B_DEL = "❌ Akkauntni o'chirish"
B_PHONE = "📞 Telefon orqali"
B_QR = "📷 QR kod orqali"
B_SENDPHONE = "📱 Telefon raqamni yuborish"

MODES = {"all": "👥 Hammasi", "username": "🔖 Faqat username'lilar",
         "online": "🟢 Faqat online", "noadmin": "🛡 Adminlarsiz"}


def main_kb(uid: int) -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=B_SCRAPE)],
            [KeyboardButton(text=B_COLL), KeyboardButton(text=B_ACCS)],
            [KeyboardButton(text=B_PLANS), KeyboardButton(text=B_REF)],
            [KeyboardButton(text=B_SET), KeyboardButton(text=B_STAT), KeyboardButton(text=B_HELP)]]
    if uid == OWNER_ID:
        rows.append([KeyboardButton(text=B_ADMIN)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def cancel_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=B_CANCEL)]], resize_keyboard=True)


def acc_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=B_ADD)],
        [KeyboardButton(text=B_LIST), KeyboardButton(text=B_DEL)],
        [KeyboardButton(text=B_BACK)]], resize_keyboard=True)


def pay_url(plan_title: str, uid: int) -> str:
    return f"https://t.me/{OWNER_USERNAME}?text=" + quote(f"Salom! {plan_title} tarifini sotib olmoqchiman. Mening ID: {uid}")


def plan_card(p) -> str:
    price = "BEPUL 🎁" if p["price"] == 0 else f"{p['price']:,} so'm".replace(",", " ")
    return (f"⭐ <b>{esc(p['title'])}</b>\n"
            f"┌──────────────────\n"
            f"├ 💰 Narx: <b>{price}</b>\n"
            f"├ ⏳ Muddati: <b>{p['days']} kun</b>\n"
            f"├ 👤 Akkauntlar: <b>{p['max_accounts']} ta</b>\n"
            f"├ 🧲 Odam yig'ish: <b>{'Cheksiz ♾' if p['scrape_daily'] < 0 else str(p['scrape_daily']) + ' ta/kun'}</b>\n"
            f"├ 📥 Userlarni yuklab olish: {yn(p['can_export'])}\n"
            f"├ 📣 Mention (.u .uo .r): <b>{'Cheksiz ♾' if p['mention_daily'] < 0 else str(p['mention_daily']) + ' ta/kun'}</b>\n"
            f"└──────────────────")


NO_PLAN_TEXT = ("⛔ <b>Faol tarifingiz yo'q.</b>\n\nBepul tarifni olish uchun pastdagi tugmani bosing "
                "yoki «💳 Tarif sotib olish» bo'limiga kiring.")


def no_plan_kb():
    return ikb([("🎁 Bepul olish", "getfree")])


async def stat_text(uid: int) -> str:
    u = await get_user(uid)
    plan = await get_active_plan(uid)
    sc, mn = await usage_get(uid)
    accs = (await db_one("SELECT COUNT(*) c FROM accounts WHERE owner_id=? AND status='active'", (uid,)))["c"]
    coll = (await db_one("SELECT COUNT(*) c FROM collected WHERE owner_id=?", (uid,)))["c"]
    if plan:
        exp_txt = "Ha" if plan["can_export"] else "Yo'q"
        left = "Cheksiz" if uid == OWNER_ID else fmt_left(u["plan_until"])
        body = (f"💳 <b>Sizning tarifingiz:</b> {esc(plan['title'])}\n"
                f"⏳ <b>Tugashiga qoldi:</b> {left}\n\n"
                f"📋 <b>Tarif imkoniyatlari:</b>\n"
                f"• Odam yig'ish: ✅ Ha\n"
                f"• Userlarni yuklab olish: {yn(plan['can_export'])} {exp_txt}\n"
                f"• Mention: ✅ Ha\n"
                f"• Akkauntlar: {plan['max_accounts']} ta\n\n"
                f"📈 <b>Kunlik limitlar:</b>\n"
                f"• Odam yig'ish: {sc} / {lim(plan['scrape_daily'])}\n"
                f"• Mention: {mn} / {lim(plan['mention_daily'])}\n")
    else:
        body = "💳 <b>Sizning tarifingiz:</b> ❌ faol emas\n\n"
    return (f"📊 <b>Statistika</b>\n\n{body}\n⚙️ <b>Umumiy:</b>\n"
            f"• Ulangan akkauntlar: {accs} ta\n• Yig'ilgan userlar: {coll} ta\n• Bugungi mentionlar: {mn} ta\n\n"
            f"<i>Ma'lumotlar real vaqtda yangilanadi</i>")


GUIDE_TEXT = (
    "📖 <b>Mention qo'llanmasi</b>\n\n"
    "Bu funksiya guruhlarda a'zolarni belgilash (mention) uchun ishlatiladi. "
    "Buyruqni <b>ulangan akkauntingiz bilan guruhga</b> yozasiz.\n\n"
    "📌 <b>Buyruqlar:</b>\n"
    "• <code>.u matn</code> — guruhdagi barcha a'zolarni matn bilan mention qiladi\n"
    "• <code>.uo matn</code> — faqat online a'zolarni mention qiladi\n"
    "• <code>.r matn1 | matn2 | matn3</code> — har bir a'zoni tasodifiy matn bilan mention qiladi\n"
    "• <code>.su</code> — joriy chatdagi mention jarayonini to'xtatadi\n\n"
    "⚙️ <b>Sozlamalar:</b>\n"
    "• Mention YOQILGAN/O'CHIRILGAN — funksiyani butunlay yoqish yoki o'chirish\n"
    "• Tezlik — mention xabarlari orasidagi vaqt (sekund)\n\n"
    "💡 <b>Maslahat:</b>\n"
    "• Kichik guruhlarda (50 tagacha) tezroq: 1–3s\n"
    "• Katta guruhlarda (100+) sekinroq: 5–10s (bot buni avtomatik ham moslaydi)\n"
    "• Telegram limitiga tushmaslik uchun <code>.uo</code> bilan online userlarni belgilang\n"
    "• Bot xavfsizlik uchun pauzaga tasodifiy qo'shimcha qo'shadi"
)

HELP_TEXT = (
    "ℹ️ <b>Yordam</b>\n\n"
    "🚀 <b>Boshlash uchun 3 qadam:</b>\n"
    "1️⃣ <b>Akkaunt ulang:</b> 👤 Akkauntlarim bo'limi\n"
    "2️⃣ <b>Odam yig'ing:</b> 🧲 Odam yig'ish orqali guruhlardan user yig'ing\n"
    "3️⃣ <b>Mention qiling:</b> guruhda <code>.u</code>, <code>.uo</code>, <code>.r</code> buyruqlarini yozing\n\n"
    "📥 Yig'ilgan userlarni yuklab olish pullik tarifda mavjud.\n"
    "🔗 Do'stlaringizni taklif qilib sovg'alar yuting.\n\n"
    f"👑 Savollar uchun: @{OWNER_USERNAME}"
)


# ══════════════════════════ BOT (aiogram) ══════════════════════════
router = Router()
admin = Router()
TEMP: dict[int, dict] = {}   # akkaunt ulash jarayonidagi vaqtinchalik clientlar


class AddAcc(StatesGroup):
    method = State()
    phone = State()
    code = State()
    password = State()


class Scrape(StatesGroup):
    link = State()


class AdminS(StatesGroup):
    broadcast = State()
    find_user = State()
    give_days = State()
    add_days = State()
    plan_field = State()
    chan_ref = State()
    chan_link = State()


async def cleanup_temp(uid: int) -> None:
    t = TEMP.pop(uid, None)
    if t:
        t["cancel"] = True
        try:
            await t["client"].disconnect()
        except Exception:  # noqa: BLE001
            pass


async def reset(state: FSMContext, uid: int) -> None:
    await state.clear()
    await cleanup_temp(uid)


# ───────────── Foydalanuvchini ro'yxatga olish + referal ─────────────
async def ensure_user(user, text: str | None) -> None:
    row = await get_user(user.id)
    if row:
        if row["username"] != user.username or row["full_name"] != user.full_name:
            await db_exec("UPDATE users SET username=?, full_name=? WHERE id=?", (user.username, user.full_name, user.id))
        return
    ref = None
    if text and text.startswith("/start"):
        parts = text.split(maxsplit=1)
        if len(parts) > 1 and parts[1].startswith("ref") and parts[1][3:].isdigit():
            ref = int(parts[1][3:])
    if ref == user.id or (ref and not await get_user(ref)):
        ref = None
    await db_exec("INSERT INTO users(id,username,full_name,joined) VALUES(?,?,?,?)",
                  (user.id, user.username, user.full_name, time.time()))
    if ref:
        await db_exec("INSERT OR IGNORE INTO referrals(invited_id,referrer_id,created) VALUES(?,?,?)",
                      (user.id, ref, time.time()))
        total = (await db_one("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (ref,)))["c"]
        ru = await get_user(ref)
        avail = max(total - ru["ref_used"], 0)
        await notify_user(ref, f"🎉 Yangi referal qo'shildi! Mavjud: <b>{avail}</b> ta.")
        if any(avail == need for need, _, _ in GIFT_TIERS):
            await notify_user(OWNER_ID, f"🎁 Foydalanuvchi {mention_html(ref, ru['username'], ru['full_name'])} "
                                        f"(<code>{ref}</code>) gift shartini bajardi: <b>{avail}</b> ta referal.")


async def missing_channels(uid: int) -> list:
    chans = await db_all("SELECT * FROM channels")
    miss = []
    for c in chans:
        try:
            cm = await BOT.get_chat_member(c["chat_id"], uid)
            if cm.status in ("left", "kicked"):
                miss.append(c)
        except Exception as e:  # noqa: BLE001
            log.warning("sub check %s: %s", c["chat_id"], e)
    return miss


def sub_kb(miss: list) -> InlineKeyboardMarkup:
    rows = [[(f"📢 {c['title']}", c["link"])] for c in miss if c["link"]]
    rows.append([("✅ Tekshirish", "chk_sub")])
    return ikb(*rows)


SUB_TEXT = "📢 <b>Botdan foydalanish uchun quyidagi kanal(lar)ga a'zo bo'ling</b>, so'ng «✅ Tekshirish» tugmasini bosing:"


class Gate(BaseMiddleware):
    """Ro'yxatga olish, ban tekshiruvi va majburiy obuna."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is None or user.is_bot:
            return await handler(event, data)
        chat = event.chat if isinstance(event, Message) else (event.message.chat if event.message else None)
        if chat is not None and chat.type != "private":
            return None
        await ensure_user(user, event.text if isinstance(event, Message) else None)
        if user.id == OWNER_ID:
            return await handler(event, data)
        row = await get_user(user.id)
        target = event if isinstance(event, Message) else event.message
        if row["banned"]:
            if isinstance(event, CallbackQuery):
                await event.answer("🚫 Siz bloklangansiz.", show_alert=True)
            else:
                await event.answer("🚫 Siz bloklangansiz.")
            return None
        if isinstance(event, CallbackQuery) and event.data == "chk_sub":
            return await handler(event, data)
        miss = await missing_channels(user.id)
        if miss:
            if isinstance(event, CallbackQuery):
                await event.answer()
            await target.answer(SUB_TEXT, reply_markup=sub_kb(miss))
            return None
        return await handler(event, data)


# ───────────── /start, bosh menyu ─────────────
WELCOME = (
    "👋 <b>UTAG botiga xush kelibsiz!</b>\n\n"
    "Bot xizmatlaridan foydalanishni boshlashingiz mumkin.\n\n"
    "👑 Bot egasi: @{owner}\n\n"
    "🚀 <b>Boshlash uchun 3 qadam:</b>\n"
    "1️⃣ <b>Akkaunt ulang:</b> 👤 Akkauntlarim bo'limiga kiring\n"
    "2️⃣ <b>Odam yig'ing:</b> 🧲 Odam yig'ish orqali guruhlardan user yig'ing\n"
    "3️⃣ <b>Mention qiling:</b> guruhda <code>.u</code> buyrug'ini yozing\n\n"
    "⚡ UTAG — Yangi imkoniyatlar sari!\n\n"
    "👇 Kerakli bo'limni pastdagi tugmalardan tanlang"
)


async def send_welcome(m: Message) -> None:
    text = WELCOME.format(owner=OWNER_USERNAME)
    if os.path.exists(LOGO_FILE):
        try:
            await m.answer_photo(FSInputFile(LOGO_FILE), caption=text, reply_markup=main_kb(m.from_user.id))
            return
        except Exception:  # noqa: BLE001
            pass
    await m.answer(text, reply_markup=main_kb(m.from_user.id))


@router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    await send_welcome(m)


@router.message(F.text.in_({B_CANCEL, B_BACK}))
async def go_home(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    await m.answer("🏠 Bosh menyu", reply_markup=main_kb(m.from_user.id))


@router.callback_query(F.data == "chk_sub")
async def cb_chk_sub(cb: CallbackQuery):
    miss = await missing_channels(cb.from_user.id)
    if miss:
        await cb.answer("❌ Hali hammasiga a'zo bo'lmadingiz.", show_alert=True)
        try:
            await cb.message.edit_reply_markup(reply_markup=sub_kb(miss))
        except TelegramBadRequest:
            pass
        return
    await cb.answer("✅ Rahmat!")
    try:
        await cb.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await cb.message.answer("✅ Obuna tasdiqlandi!", reply_markup=main_kb(cb.from_user.id))


# ───────────── Tariflar ─────────────
@router.message(F.text == B_PLANS)
async def show_plans(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    plans = await db_all("SELECT * FROM plans WHERE active=1 ORDER BY sort")
    if not plans:
        await m.answer("Hozircha tariflar mavjud emas.")
        return
    for p in plans:
        if p["price"] == 0:
            kb = ikb([("🎁 Bepul olish", "getfree")])
        else:
            kb = ikb([("💳 Karta orqali to'lov", pay_url(p["title"], m.from_user.id))])
        await m.answer(plan_card(p), reply_markup=kb)


@router.callback_query(F.data == "getfree")
async def cb_getfree(cb: CallbackQuery):
    uid = cb.from_user.id
    p = await get_plan_row("free")
    if not p or not p["active"]:
        await cb.answer("Bepul tarif hozir mavjud emas.", show_alert=True)
        return
    u = await get_user(uid)
    if u["free_used"] and uid != OWNER_ID:
        await cb.answer("⚠️ Bepul tarif faqat bir marta beriladi.", show_alert=True)
        return
    if await get_active_plan(uid) and uid != OWNER_ID:
        await cb.answer("ℹ️ Sizda allaqachon faol tarif bor.", show_alert=True)
        return
    until = await activate_plan(uid, "free", p["days"])
    await db_exec("UPDATE users SET free_used=1 WHERE id=?", (uid,))
    await cb.answer("🎉 Faollashtirildi!")
    await cb.message.answer(f"🎉 Sizning bepul <b>{esc(p['title'])}</b> tarifingiz faollashtirildi!\n"
                            f"⏳ Muddati: {p['days']} kun ({fmt_date(until)} gacha)",
                            reply_markup=main_kb(uid))


# ───────────── Akkauntlar ─────────────
@router.message(F.text == B_ACCS)
async def accounts_menu(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    accs = await db_all("SELECT * FROM accounts WHERE owner_id=? AND status='active'", (m.from_user.id,))
    plan = await get_active_plan(m.from_user.id)
    mx = plan["max_accounts"] if plan else 0
    if not accs:
        txt = "👤 <b>Akkauntlarim</b>\n\n❌ Hozircha akkaunt ulanmagan.\nYangi akkaunt qo'shish uchun pastdagi tugmani bosing."
    else:
        txt = f"👤 <b>Akkauntlarim</b>\n\nUlangan: <b>{len(accs)}/{mx}</b>\nRo'yxat uchun «{B_LIST}» tugmasini bosing."
    await m.answer(txt, reply_markup=acc_kb())


@router.message(F.text == B_LIST)
async def accounts_list(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    accs = await db_all("SELECT * FROM accounts WHERE owner_id=? ORDER BY id", (m.from_user.id,))
    if not accs:
        await m.answer("❌ Hozircha akkaunt ulanmagan.", reply_markup=acc_kb())
        return
    lines = ["📋 <b>Akkauntlarim ro'yxati</b>\n"]
    for i, a in enumerate(accs, 1):
        st = "🟢 faol" if a["status"] == "active" else "🔴 uzilgan"
        un = f"@{a['username']}" if a["username"] else "—"
        lines.append(f"{i}. <b>{esc(a['name'])}</b>\n   📱 {esc(a['phone'])} | {un}\n   {st}")
    await m.answer("\n".join(lines), reply_markup=acc_kb())


@router.message(F.text == B_DEL)
async def accounts_delete_menu(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    accs = await db_all("SELECT * FROM accounts WHERE owner_id=? ORDER BY id", (m.from_user.id,))
    if not accs:
        await m.answer("❌ O'chirish uchun akkaunt yo'q.", reply_markup=acc_kb())
        return
    rows = [[(f"🗑 {a['name']} ({a['phone']})", f"accdel:{a['id']}")] for a in accs]
    await m.answer("Qaysi akkauntni o'chirmoqchisiz?", reply_markup=ikb(*rows))


@router.callback_query(F.data.startswith("accdel:"))
async def accounts_delete_ask(cb: CallbackQuery):
    acc_id = int(cb.data.split(":")[1])
    await cb.answer()
    await cb.message.edit_text("⚠️ Akkaunt o'chirilsin va uning sessiyasi tugatilsinmi?",
                               reply_markup=ikb([("✅ Ha, o'chirish", f"accdok:{acc_id}"), ("↩️ Yo'q", "accdno")]))


@router.callback_query(F.data == "accdno")
async def accounts_delete_no(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("↩️ Bekor qilindi.")


@router.callback_query(F.data.startswith("accdok:"))
async def accounts_delete_do(cb: CallbackQuery):
    acc_id = int(cb.data.split(":")[1])
    acc = await db_one("SELECT * FROM accounts WHERE id=? AND owner_id=?", (acc_id, cb.from_user.id))
    if not acc:
        await cb.answer("Topilmadi.", show_alert=True)
        return
    client = CLIENTS.pop(acc_id, None)
    if client is None and acc["status"] == "active":
        try:
            client = new_client(FERNET.decrypt(acc["session"].encode()).decode())
            await client.connect()
        except Exception:  # noqa: BLE001
            client = None
    if client:
        try:
            await client.log_out()
        except Exception:  # noqa: BLE001
            pass
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    await db_exec("DELETE FROM accounts WHERE id=?", (acc_id,))
    await cb.answer("🗑 O'chirildi")
    await cb.message.edit_text(f"🗑 Akkaunt o'chirildi: {esc(acc['name'])}")


@router.message(F.text == B_ADD)
async def add_account_start(m: Message, state: FSMContext):
    uid = m.from_user.id
    await reset(state, uid)
    plan = await get_active_plan(uid)
    if not plan:
        await m.answer(NO_PLAN_TEXT, reply_markup=no_plan_kb())
        return
    cnt = (await db_one("SELECT COUNT(*) c FROM accounts WHERE owner_id=? AND status='active'", (uid,)))["c"]
    if cnt >= plan["max_accounts"]:
        await m.answer(f"⚠️ Tarifingiz bo'yicha maksimal akkaunt soni: <b>{plan['max_accounts']}</b> ta.\n"
                       f"Ko'proq ulash uchun tarifni oshiring.", reply_markup=acc_kb())
        return
    if not API_ID or not API_HASH:
        await m.answer("⚠️ Bot sozlanmagan (API_ID/API_HASH). Egasiga xabar bering.")
        return
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=B_PHONE), KeyboardButton(text=B_QR)],
                                       [KeyboardButton(text=B_BACK)]], resize_keyboard=True)
    await state.set_state(AddAcc.method)
    await m.answer("🔐 <b>Yangi akkaunt ulash</b>\n\nAkkauntni qaysi usulda ulamoqchisiz?\n\n"
                   "📞 <b>Telefon orqali</b> — telefon raqam va SMS/Telegram kodi bilan\n"
                   "📷 <b>QR kod orqali</b> — telefoningizdan skaner qilib\n\n"
                   "💡 QR kod usuli ayniqsa 2FA (ikki bosqichli himoya) yoqilgan akkauntlar uchun qulay.",
                   reply_markup=kb)


@router.message(AddAcc.method, F.text == B_PHONE)
async def add_method_phone(m: Message, state: FSMContext):
    await state.set_state(AddAcc.phone)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=B_SENDPHONE, request_contact=True)],
                                       [KeyboardButton(text=B_CANCEL)]], resize_keyboard=True)
    await m.answer("📞 <b>Telefon orqali ulash</b>\n\nTelefon raqamingizni xalqaro formatda yuboring.\n"
                   "Masalan: <code>+998901234567</code>\n\nYoki pastdagi tugma orqali raqamingizni yuboring.",
                   reply_markup=kb)


@router.message(AddAcc.phone)
async def add_phone(m: Message, state: FSMContext):
    uid = m.from_user.id
    raw = m.contact.phone_number if m.contact else (m.text or "")
    phone = "+" + re.sub(r"\D", "", raw)
    if len(phone) < 10:
        await m.answer("❌ Raqam noto'g'ri. Masalan: <code>+998901234567</code>")
        return
    wait = await m.answer("⏳ Kod yuborilmoqda...")
    client = new_client()
    try:
        await client.connect()
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        await client.disconnect()
        await wait.edit_text("❌ Telefon raqam noto'g'ri.")
        return
    except PhoneNumberBannedError:
        await client.disconnect()
        await wait.edit_text("🚫 Bu raqam Telegram tomonidan bloklangan.")
        return
    except FloodWaitError as e:
        await client.disconnect()
        await wait.edit_text(f"⏳ Telegram cheklovi: {e.seconds} soniyadan keyin urinib ko'ring.")
        return
    except Exception as e:  # noqa: BLE001
        await client.disconnect()
        log.warning("send_code: %s", e)
        await wait.edit_text("❌ Kod yuborib bo'lmadi. Keyinroq urinib ko'ring.")
        return
    await cleanup_temp(uid)
    TEMP[uid] = dict(client=client, phone=phone, hash=sent.phone_code_hash, cancel=False)
    await state.set_state(AddAcc.code)
    await wait.edit_text(
        f"📨 <b>Kod yuborildi!</b>\n\nTelefon: <code>{esc(phone)}</code>\n\n"
        f"Iltimos, Telegram ilovangizga kelgan <b>5 xonali kodni</b> kiriting.\n\n"
        f"⚠️ <b>Kod formatiga e'tibor bering:</b>\n"
        f"✅ To'g'ri: <code>1-2-3-4-5</code> (chiziqcha bilan)\n"
        f"✅ To'g'ri: <code>1 2 3 4 5</code> (bo'sh joy bilan)\n"
        f"❌ Noto'g'ri: <code>12345</code> (qo'shib yozilgan — Telegram bloklaydi)\n\n"
        f"<i>Bekor qilish uchun pastdagi tugmani bosing.</i>")


@router.message(AddAcc.code)
async def add_code(m: Message, state: FSMContext):
    uid = m.from_user.id
    t = TEMP.get(uid)
    if not t:
        await reset(state, uid)
        await m.answer("⏱ Jarayon eskirgan. Qaytadan boshlang.", reply_markup=acc_kb())
        return
    digits = re.sub(r"\D", "", m.text or "")
    if not 5 <= len(digits) <= 6:
        await m.answer("❌ Kod 5 xonali bo'lishi kerak. Masalan: <code>1-2-3-4-5</code>")
        return
    client: TelegramClient = t["client"]
    try:
        await client.sign_in(phone=t["phone"], code=digits, phone_code_hash=t["hash"])
    except SessionPasswordNeededError:
        await state.set_state(AddAcc.password)
        await m.answer("🔐 <b>Ikki bosqichli himoya paroli</b>\n\nBu akkauntda ikki bosqichli himoya (2FA) yoqilgan.\n\n"
                       "Iltimos, <b>2FA parolingizni</b> kiriting.")
        return
    except PhoneCodeInvalidError:
        await m.answer("❌ Kod noto'g'ri. Qaytadan kiriting.")
        return
    except PhoneCodeExpiredError:
        await reset(state, uid)
        await m.answer("⌛ Kod muddati tugadi. Qaytadan urinib ko'ring.", reply_markup=acc_kb())
        return
    except Exception as e:  # noqa: BLE001
        log.warning("sign_in: %s", e)
        await reset(state, uid)
        await m.answer("❌ Kirishda xatolik. Qaytadan urinib ko'ring.", reply_markup=acc_kb())
        return
    await finish_account(m, state, client)


@router.message(AddAcc.password)
async def add_password(m: Message, state: FSMContext):
    uid = m.from_user.id
    t = TEMP.get(uid)
    if not t:
        await reset(state, uid)
        await m.answer("⏱ Jarayon eskirgan. Qaytadan boshlang.", reply_markup=acc_kb())
        return
    try:
        await m.delete()  # xavfsizlik uchun parol xabarini o'chiramiz
    except Exception:  # noqa: BLE001
        pass
    try:
        await t["client"].sign_in(password=m.text or "")
    except PasswordHashInvalidError:
        await m.answer("❌ Parol noto'g'ri. Qaytadan kiriting.")
        return
    except FloodWaitError as e:
        await m.answer(f"⏳ Telegram cheklovi: {e.seconds} soniya kuting.")
        return
    except Exception as e:  # noqa: BLE001
        log.warning("2fa: %s", e)
        await reset(state, uid)
        await m.answer("❌ Xatolik. Qaytadan urinib ko'ring.", reply_markup=acc_kb())
        return
    await finish_account(m, state, t["client"])


@router.message(AddAcc.method, F.text == B_QR)
async def add_method_qr(m: Message, state: FSMContext):
    uid = m.from_user.id
    try:
        import qrcode  # noqa: WPS433
    except ImportError:
        await m.answer("⚠️ QR kod moduli o'rnatilmagan. Telefon orqali ulang yoki egasiga xabar bering.")
        return
    await cleanup_temp(uid)
    client = new_client()
    await client.connect()
    t = dict(client=client, phone="", cancel=False)
    TEMP[uid] = t
    await m.answer("📷 <b>QR kod orqali ulash</b>\n\nTelefoningizda: <b>Telegram → Sozlamalar → Qurilmalar → "
                   "Qurilma ulash</b> ni oching va QR kodni skaner qiling.", reply_markup=cancel_kb())
    try:
        qr = await client.qr_login()
        for _ in range(4):
            img = qrcode.make(qr.url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            sent = await m.answer_photo(BufferedInputFile(buf.getvalue(), "qr.png"),
                                        caption="⏳ QR kod 1 daqiqa amal qiladi. Skaner qiling...")
            try:
                await qr.wait(timeout=55)
                try:
                    await sent.delete()
                except Exception:  # noqa: BLE001
                    pass
                await finish_account(m, state, client)
                return
            except (asyncio.TimeoutError, TimeoutError):
                try:
                    await sent.delete()
                except Exception:  # noqa: BLE001
                    pass
                if t.get("cancel"):
                    return
                await qr.recreate()
            except SessionPasswordNeededError:
                await state.set_state(AddAcc.password)
                await m.answer("🔐 <b>Ikki bosqichli himoya paroli</b>\n\nIltimos, <b>2FA parolingizni</b> kiriting.")
                return
        await reset(state, uid)
        await m.answer("⌛ QR kod muddati tugadi. Qaytadan urinib ko'ring.", reply_markup=acc_kb())
    except Exception as e:  # noqa: BLE001
        if t.get("cancel"):
            return
        log.warning("qr: %s", e)
        await reset(state, uid)
        await m.answer("❌ QR orqali ulashda xatolik. Telefon orqali urinib ko'ring.", reply_markup=acc_kb())


async def finish_account(m: Message, state: FSMContext, client: TelegramClient) -> None:
    uid = m.from_user.id
    try:
        me = await client.get_me()
        plan = await get_active_plan(uid)
        cnt = (await db_one("SELECT COUNT(*) c FROM accounts WHERE owner_id=? AND status='active'", (uid,)))["c"]
        dup = await db_one("SELECT id FROM accounts WHERE owner_id=? AND tg_id=? AND status='active'", (uid, me.id))
        if dup or not plan or cnt >= plan["max_accounts"]:
            try:
                await client.log_out()
            except Exception:  # noqa: BLE001
                pass
            TEMP.pop(uid, None)
            await state.clear()
            why = "bu akkaunt allaqachon ulangan" if dup else "tarif limiti to'lgan yoki tarif faol emas"
            await m.answer(f"⚠️ Akkaunt ulanmadi: {why}.", reply_markup=acc_kb())
            return
        enc = FERNET.encrypt(client.session.save().encode()).decode()
        name = " ".join(x for x in [me.first_name, me.last_name] if x) or "—"
        phone = "+" + (me.phone or "")
        cur = await db_exec(
            "INSERT INTO accounts(owner_id,phone,tg_id,name,username,session,status,created) VALUES(?,?,?,?,?,?,?,?)",
            (uid, phone, me.id, name, me.username or "", enc, "active", time.time()))
        acc_id = cur.lastrowid
        attach_handlers(client, acc_id, uid)
        CLIENTS[acc_id] = client
        TEMP.pop(uid, None)
        await state.clear()
        await m.answer(
            f"✅ <b>Akkaunt muvaffaqiyatli ulandi!</b>\n\n👤 Ism: <b>{esc(name)}</b>\n📱 Telefon: <code>{esc(phone)}</code>\n"
            f"🆔 ID: <code>{me.id}</code>\n🔗 Username: {('@' + me.username) if me.username else '—'}",
            reply_markup=acc_kb())
        await m.answer("✅ <b>Mention funksiyasi faollashtirildi!</b>\n\n<code>.u</code>, <code>.uo</code> yoki "
                       "<code>.r</code> buyrug'ini istalgan guruhda darhol sinab ko'rishingiz mumkin.")
    except Exception as e:  # noqa: BLE001
        log.exception("finish_account: %s", e)
        await reset(state, uid)
        await m.answer("❌ Akkauntni saqlashda xatolik.", reply_markup=acc_kb())


# ───────────── Odam yig'ish ─────────────
@router.message(F.text == B_SCRAPE)
async def scrape_start(m: Message, state: FSMContext):
    uid = m.from_user.id
    await reset(state, uid)
    plan = await get_active_plan(uid)
    if not plan:
        await m.answer(NO_PLAN_TEXT, reply_markup=no_plan_kb())
        return
    accs = await db_all("SELECT * FROM accounts WHERE owner_id=? AND status='active'", (uid,))
    if not accs:
        await m.answer("❌ <b>Akkaunt ulanmagan!</b>\n\nOdam yig'ish uchun avval 👤 <b>Akkauntlarim</b> bo'limidan "
                       "kamida bitta akkaunt ulashingiz kerak.")
        return
    if plan["scrape_daily"] >= 0:
        sc, _ = await usage_get(uid)
        if sc >= plan["scrape_daily"]:
            await m.answer(f"📈 Kunlik limit tugadi ({sc}/{plan['scrape_daily']}). Ertaga qayta urinib ko'ring yoki tarifni oshiring.")
            return
    if len(accs) == 1:
        await state.update_data(acc_id=accs[0]["id"])
        await state.set_state(Scrape.link)
        await m.answer(SCRAPE_PROMPT, reply_markup=cancel_kb())
        return
    rows = [[(f"{a['name']} ({a['phone']})", f"scacc:{a['id']}")] for a in accs]
    await m.answer("👤 Qaysi akkaunt orqali yig'amiz?", reply_markup=ikb(*rows))


SCRAPE_PROMPT = ("🧲 <b>Odam yig'ish</b>\n\n1️⃣ Guruh linkini yoki @username ni yuboring:\n"
                 "• <code>https://t.me/+AbCdEf...</code>\n• <code>@guruh_nomi</code>\n\n"
                 "ℹ️ Ochiq guruhga akkaunt o'zi kiradi. Yopiq guruh uchun taklif linki kerak.\n"
                 "2️⃣ Keyin rejimni tanlaysiz.")


@router.callback_query(F.data.startswith("scacc:"))
async def scrape_pick_acc(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.update_data(acc_id=int(cb.data.split(":")[1]))
    await state.set_state(Scrape.link)
    await cb.message.answer(SCRAPE_PROMPT, reply_markup=cancel_kb())


@router.message(Scrape.link)
async def scrape_link(m: Message, state: FSMContext):
    link = (m.text or "").strip()
    if len(link) < 4:
        await m.answer("❌ Link noto'g'ri. Qaytadan yuboring.")
        return
    await state.update_data(link=link)
    rows = [[(v, f"scm:{k}")] for k, v in MODES.items()]
    await m.answer("3️⃣ <b>Rejimni tanlang:</b>", reply_markup=ikb(*rows))


@router.callback_query(F.data.startswith("scm:"))
async def scrape_run(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    mode = cb.data.split(":")[1]
    data = await state.get_data()
    if "link" not in data or mode not in MODES:
        await cb.answer("Jarayon eskirgan.", show_alert=True)
        return
    await cb.answer()
    await state.clear()
    msg = await cb.message.edit_text(f"⏳ <b>Yig'ilmoqda...</b>\nRejim: {MODES[mode]}\nBu bir necha daqiqa olishi mumkin.")
    client = await get_client(data["acc_id"])
    if not client:
        await msg.edit_text("❌ Akkaunt ishlamayapti. Qayta ulang.")
        return
    try:
        ent = await resolve_group(client, data["link"])
        users = await scrape_members(client, ent, mode)
    except ScrapeError as e:
        await msg.edit_text(f"❌ {esc(str(e))}")
        return
    except AUTH_ERRORS as e:
        await mark_dead(data["acc_id"], type(e).__name__)
        await msg.edit_text("❌ Akkaunt sessiyasi tugagan. Qayta ulang.")
        return
    except Exception as e:  # noqa: BLE001
        log.warning("scrape: %s", e)
        await msg.edit_text("❌ Yig'ishda xatolik yuz berdi. Keyinroq urinib ko'ring.")
        return
    title = getattr(ent, "title", None) or data["link"]
    cur = await db_exec("INSERT INTO sources(owner_id,title,link,mode,cnt,created) VALUES(?,?,?,?,?,?)",
                        (uid, title, data["link"], mode, len(users), time.time()))
    sid = cur.lastrowid
    await db_many("INSERT OR IGNORE INTO collected(source_id,owner_id,tg_id,username,name) VALUES(?,?,?,?,?)",
                  [(sid, uid, u["id"], u["username"], u["name"]) for u in users])
    await usage_add(uid, scrapes=1)
    plan = await get_active_plan(uid)
    text = (f"✅ <b>Yig'ish tugadi!</b>\n\n📍 Guruh: <b>{esc(title)}</b>\n🎛 Rejim: {MODES[mode]}\n"
            f"👥 Yig'ildi: <b>{len(users)}</b> ta")
    if plan and plan["can_export"]:
        kb = ikb([("⬇️ Yuklab olish", f"exp:{sid}")])
    else:
        text += "\n\n🔒 Yig'ilgan userlarni yuklab olish uchun pullik tarif kerak."
        kb = ikb([("💳 Tarif sotib olish", pay_url("pullik tarif", uid))])
    await msg.edit_text(text, reply_markup=kb)


# ───────────── Yig'ilgan userlar ─────────────
@router.message(F.text == B_COLL)
async def collected_menu(m: Message, state: FSMContext):
    uid = m.from_user.id
    await reset(state, uid)
    srcs = await db_all("SELECT * FROM sources WHERE owner_id=? ORDER BY id DESC LIMIT 20", (uid,))
    if not srcs:
        await m.answer("📁 <b>Yig'ilgan userlar</b>\n\n❌ Hozircha hech qanday user yig'ilmagan.\n\nUser yig'ish uchun:\n"
                       "1️⃣ 🧲 <b>Odam yig'ish</b> bo'limiga kiring\n2️⃣ Guruh linkini yuboring\n3️⃣ Rejimni tanlang")
        return
    total = (await db_one("SELECT COUNT(*) c FROM collected WHERE owner_id=?", (uid,)))["c"]
    lines = [f"📁 <b>Yig'ilgan userlar</b>\n\nJami: <b>{total}</b> ta\n"]
    rows = []
    for i, s in enumerate(srcs, 1):
        lines.append(f"{i}. {esc(s['title'])} — <b>{s['cnt']}</b> ta ({fmt_date(s['created'])})")
        rows.append([(f"⬇️ {i}. {s['title'][:28]} ({s['cnt']})", f"exp:{s['id']}")])
    rows.append([("⬇️ Hammasini yuklab olish", "exp:all")])
    rows.append([("🗑 Hammasini tozalash", "clr:ask")])
    await m.answer("\n".join(lines), reply_markup=ikb(*rows))


@router.callback_query(F.data.startswith("exp:"))
async def export_users(cb: CallbackQuery):
    uid = cb.from_user.id
    plan = await get_active_plan(uid)
    if not plan or not plan["can_export"]:
        await cb.answer("🔒 Yuklab olish faqat pullik tarifda mavjud.", show_alert=True)
        await cb.message.answer("🔒 Yig'ilgan userlarni yuklab olish uchun tarif sotib oling:",
                                reply_markup=ikb([("💳 Karta orqali to'lov", pay_url("pullik tarif", uid))]))
        return
    key = cb.data.split(":")[1]
    if key == "all":
        rows = await db_all("SELECT DISTINCT tg_id, username, name FROM collected WHERE owner_id=?", (uid,))
        fname = "all_users"
    else:
        rows = await db_all("SELECT tg_id, username, name FROM collected WHERE owner_id=? AND source_id=?", (uid, int(key)))
        fname = f"users_{key}"
    if not rows:
        await cb.answer("Bo'sh.", show_alert=True)
        return
    await cb.answer("⏳ Tayyorlanmoqda...")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "username", "name"])
    for r in rows:
        w.writerow([r["tg_id"], r["username"], r["name"]])
    usernames = "\n".join(f"@{r['username']}" for r in rows if r["username"])
    await cb.message.answer_document(BufferedInputFile(buf.getvalue().encode("utf-8-sig"), f"{fname}.csv"),
                                     caption=f"📊 To'liq ro'yxat: {len(rows)} ta")
    if usernames:
        await cb.message.answer_document(BufferedInputFile(usernames.encode("utf-8"), f"{fname}_usernames.txt"),
                                         caption="🔖 Faqat username'lar")


@router.callback_query(F.data == "clr:ask")
async def clear_ask(cb: CallbackQuery):
    await cb.answer()
    await cb.message.edit_text("⚠️ Barcha yig'ilgan userlar o'chirilsinmi?",
                               reply_markup=ikb([("✅ Ha", "clr:ok"), ("↩️ Yo'q", "accdno")]))


@router.callback_query(F.data == "clr:ok")
async def clear_ok(cb: CallbackQuery):
    uid = cb.from_user.id
    await db_exec("DELETE FROM collected WHERE owner_id=?", (uid,))
    await db_exec("DELETE FROM sources WHERE owner_id=?", (uid,))
    await cb.answer("🗑 Tozalandi")
    await cb.message.edit_text("🗑 Yig'ilgan userlar tozalandi.")


# ───────────── Referal ─────────────
@router.message(F.text == B_REF)
async def referral(m: Message, state: FSMContext):
    uid = m.from_user.id
    await reset(state, uid)
    total = (await db_one("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (uid,)))["c"]
    u = await get_user(uid)
    used = u["ref_used"]
    avail = max(total - used, 0)
    link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    await m.answer(f"🔗 <b>Referal tizimi</b>\n\nDo'stlaringizni taklif qiling va bonuslarga ega bo'ling!\n\n"
                   f"<b>Sizning shaxsiy linkingiz:</b>\n<code>{link}</code>\n(ustiga bosing, nusxalanadi)\n\n"
                   f"📊 <b>Statistika:</b>\n• Jami takliflar: {total} ta\n• Ishlatilgan: {used} ta\n• Mavjud: {avail} ta")
    for need, title, desc in GIFT_TIERS:
        if avail >= need:
            tail = f"✅ <b>Shart bajarilgan!</b> Giftni olish uchun @{OWNER_USERNAME} ga murojaat qiling."
        else:
            tail = f"⏳ Yana <b>{need - avail}</b> ta referal kerak."
        await m.answer(f"{title}\n\n{desc}\n\n📌 Talab qilinadi: {need} ta referal\n📊 Sizda mavjud: {avail} ta\n\n{tail}")


# ───────────── Statistika / Yordam ─────────────
@router.message(F.text == B_STAT)
async def statistics(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    await m.answer(await stat_text(m.from_user.id))


@router.message(F.text == B_HELP)
async def help_cmd(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    await m.answer(HELP_TEXT)


# ───────────── Sozlamalar (mention) ─────────────
def settings_view(u) -> tuple[str, InlineKeyboardMarkup]:
    on = bool(u["mention_on"])
    d = u["mention_delay"]
    state_txt = "YOQILGAN" if on else "O'CHIRILGAN"
    text = (f"⚙️ <b>MENTION SOZLAMALARI</b>\n\n{'🟢' if on else '🔴'} Holat: <b>{state_txt}</b>\n"
            f"⏱ Tezlik: <b>{d} soniya</b>\n\n<i>Katta guruhlarda bot pauzani avtomatik kattalashtiradi.</i>\n\n"
            f"👇 Kerakli sozlamani tanlang:")
    toggle = ("✅ MENTION YOQILGAN (o'chirish uchun bosing)" if on else "❌ MENTION O'CHIRILGAN (yoqish uchun bosing)")
    row1 = [(("✅ " if d == i else "") + f"{i}s", f"std:{i}") for i in range(1, 6)]
    row2 = [(("✅ " if d == i else "") + f"{i}s", f"std:{i}") for i in range(6, 11)]
    return text, ikb([(toggle, "stt")], [("--- ⏱ TEZLIK (sekund) ---", "noop")], row1, row2,
                     [("📖 Qo'llanmani o'qish", "stg")])


@router.message(F.text == B_SET)
async def settings(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    u = await get_user(m.from_user.id)
    text, kb = settings_view(u)
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data == "noop")
async def cb_noop(cb: CallbackQuery):
    await cb.answer()


@router.callback_query(F.data.in_({"stt"}) | F.data.startswith("std:"))
async def cb_settings(cb: CallbackQuery):
    uid = cb.from_user.id
    if cb.data == "stt":
        await db_exec("UPDATE users SET mention_on=1-mention_on WHERE id=?", (uid,))
    else:
        await db_exec("UPDATE users SET mention_delay=? WHERE id=?", (min(max(int(cb.data.split(":")[1]), 1), 10), uid))
    u = await get_user(uid)
    text, kb = settings_view(u)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await cb.answer("Saqlandi ✅")


@router.callback_query(F.data == "stg")
async def cb_guide(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(GUIDE_TEXT, reply_markup=ikb([("🔙 Sozlamalarga qaytish", "stback")]))


@router.callback_query(F.data == "stback")
async def cb_stback(cb: CallbackQuery):
    await cb.answer()
    u = await get_user(cb.from_user.id)
    text, kb = settings_view(u)
    await cb.message.answer(text, reply_markup=kb)


# ══════════════════════════ OWNER / ADMIN PANEL ══════════════════════════
admin.message.filter(F.from_user.id == OWNER_ID)
admin.callback_query.filter(F.from_user.id == OWNER_ID)

PLAN_FIELDS = {"title": ("Nomi", str), "price": ("Narx (so'm)", int), "days": ("Muddat (kun)", int),
               "max_accounts": ("Maks. akkaunt", int), "scrape_daily": ("Kunlik odam yig'ish (-1 = ∞)", int),
               "mention_daily": ("Kunlik mention (-1 = ∞)", int)}


def admin_home_kb() -> InlineKeyboardMarkup:
    return ikb([("📊 Umumiy statistika", "ad:stats")],
               [("👥 Foydalanuvchilar", "ad:users:0"), ("🔎 User qidirish", "ad:find")],
               [("💰 Tariflar va narxlar", "ad:pl")],
               [("📢 E'lon yuborish", "ad:bc"), ("📌 Majburiy obuna", "ad:ch")],
               [("🎲 Gift o'yini (tasodifiy g'olib)", "ad:gift")],
               [("🛡 Akkauntlar monitoringi", "ad:acc"), ("💾 Backup", "ad:bk")])


@admin.message(F.text == B_ADMIN)
async def admin_open(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    await m.answer("👑 <b>Admin panel</b>", reply_markup=admin_home_kb())


@admin.callback_query(F.data == "ad:home")
async def ad_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text("👑 <b>Admin panel</b>", reply_markup=admin_home_kb())


@admin.callback_query(F.data == "ad:stats")
async def ad_stats(cb: CallbackQuery):
    await cb.answer()
    now = time.time()
    c = lambda sql, a=(): db_one(sql, a)  # noqa: E731
    total = (await c("SELECT COUNT(*) c FROM users"))["c"]
    new_today = (await c("SELECT COUNT(*) c FROM users WHERE joined>?", (now - 86400,)))["c"]
    banned = (await c("SELECT COUNT(*) c FROM users WHERE banned=1"))["c"]
    paid = (await c("SELECT COUNT(*) c FROM users WHERE plan_until>? AND plan_key NOT IN ('free','')", (now,)))["c"]
    free = (await c("SELECT COUNT(*) c FROM users WHERE plan_until>? AND plan_key='free'", (now,)))["c"]
    acc_ok = (await c("SELECT COUNT(*) c FROM accounts WHERE status='active'"))["c"]
    acc_bad = (await c("SELECT COUNT(*) c FROM accounts WHERE status!='active'"))["c"]
    coll = (await c("SELECT COUNT(*) c FROM collected"))["c"]
    ment = (await c("SELECT COALESCE(SUM(mentions),0) s FROM usage WHERE day=?", (today(),)))["s"]
    await cb.message.edit_text(
        f"📊 <b>Umumiy statistika</b>\n\n👥 Userlar: <b>{total}</b> (bugun +{new_today})\n🚫 Bloklangan: {banned}\n"
        f"💳 Pullik tarifdagilar: <b>{paid}</b>\n🎁 Bepul tarifdagilar: {free}\n"
        f"👤 Faol akkauntlar: <b>{acc_ok}</b> | 🔴 o'lgan: {acc_bad}\n📥 Yig'ilgan userlar: {coll}\n"
        f"📣 Bugungi mentionlar: {ment}\n🔌 Ishlayotgan sessiyalar: {len(CLIENTS)}",
        reply_markup=ikb([("🔙 Orqaga", "ad:home")]))


# ── Foydalanuvchilar ──
@admin.callback_query(F.data.startswith("ad:users:"))
async def ad_users(cb: CallbackQuery):
    await cb.answer()
    page = int(cb.data.split(":")[2])
    total = (await db_one("SELECT COUNT(*) c FROM users"))["c"]
    rows = await db_all("SELECT id, username, full_name, banned FROM users ORDER BY joined DESC LIMIT 10 OFFSET ?", (page * 10,))
    btns = [[(f"{'🚫 ' if r['banned'] else ''}{(r['full_name'] or '')[:20]} | {r['id']}", f"ad:u:{r['id']}")] for r in rows]
    nav = []
    if page > 0:
        nav.append(("⬅️", f"ad:users:{page - 1}"))
    if (page + 1) * 10 < total:
        nav.append(("➡️", f"ad:users:{page + 1}"))
    if nav:
        btns.append(nav)
    btns.append([("🔙 Orqaga", "ad:home")])
    await cb.message.edit_text(f"👥 <b>Foydalanuvchilar</b> ({total} ta) — {page + 1}-sahifa", reply_markup=ikb(*btns))


@admin.callback_query(F.data == "ad:find")
async def ad_find(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminS.find_user)
    await cb.message.answer("🔎 User ID yoki @username yuboring:", reply_markup=cancel_kb())


async def user_card(uid: int) -> tuple[str, InlineKeyboardMarkup] | None:
    u = await get_user(uid)
    if not u:
        return None
    plan = await get_plan_row(u["plan_key"]) if u["plan_key"] else None
    active = u["plan_until"] > time.time()
    total_ref = (await db_one("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (uid,)))["c"]
    accs = (await db_one("SELECT COUNT(*) c FROM accounts WHERE owner_id=? AND status='active'", (uid,)))["c"]
    coll = (await db_one("SELECT COUNT(*) c FROM collected WHERE owner_id=?", (uid,)))["c"]
    tar = (f"{esc(plan['title'])} ({fmt_left(u['plan_until'])})" if plan and active else "❌ yo'q")
    text = (f"👤 <b>{esc(u['full_name'] or '—')}</b>\n🆔 <code>{uid}</code> | {('@' + u['username']) if u['username'] else '—'}\n"
            f"📅 Qo'shilgan: {fmt_date(u['joined'])}\n💳 Tarif: {tar}\n👤 Akkauntlar: {accs} | 📥 Yig'ilgan: {coll}\n"
            f"🔗 Referal: {total_ref} (ishlatilgan {u['ref_used']})\n🚫 Ban: {'HA' if u['banned'] else 'yo`q'}")
    kb = ikb([("✅ Unban" if u["banned"] else "🚫 Ban", f"ad:{'unban' if u['banned'] else 'ban'}:{uid}")],
             [("🏷 Tarif berish", f"ad:gp:{uid}"), ("⏱ Kun qo'shish", f"ad:ad:{uid}")],
             [("🚫 Tarifni olish", f"ad:tk:{uid}")],
             [(f"🎁 Gift berildi (-{GIFT_TIERS[0][0]})", f"ad:rg:{uid}:{GIFT_TIERS[0][0]}"),
              (f"🎁 Gift berildi (-{GIFT_TIERS[1][0]})", f"ad:rg:{uid}:{GIFT_TIERS[1][0]}")],
             [("🔙 Orqaga", "ad:users:0")])
    return text, kb


@admin.message(AdminS.find_user)
async def ad_find_do(m: Message, state: FSMContext):
    q = (m.text or "").strip().lstrip("@")
    row = await get_user(int(q)) if q.isdigit() else await db_one("SELECT * FROM users WHERE LOWER(username)=?", (q.lower(),))
    if not row:
        await m.answer("❌ Topilmadi. Qayta yuboring yoki bekor qiling.")
        return
    await state.clear()
    card = await user_card(row["id"])
    await m.answer(card[0], reply_markup=card[1])
    await m.answer("👑", reply_markup=main_kb(OWNER_ID))


@admin.callback_query(F.data.regexp(r"^ad:u:\d+$"))
async def ad_user(cb: CallbackQuery):
    await cb.answer()
    card = await user_card(int(cb.data.split(":")[2]))
    if card:
        await cb.message.edit_text(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:(ban|unban|tk):\d+$"))
async def ad_ban_tk(cb: CallbackQuery):
    _, act, uid = cb.data.split(":")
    uid = int(uid)
    if act == "ban":
        await db_exec("UPDATE users SET banned=1 WHERE id=?", (uid,))
    elif act == "unban":
        await db_exec("UPDATE users SET banned=0 WHERE id=?", (uid,))
    else:
        await db_exec("UPDATE users SET plan_key='', plan_until=0 WHERE id=?", (uid,))
        await notify_user(uid, "ℹ️ Tarifingiz admin tomonidan bekor qilindi.")
    await cb.answer("Bajarildi ✅")
    card = await user_card(uid)
    await cb.message.edit_text(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:rg:\d+:\d+$"))
async def ad_ref_gift(cb: CallbackQuery):
    _, _, uid, n = cb.data.split(":")
    uid, n = int(uid), int(n)
    total = (await db_one("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (uid,)))["c"]
    u = await get_user(uid)
    if total - u["ref_used"] < n:
        await cb.answer("Mavjud referal yetarli emas.", show_alert=True)
        return
    await db_exec("UPDATE users SET ref_used=ref_used+? WHERE id=?", (n, uid))
    await notify_user(uid, "🎁 Referal giftingiz berildi! Rahmat 🙌")
    await cb.answer("✅ Hisobdan yechildi")
    card = await user_card(uid)
    await cb.message.edit_text(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:gp:\d+$"))
async def ad_give_plan(cb: CallbackQuery):
    await cb.answer()
    uid = int(cb.data.split(":")[2])
    plans = await db_all("SELECT * FROM plans ORDER BY sort")
    rows = [[(f"{p['title']} ({p['days']} kun)", f"ad:gpp:{uid}:{p['key']}")] for p in plans]
    rows.append([("🔙 Orqaga", f"ad:u:{uid}")])
    await cb.message.edit_text("🏷 Qaysi tarif berilsin?", reply_markup=ikb(*rows))


@admin.callback_query(F.data.startswith("ad:gpp:"))
async def ad_give_plan2(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    _, _, uid, key = cb.data.split(":")
    p = await get_plan_row(key)
    await state.set_state(AdminS.give_days)
    await state.update_data(uid=int(uid), key=key)
    await cb.message.answer(f"⏱ <b>{esc(p['title'])}</b> necha kunga berilsin?\n"
                            f"Standart: <b>{p['days']}</b> kun. Raqam yuboring (yoki <code>0</code> = standart).",
                            reply_markup=cancel_kb())


@admin.message(AdminS.give_days)
async def ad_give_days(m: Message, state: FSMContext):
    if not (m.text or "").strip().lstrip("-").isdigit():
        await m.answer("❌ Raqam yuboring.")
        return
    d = await state.get_data()
    await state.clear()
    p = await get_plan_row(d["key"])
    days = int(m.text) or p["days"]
    until = await activate_plan(d["uid"], d["key"], days)
    await notify_user(d["uid"], f"🎉 Sizga <b>{esc(p['title'])}</b> tarifi berildi!\n⏳ {days} kun ({fmt_date(until)} gacha)")
    card = await user_card(d["uid"])
    await m.answer(f"✅ Tarif berildi: {esc(p['title'])} — {days} kun", reply_markup=main_kb(OWNER_ID))
    await m.answer(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:ad:\d+$"))
async def ad_add_days(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminS.add_days)
    await state.update_data(uid=int(cb.data.split(":")[2]))
    await cb.message.answer("⏱ Necha kun qo'shilsin? (manfiy son ayiradi)", reply_markup=cancel_kb())


@admin.message(AdminS.add_days)
async def ad_add_days_do(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t.lstrip("-").isdigit():
        await m.answer("❌ Raqam yuboring.")
        return
    d = await state.get_data()
    await state.clear()
    u = await get_user(d["uid"])
    base = max(u["plan_until"], time.time())
    await db_exec("UPDATE users SET plan_until=?, exp_notified=0 WHERE id=?", (base + int(t) * 86400, d["uid"]))
    if int(t) > 0:
        await notify_user(d["uid"], f"⏱ Tarifingizga <b>{int(t)}</b> kun qo'shildi.")
    card = await user_card(d["uid"])
    await m.answer("✅ Bajarildi", reply_markup=main_kb(OWNER_ID))
    await m.answer(card[0], reply_markup=card[1])


# ── Tariflar ──
@admin.callback_query(F.data == "ad:pl")
async def ad_plans(cb: CallbackQuery):
    await cb.answer()
    plans = await db_all("SELECT * FROM plans ORDER BY sort")
    rows = [[(f"{'✅' if p['active'] else '⛔'} {p['title']} — {p['price']} so'm", f"ad:pls:{p['key']}")] for p in plans]
    rows.append([("🔙 Orqaga", "ad:home")])
    await cb.message.edit_text("💰 <b>Tariflar</b> (tahrirlash uchun tanlang):", reply_markup=ikb(*rows))


async def plan_edit_view(key: str):
    p = await get_plan_row(key)
    rows = [[(f"✏️ {lbl}", f"ad:pe:{key}:{f}")] for f, (lbl, _) in PLAN_FIELDS.items()]
    rows.append([(f"📥 Yuklab olish: {yn(p['can_export'])} (almashtirish)", f"ad:pt:{key}:can_export")])
    rows.append([(f"🔌 Faol: {yn(p['active'])} (almashtirish)", f"ad:pt:{key}:active")])
    rows.append([("🔙 Orqaga", "ad:pl")])
    return plan_card(p), ikb(*rows)


@admin.callback_query(F.data.startswith("ad:pls:"))
async def ad_plan_view(cb: CallbackQuery):
    await cb.answer()
    text, kb = await plan_edit_view(cb.data.split(":")[2])
    await cb.message.edit_text(text, reply_markup=kb)


@admin.callback_query(F.data.startswith("ad:pt:"))
async def ad_plan_toggle(cb: CallbackQuery):
    _, _, key, field = cb.data.split(":")
    if field not in ("can_export", "active"):
        return
    await db_exec(f"UPDATE plans SET {field}=1-{field} WHERE key=?", (key,))
    await cb.answer("Saqlandi ✅")
    text, kb = await plan_edit_view(key)
    await cb.message.edit_text(text, reply_markup=kb)


@admin.callback_query(F.data.startswith("ad:pe:"))
async def ad_plan_edit(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    _, _, key, field = cb.data.split(":")
    if field not in PLAN_FIELDS:
        return
    await state.set_state(AdminS.plan_field)
    await state.update_data(key=key, field=field)
    await cb.message.answer(f"✏️ <b>{PLAN_FIELDS[field][0]}</b> uchun yangi qiymatni yuboring:", reply_markup=cancel_kb())


@admin.message(AdminS.plan_field)
async def ad_plan_edit_do(m: Message, state: FSMContext):
    d = await state.get_data()
    field = d["field"]
    typ = PLAN_FIELDS[field][1]
    val = (m.text or "").strip()
    try:
        v = typ(val)
    except ValueError:
        await m.answer("❌ Qiymat noto'g'ri.")
        return
    await state.clear()
    await db_exec(f"UPDATE plans SET {field}=? WHERE key=?", (v, d["key"]))
    text, kb = await plan_edit_view(d["key"])
    await m.answer("✅ Saqlandi", reply_markup=main_kb(OWNER_ID))
    await m.answer(text, reply_markup=kb)


# ── E'lon ──
@admin.callback_query(F.data == "ad:bc")
async def ad_bc(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminS.broadcast)
    await cb.message.answer("📢 Hammaga yuboriladigan xabarni yuboring (matn, rasm, video — istalgani):", reply_markup=cancel_kb())


@admin.message(AdminS.broadcast)
async def ad_bc_msg(m: Message, state: FSMContext):
    await state.clear()
    n = (await db_one("SELECT COUNT(*) c FROM users WHERE banned=0"))["c"]
    await m.answer(f"👆 Shu xabar <b>{n}</b> ta foydalanuvchiga yuborilsinmi?",
                   reply_markup=ikb([("✅ Yuborish", f"ad:bcgo:{m.message_id}"), ("❌ Bekor", "ad:home")]))
    await m.answer("👑", reply_markup=main_kb(OWNER_ID))


async def send_all(owner_chat: int, fn) -> tuple[int, int]:
    ids = [r["id"] for r in await db_all("SELECT id FROM users WHERE banned=0")]
    ok = fail = 0
    for uid in ids:
        try:
            await fn(uid)
            ok += 1
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await fn(uid)
                ok += 1
            except Exception:  # noqa: BLE001
                fail += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            fail += 1
        except Exception:  # noqa: BLE001
            fail += 1
        await asyncio.sleep(0.05)
    return ok, fail


@admin.callback_query(F.data.startswith("ad:bcgo:"))
async def ad_bc_go(cb: CallbackQuery):
    mid = int(cb.data.split(":")[2])
    await cb.answer("Yuborilmoqda...")
    await cb.message.edit_text("⏳ Yuborilmoqda...")

    async def job():
        ok, fail = await send_all(cb.from_user.id, lambda uid: BOT.copy_message(uid, cb.from_user.id, mid))
        await notify_user(OWNER_ID, f"📢 E'lon yakunlandi: ✅ {ok} | ❌ {fail}")
    spawn(job())


# ── Majburiy obuna ──
async def show_channels(cb: CallbackQuery) -> None:
    chans = await db_all("SELECT * FROM channels")
    rows = [[(f"🗑 {c['title']}", f"ad:chd:{c['chat_id']}")] for c in chans]
    rows.append([("➕ Kanal qo'shish", "ad:cha")])
    rows.append([("🔙 Orqaga", "ad:home")])
    txt = "📌 <b>Majburiy obuna kanallari</b>\n\n" + ("\n".join(f"• {esc(c['title'])}" for c in chans) or "Hozircha yo'q.")
    await cb.message.edit_text(txt + "\n\n<i>Bot kanalda ADMIN bo'lishi shart.</i>", reply_markup=ikb(*rows))


@admin.callback_query(F.data == "ad:ch")
async def ad_channels(cb: CallbackQuery):
    await cb.answer()
    await show_channels(cb)


@admin.callback_query(F.data == "ad:cha")
async def ad_chan_add(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminS.chan_ref)
    await cb.message.answer("📌 Kanal <b>@username</b>, havola yoki <b>-100...</b> ID sini yuboring:\n"
                            "(bot avval shu kanalga admin qilingan bo'lsin)", reply_markup=cancel_kb())


@admin.message(AdminS.chan_ref)
async def ad_chan_ref(m: Message, state: FSMContext):
    ref = (m.text or "").strip()
    mm = re.search(r"t\.me/([A-Za-z]\w{3,})", ref)
    if mm:
        ref = "@" + mm.group(1)
    elif re.match(r"^[A-Za-z]\w{3,}$", ref):
        ref = "@" + ref
    elif re.match(r"^-?\d+$", ref):
        ref = int(ref)
    try:
        chat = await BOT.get_chat(ref)
        me = await BOT.get_chat_member(chat.id, BOT.id)
        if me.status not in ("administrator", "creator"):
            await m.answer("❌ Bot bu kanalda admin emas. Avval admin qiling va qayta yuboring.")
            return
    except Exception as e:  # noqa: BLE001
        await m.answer(f"❌ Kanal topilmadi yoki bot kira olmaydi: {esc(str(e))[:120]}")
        return
    if chat.username:
        await db_exec("INSERT OR REPLACE INTO channels(chat_id,title,link) VALUES(?,?,?)",
                      (chat.id, chat.title or chat.username, f"https://t.me/{chat.username}"))
        await state.clear()
        await m.answer(f"✅ Qo'shildi: {esc(chat.title or '')}", reply_markup=main_kb(OWNER_ID))
        return
    await state.set_state(AdminS.chan_link)
    await state.update_data(chat_id=chat.id, title=chat.title or "Kanal")
    await m.answer("🔗 Bu yopiq kanal. Foydalanuvchilar uchun <b>taklif havolasini</b> yuboring (https://t.me/+...):")


@admin.message(AdminS.chan_link)
async def ad_chan_link(m: Message, state: FSMContext):
    link = (m.text or "").strip()
    if not link.startswith("https://t.me/"):
        await m.answer("❌ Havola https://t.me/ bilan boshlanishi kerak.")
        return
    d = await state.get_data()
    await state.clear()
    await db_exec("INSERT OR REPLACE INTO channels(chat_id,title,link) VALUES(?,?,?)", (d["chat_id"], d["title"], link))
    await m.answer(f"✅ Qo'shildi: {esc(d['title'])}", reply_markup=main_kb(OWNER_ID))


@admin.callback_query(F.data.startswith("ad:chd:"))
async def ad_chan_del(cb: CallbackQuery):
    await db_exec("DELETE FROM channels WHERE chat_id=?", (int(cb.data.split(":")[2]),))
    await cb.answer("🗑 O'chirildi")
    await show_channels(cb)


# ── Gift o'yini ──
@admin.callback_query(F.data == "ad:gift")
async def ad_gift(cb: CallbackQuery):
    await cb.answer()
    r = await db_one("SELECT id, username, full_name FROM users WHERE banned=0 AND id!=? ORDER BY RANDOM() LIMIT 1", (OWNER_ID,))
    if not r:
        await cb.message.answer("Foydalanuvchi yo'q.")
        return
    mn = mention_html(r["id"], r["username"], r["full_name"])
    await cb.message.answer(
        f"🎲 <b>Tasodifiy g'olib tanlandi!</b>\n\n🏆 {mn}\n🆔 <code>{r['id']}</code> | {esc(r['full_name'] or '')}\n\n"
        f"Giftni o'zingiz qo'lda berasiz.",
        reply_markup=ikb([("🔄 Qayta tanlash", "ad:gift")],
                         [("✉️ G'olibga xabar yuborish", f"ad:gdm:{r['id']}")],
                         [("📢 Hammaga e'lon qilish", f"ad:gann:{r['id']}")]))


@admin.callback_query(F.data.startswith("ad:gdm:"))
async def ad_gift_dm(cb: CallbackQuery):
    uid = int(cb.data.split(":")[2])
    await notify_user(uid, "🎉 <b>Tabriklaymiz!</b> Siz gift o'yinida g'olib bo'ldingiz!\n"
                           f"Sovg'angizni olish uchun @{OWNER_USERNAME} bilan bog'laning 🎁")
    await cb.answer("✅ Yuborildi", show_alert=True)


@admin.callback_query(F.data.startswith("ad:gann:"))
async def ad_gift_ann(cb: CallbackQuery):
    uid = int(cb.data.split(":")[2])
    r = await get_user(uid)
    mn = mention_html(uid, r["username"], r["full_name"])
    text = f"🎁 <b>Gift o'yini g'olibi:</b> {mn}\n\n🎉 Tabriklaymiz!"
    await cb.answer("Yuborilmoqda...")

    async def job():
        ok, fail = await send_all(cb.from_user.id, lambda x: BOT.send_message(x, text))
        await notify_user(OWNER_ID, f"📢 G'olib e'loni yakunlandi: ✅ {ok} | ❌ {fail}")
    spawn(job())


# ── Akkauntlar monitoringi / backup ──
@admin.callback_query(F.data == "ad:acc")
async def ad_accs(cb: CallbackQuery):
    await cb.answer()
    act = (await db_one("SELECT COUNT(*) c FROM accounts WHERE status='active'"))["c"]
    dead = await db_all("SELECT * FROM accounts WHERE status!='active' ORDER BY id DESC LIMIT 15")
    txt = f"🛡 <b>Akkauntlar monitoringi</b>\n\n🟢 Faol: {act}\n🔌 Ulangan sessiyalar: {len(CLIENTS)}\n🔴 O'lgan: {len(dead)}\n"
    for a in dead:
        txt += f"\n• {esc(a['name'])} {esc(a['phone'])} (user <code>{a['owner_id']}</code>)"
    await cb.message.edit_text(txt, reply_markup=ikb([("🔄 Hammasini tekshirish", "ad:acchk")], [("🔙 Orqaga", "ad:home")]))


@admin.callback_query(F.data == "ad:acchk")
async def ad_accs_check(cb: CallbackQuery):
    await cb.answer("Tekshirilmoqda...")
    ok, dead = await health_check()
    await cb.message.answer(f"🔄 Tekshiruv tugadi: ✅ {ok} | 🔴 yangi o'lgan {dead}")


async def send_backup(chat_id: int) -> None:
    await DB.commit()
    tmp = DB_PATH + ".bak"
    shutil.copyfile(DB_PATH, tmp)
    await BOT.send_document(chat_id, FSInputFile(tmp, filename=f"utag_backup_{datetime.now(TZ):%Y%m%d_%H%M}.db"),
                            caption="💾 Baza zaxirasi (.utag_key faylini ham saqlab qo'ying!)")
    os.remove(tmp)


@admin.callback_query(F.data == "ad:bk")
async def ad_backup(cb: CallbackQuery):
    await cb.answer()
    await send_backup(cb.from_user.id)


# ══════════════════════════ XATOLAR / FON ISHLARI ══════════════════════════
_last_err = 0.0


@router.error()
async def on_error(event: ErrorEvent):
    global _last_err
    log.exception("Handler xatosi: %s", event.exception)
    if time.time() - _last_err > 30:
        _last_err = time.time()
        await notify_user(OWNER_ID, f"⚠️ <b>Bot xatosi:</b> <code>{esc(type(event.exception).__name__)}: "
                                    f"{esc(str(event.exception))[:300]}</code>")


async def maintenance_loop() -> None:
    last_backup = time.time()
    last_health = time.time()
    while True:
        await asyncio.sleep(1800)
        try:
            now = time.time()
            rows = await db_all("SELECT id, plan_key, plan_until, exp_notified FROM users WHERE plan_key!='' AND plan_until>0")
            for r in rows:
                if r["id"] == OWNER_ID:
                    continue
                left = r["plan_until"] - now
                if left <= 0 and r["exp_notified"] < 2:
                    await db_exec("UPDATE users SET exp_notified=2 WHERE id=?", (r["id"],))
                    await notify_user(r["id"], "⌛ <b>Tarifingiz muddati tugadi.</b>\n«💳 Tarif sotib olish» bo'limidan yangilang.")
                elif 0 < left <= 86400 and r["exp_notified"] < 1:
                    await db_exec("UPDATE users SET exp_notified=1 WHERE id=?", (r["id"],))
                    await notify_user(r["id"], "⏰ Tarifingiz <b>24 soatdan kam</b> vaqtda tugaydi.")
            if now - last_health > 10800:
                last_health = now
                await health_check()
            if now - last_backup > 86400:
                last_backup = now
                await send_backup(OWNER_ID)
        except Exception as e:  # noqa: BLE001
            log.warning("maintenance: %s", e)


async def main() -> None:
    global BOT, BOT_USERNAME
    missing = [k for k, v in dict(BOT_TOKEN=BOT_TOKEN, API_ID=API_ID, API_HASH=API_HASH, OWNER_ID=OWNER_ID).items() if not v]
    if missing:
        raise SystemExit(f"❌ Sozlanmagan: {', '.join(missing)}  (.env faylni to'ldiring)")
    await init_db()
    BOT = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    BOT_USERNAME = (await BOT.get_me()).username or ""
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(Gate())
    dp.callback_query.outer_middleware(Gate())
    dp.include_router(router)
    dp.include_router(admin)

    accs = await db_all("SELECT * FROM accounts WHERE status='active'")
    ok = 0
    for a in accs:
        if await start_account(a):
            ok += 1
        await asyncio.sleep(0.5)
    log.info("Bot @%s ishga tushdi. Akkauntlar: %s/%s", BOT_USERNAME, ok, len(accs))
    spawn(maintenance_loop())
    await BOT.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(BOT, allowed_updates=dp.resolve_used_update_types())
    finally:
        for cl in CLIENTS.values():
            try:
                await cl.disconnect()
            except Exception:  # noqa: BLE001
                pass
        await DB.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
