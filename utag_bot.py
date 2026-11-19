#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║  DARK UTAG BOT  —  bitta faylli to'liq loyiha                ║
║  aiogram 3 (bot) + Telethon (userbot) + SQLite               ║
╚══════════════════════════════════════════════════════════════╝

O'RNATISH
    pip install "aiogram>=3.10" "telethon>=1.34" aiosqlite cryptography "qrcode[pil]"

SOZLASH  (shu papkada .env fayl yarating yoki muhit o'zgaruvchisi qilib bering)
    BOT_TOKEN=123456:ABC...          # @BotFather dan
    API_ID=1234567                   # https://my.telegram.org dan
    API_HASH=abcdef0123456789...     # https://my.telegram.org dan
    OWNER_USERNAME=Mirkamilovic      # bot egasi. U botga /start bosganda ega avtomatik biriktiriladi
    # OWNER_ID kerak emas (env dagi eski OWNER_ID e'tiborga olinmaydi)
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
import copy
from collections import Counter
import csv
import html
import io
import json
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
from aiogram.filters import Command, CommandStart  # noqa: E402
from aiogram.fsm.context import FSMContext  # noqa: E402
from aiogram.fsm.state import State, StatesGroup  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.types import (  # noqa: E402
    BotCommand, BufferedInputFile, CallbackQuery, ErrorEvent, FSInputFile, InlineKeyboardButton,
    InlineKeyboardMarkup, KeyboardButton, Message, ReactionTypeEmoji, ReplyKeyboardMarkup,
)

from telethon import TelegramClient, events, types as tl_types, utils as tl_utils  # noqa: E402
from telethon.errors import (  # noqa: E402
    AuthKeyUnregisteredError, ChannelPrivateError, ChatAdminRequiredError, ChatWriteForbiddenError,
    FloodWaitError, InviteHashExpiredError, InviteHashInvalidError, PasswordHashInvalidError,
    PhoneCodeExpiredError, PhoneCodeInvalidError, PhoneNumberBannedError, PhoneNumberInvalidError,
    SessionExpiredError, SessionPasswordNeededError, SessionRevokedError, SlowModeWaitError,
    UserBannedInChannelError, UserDeactivatedBanError, UserDeactivatedError,
    UsernameInvalidError, UsernameNotOccupiedError, PeerFloodError, UserPrivacyRestrictedError,
    UserIsBlockedError, InputUserDeactivatedError,
)
from telethon.sessions import StringSession  # noqa: E402
from telethon.tl.functions.account import UpdateProfileRequest  # noqa: E402
from telethon.tl.functions.channels import EditAdminRequest, JoinChannelRequest  # noqa: E402
from telethon.tl.functions.users import GetFullUserRequest  # noqa: E402
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest  # noqa: E402
from telethon.tl.types import (  # noqa: E402
    Channel, ChannelParticipantsAdmins, ChatInviteAlready, User, UserStatusLastMonth, UserStatusLastWeek,
    UserStatusOffline, UserStatusOnline, UserStatusRecently,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("utag")

# ══════════════════════════ SOZLAMALAR ══════════════════════════
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "").strip()
OWNER_ID = 0   # bazadan yuklanadi (egasi @OWNER_USERNAME birinchi /start bosganda avtomatik biriktiriladi)
OWNER_USERNAME = (os.getenv("OWNER_USERNAME", "Mirkamilovic") or "Mirkamilovic").lstrip("@")
ADMINS: set[int] = set()   # yordamchi adminlar (panel orqali boshqariladi)
def _resolve_db_path() -> str:
    """DB_PATH ni tekshiradi: papka yo'q bo'lsa yaratadi, yozib bo'lmasa joriy papkaga qaytadi."""
    raw = (os.getenv("DB_PATH", "") or "").strip().strip('"').strip("'") or "utag.db"
    raw = os.path.abspath(raw)
    if os.path.isdir(raw):  # DB_PATH papka nomi bo'lib qolgan bo'lsa
        raw = os.path.join(raw, "utag.db")
    folder = os.path.dirname(raw)
    try:
        os.makedirs(folder, exist_ok=True)
        probe = os.path.join(folder, ".write_test")
        with open(probe, "w") as _f:
            _f.write("ok")
        os.remove(probe)
        return raw
    except OSError as e:
        fallback = os.path.abspath("utag.db")
        print(f"[DB] '{raw}' ochilmadi ({e}). Vaqtincha '{fallback}' ishlatiladi. "
              f"Doimiy saqlash uchun Railway Volume ulang.", flush=True)
        return fallback


DB_PATH = _resolve_db_path()
KEY_FILE = os.path.join(os.path.dirname(DB_PATH), ".utag_key")
LOGO_FILE = "logo.jpg"
TURBO_DELAY = 0.3                                                     # standart tezlik: 0.3 soniyada bitta utag
MAX_SCRAPE = int(os.getenv("MAX_SCRAPE", "20000"))                  # bir marta yig'iladigan maks. user
MAX_MENTION_MEMBERS = int(os.getenv("MAX_MENTION_MEMBERS", "5000"))  # bir marta mention qilinadigan maks. a'zo
SCAN_MESSAGES = int(os.getenv("SCAN_MESSAGES", "4000"))              # a'zo yetmasa, nechta oxirgi xabar mualliflari tekshiriladi
TZ = timezone(timedelta(hours=5))                                    # Toshkent vaqti
BOT_USERNAME = ""
BOT: Bot = None  # type: ignore

GIFT_TIERS = [
    (8, "🎁 <b>Gift 15 talik</b>", "Do'stlaringizni taklif qiling va 15 talik giftni yutib oling!"),
    (20, "🎁 <b>Katta gift</b>", "Do'stlaringizni taklif qiling va katta giftga ega bo'ling!"),
]

# ══════════════════════════ GAPLAR BAZASI (1-tur: .r) ══════════════════════════
# Har bir toifada bitta qatorga bitta gap (inson yozgandek, jonli gaplar).
# Foydalanish:  .r  (hammasi)   |   .r #hazil #salom  (tanlangan toifalar)   |   .r gap1 | gap2  (o'z gaplaringiz)
_PHRASE_SRC: dict[str, str] = {
    "salom": """
assalomu alaykum, tirikmisiz o'zi?
oo kim keldi, salom salom
salom jigar, nima gaplar
assalom, ko'rinmay ketding-ku
hay salom, o'lib qoldingmi deb turgandim
salom, kayfiyat qalay bugun
assalomu alaykum, uxlab yotganmidingiz?
yaxshimisiz, uyda hamma tinchmi
salom, bir ovoz bering, eshitaylik
ha salom, qayerlarda yuribsiz
oo salom, sizni sog'indik rostdan
assalomu alaykum, ishlar zo'rmi
salom-salom, choy ichdingizmi
yo'q desangiz ham salom beraman, salom
qalaysan, tinchmisan
salom, bugun kimning kuni ekan
assalom, guruhdan qochib yuribsiz shekilli
hoy salom, jimgina o'tib ketmoqchimidingiz
salom, ismingizni ko'rib yuzimga kulgi keldi
assalomu alaykum, yangiliklar bormi
salom, tirikligingizni bilib xursand bo'ldim
oo, mana kim ekan, salom
salom, tushdan oldin uyg'ondingizmi
assalom, hammasi joyidami
salom opa-singil, aka-uka, hammaga salom
""",
    "savol": """
qayerdasiz o'zi, darak yo'q
nima qilyapsiz hozir, rostini ayting
uxlayapsizmi yoki jim turibsizmi
bugun nima yedingiz, aytmasangiz ham bo'ladi
hozir telefonni qo'lingizda ushlab o'tiribsizmi
ovqat qildingizmi yoki yana yeb qo'ya qoldingizmi
bugun nechta choy ichdingiz
nega javob bermayapsiz, ko'rdingiz-ku
eng so'nggi marta qachon kuldingiz
kechasi nechada yotdingiz
bugun ishga bordingizmi yoki o'qishga
hozir qaysi qo'shiqni eshityapsiz
biror yangi gap bormi o'zi
bugun kimni eslab o'tirdingiz
choy yaxshi ko'rasizmi yoki qahva
sizda ob-havo qanaqa, bizda sovuq
hafta oxiri nima qilasiz
hozir bo'shmisiz, bir gap bor edi
qaysi serialni ko'ryapsiz bu kunlarda
telefon zaryadi nechchi foizda
eng yaxshi ko'rgan ovqatingiz nima, rostini ayting
bugun yomg'ir yog'dimi sizda
nega jimsiz, tilingizni yutib yubordingizmi
ertalab nechida turdingiz
hozir kayfiyatingiz nechi foiz
""",
    "hazil": """
javob bermasangiz telefonimni uloqtiraman
yozmasangiz, mushukimni sizga yuboraman
bugun hamma kulishi shart, vahima qilmang
jim yursangiz sizni sudga beraman
tirikmisiz, tirik bo'lsangiz stiker tashlang
choy sovib qoldi, siz esa hali yo'qsiz
guruhning yarmi uxlab yotibdi, siz ham shundaymi
sizsiz guruh yarim kasalxona kabi tinch
kim kulmasa o'sha yomon ko'rinadi
ko'zim yo'lda qoldi, javob yozing endi
yozing, men baribir kutaman, kutish menga tekin
bunaqa jim yursangiz, men ko'cha mushukiga gapirib qo'yaman
bir og'iz yozing, chiqib ketmaysiz-ku
internetingiz tugadimi yoki bizdan zerikdingizmi
jim turish pulli bo'lsa, boyib ketardingiz
telefon sizda, javob esa menda yo'q, qiziq
men gapiraman, siz esa jimgina o'qiysiz, a?
hech bo'lmasa bitta emoji tashlang, jonim
sizni ko'rib turibman, onlayn ekansiz
ko'rdi qilib qo'yib javob bermaslik jinoyat
oyoqlarim uyushib ketdi, kutib o'tirib
bugun kulmasangiz ertaga ikki barobar kulasiz
yaxshi gap yozmasangiz ham mayli, shunchaki bosib qo'ying
qo'rqmang, tishlamayman, javob bering
bu xabarni o'qiyotganingizni bilaman
""",
    "motiv": """
bugun boshlamasang ertaga ham boshlamaysan, yur harakat qil
hammasi yaxshi bo'ladi, faqat qo'lni qovushtirib o'tirma
kechagi sen bilan bugungi sen o'rtasida farq bo'lsin
charchagan bo'lsang dam ol, lekin taslim bo'lma
kichkina qadam ham qadam, to'xtab qolma
senga ishongan odam bor, shuni unutma
qiyin bo'lsa, demak to'g'ri yo'ldasan
bugun yomon bo'ldimi, ertaga yangi kun bor
o'zing uchun harakat qil, boshqalar keyin
oz-ozdan ham katta bo'ladi, sabr qil
qo'rqsang ham qil, qo'rquv o'tib ketadi
hamma kuchli emas tug'ilmaydi, o'rganiladi
orzu qilishdan charchama, qilgan odam yetadi
bugun bir ish bitirsang, kech yotsang ham yengil bo'ladi
o'zingni boshqalarga solishtirma, sening yo'ling boshqa
xato qilding, bo'ldi, o'rgandingmi, demak yutding
yaxshi niyat qil, qolganini vaqt hal qiladi
yiqilsang turasan, turmasang esa yotib qolasan, tur
boshingga tushsa ham, boshing baland bo'lsin
bir kun kelib shu kunlarga kulib qaraysan
sen o'ylagandan kuchlisan, shunchaki bilmaysan
rizq ham, baxt ham harakat qilgan odamga keladi
kechiktirma, kech bo'lib qolmasin
bugun nima qilsang, ertaga o'sha bo'lasan
ishon, hammasi o'z o'rniga tushadi
""",
    "oyin": """
mafiyada joy bor, qani kiring
o'yin boshlanyapti, siz yo'qsiz hali
bugun mafiya bo'lasizmi yoki tinch aholi
bir partiya o'ynaymizmi, zerikdim
kim mafiyaligini topish juda qiziq, kelasizmi
o'yinda odam yetishmayapti, yordam bering
ro'yxatdan o'tmagan odam o'yinga kirolmaydi, tez
kel, bugun senga komissar rolini beramiz
o'yin sensiz boshlanmaydi, to'liq bo'lsin
kechagi g'olib bugun yutadimi, ko'ramiz
mafiya bo'lsang ham sezdirma, shunga qiziq
bir o'yin o'ynaysiz, keyin to'xtay olmaysiz
qani, kim shifokor bo'ladi bugun
o'yinda yolg'on gapirish mumkin, hayotda emas
raqiblar tayyor, siz-chi
bitta tugma bosasiz xolos, o'yin shu
o'yinga kirsang, kulgu kafolatlangan
bugun kimni ovoz berib chiqaramiz, qiziq
joylar to'lib qoldi, shoshiling
senga yaxshi rol tushsa, hamma kuyib qoladi
bu o'yinda ishongan odam adashadi, kel sinab ko'r
do'stlaringni ham ol, birga o'ynaymiz
kechasi kim kimni o'ldirdi, tong bilan bilamiz
o'yinga kir, keyin gaplashamiz
""",
    "choy": """
choy damladim, siz ham keling
choy sovib qoldi, qaynatib bering desam kimga
nonushta qildingizmi yoki yana quruq choy
osh pishirsam kelarmidingiz
bugun nima yeymiz, maslahat bering
choy bilan shirinlik bo'lsa boshqa nima kerak
qaymoqli non bilan choy, orzu emasmi
issiq sho'rva bugun juda mos tushardi
mehmon kelsa choy tayyor, siz ham mehmonsiz
kechki ovqatga nima qilyapsiz, hidi bu yergacha keldi
samsa yegim keldi, kim olib keladi
non uzdim, endi gap boshlasak bo'ladi
choyni qand bilan ichasizmi yoki qandsizmi
palov desa hammaning ko'zi yonadi, to'g'rimi
mazali taom pishirgan odamga ham salom
ovqat yedingizmi o'zi, aytmasangiz bilmayman
tushlikka nima bo'ldi, hamma ovqat haqida jim
issiq non, qaynoq choy, yana nima kerak
bugun qovurdoq qilsam bo'ladimi
shirinlik yeb turing, kayfiyat yaxshi bo'ladi
choyga limon solib ko'ring, bir hovuch xursandchilik
suv ichishni ham unutmang, bir stakan
manti bo'lsa men tayyorman
yangi pishgan non hidini sog'indim
dasturxonda siz yetishmaysiz
""",
    "kayfiyat": """
kayfiyatingiz yaxshimi bugun, aytmasangiz ham bilaman
xafa bo'lmang, hammasi yaxshi bo'ladi
tabassum qilib qo'ying, hech kim ko'rmaydi
bugun yaxshi gap eshitdingizmi
derazadan bir qarang, kun juda chiroyli
yaxshi qo'shiq qo'ying, kayfiyat o'zi ko'tariladi
o'zingizni suyuklab qo'ying bugun
bir chuqur nafas oling, hammasi o'tadi
bugun o'zingizga mehribon bo'ling, bilasizmi
kimdir sizni eslayotgan bo'lsa kerak, shundoq bilib turibman
yaxshi odamlar bilan yurish kerak, siz shu yerdasiz
og'ir kun ham o'tadi, ishoning
kayfiyatni buzgan narsani tashlab yuboring, qiyin emas
kulib qo'ying, yuzingizga yarashadi
bugun yaxshi voqea bo'ladi, ichimdan sezyapman
tinchlik, osoyishtalik, mana shu eng yaxshi narsa
kimdir sizdan kuladi, kimdir sizga yo'l ochadi, ahamiyat bermang
sizni yoqtiradigan odamlar bor, o'shalarni o'ylang
yengil yuring, og'ir o'ylamang
bugun hech narsaga xafa bo'lmaymiz
kayfiyat yuqumli, keling yaxshisini ulashamiz
ko'nglingiz tinch bo'lsin
dunyo juda ham yomon emas, yana bir sinab ko'ring
yaxshi uxlab turgan odamning kayfiyati ham yaxshi, shunday emasmi
yuragingiz yengil bo'lsin
""",
    "tun": """
yotdingizmi hali, soat necha bo'ldi
tun xayrli, telefonni qo'yib uxlang
ko'zingiz yumilib ketdi hali yo'qmi
shirin tushlar ko'ring, mening haqimda emas albatta
uxlamasangiz ertaga uyqusiz yurasiz, tushundingizmi
kech bo'ldi, dam oling endi
xayrli tun, yulduzlar sizga qarab turibdi
yotib oling, ertaga gaplashamiz
yaxshi uxlang, tonggacha hech kim bezovta qilmasin
uyqu eng arzon dori, ichib oling
bu vaqtgacha uxlamaganmisiz, bo'lmaydi
telefonni o'chirib, ko'zingizga dam bering
tushingizda yaxshi joylarni ko'ring
oy chiqdi, siz esa hali uyg'oqsiz
xayrli tun va shirin orzular
bugun charchadingiz, endi yotish vaqti
yarim tunda ham yozib turibsizmi, uxlang
ko'rpaga o'ralib yoting, sovuq
bugungi ish bitdi, ertangisi ertaga
uxlab oling, kuch kerak bo'ladi
tong otguncha hech narsa o'ylamang, uxlang
uyqusi kelmagan odam bilan men ham o'tiribman
xayrli tun, tinch uxlang
tush ko'rsangiz menga ham aytib bering
""",
    "kun": """
bugun juma, duo qilib qo'ying
yangi hafta boshlandi, oldinda hammasi bor
dam olish kuni, yotib dam oling
seshanba, hali hafta ko'p
chorshanba, yarim yo'l o'tdik
payshanba, juma yaqin, sabr qiling
shanba kuni sayr qilmasangiz, bo'lmaydi
yakshanba kayfiyati bilan yuramiz
bugun juda yaxshi kun, ko'chaga chiqing
erta tongda uyg'ongan odamning kuni uzoq bo'ladi
tushlik vaqti bo'ldi, ovqatlaning
kun yarmi bo'ldi, charchamadingizmi
kech bo'ldi, bugun ham o'tdi
bahor kelsa hammaning kayfiyati ko'tariladi
yoz issiq bo'lsa ham yoqadi
kuz barglari tushsa, ko'ngil ham yumshaydi
qish sovuq, ammo choy issiq
yomg'ir yog'sa, deraza oldida o'tirish zo'r
bugun ob-havo qanaqa, bizda sovuq
dushanba og'ir, lekin o'tib ketadi
hafta oxiriga oz qoldi, chidang
kun botdi, kechga tayyorlanamiz
quyosh chiqdi, kayfiyat ham chiqsin
bugun kimningdir kuniga yorug'lik bo'ling
juma kuni yaxshilik ko'p qiling
""",
    "dost": """
sen yaxshi odamsan, shu gapni bilib qo'y
sizsiz guruh zerikarli bo'lib qolardi
do'st degani shu, har doim yonida
siz bilan gaplashish yoqimli
yaxshi do'stlar kam topiladi, siz ularning birisiz
guruhda sizning o'rningiz alohida
sizni yaxshi ko'ramiz, bilib qo'ying
bir-birimizga suyanib yuramiz
siz bor joyda hazil ham, mehr ham bor
do'stlik shu, javob bermasang ham kutaveraman
sizdek odamlar bilan tanishganimdan xursandman
mehribon bo'ling, mehr qaytadi
qiyinchilikda ham yoningizda bo'lamiz
hech kim sizdek kulgi ulashmaydi
siz bizning guruhning ruhisiz
birga bo'lsak yengamiz hammasini
sizga qarasam, o'zimga ham kuch kiradi
yaxshi gapingizni kutaman doim
siz haqingizda yaxshi gaplar eshitdim
bunday do'st topish oson emas, qadrlab turing
bir kun ko'rinmasangiz, sog'inib qolamiz
sizni eslab qo'yaman, bilib qo'ying
qadrdon do'stlar bilan hayot go'zal
doim shunday bo'lib qoling
siz kabi odamlar ko'paysin
""",
    "kutish": """
biz sizni kutyapmiz, tezroq keling
guruhga kiring, hamma sizni so'rayapti
onlayn bo'lsangiz bir yozib qo'ying
telefonni ochib qarang, sizni chaqiryapmiz
keling, guruh sizsiz yarim
sizni so'rashyapti, ko'rinib qo'ying
bir minut vaqt ajrating, kiring
ovoz bering, eshityapsizmi
qayerdasiz, hamma yig'ildi
sizni kutib charchadik, javob bering
kirib o'qing, yangilik bor
siz kelmaguncha boshlamaymiz
keling, bir gaplashib olaylik
guruhda gap ko'p, siz yo'qsiz
telefoningiz jiringlayaptimi, bu biz
hozir kirsangiz hech narsani o'tkazib yubormaysiz
qani, javob yozing, kutyapmiz
kimdir sizni so'ragandi, kirib ko'ring
nega ko'rinmaysiz, sog'indik
bu yerda siz uchun maxsus joy bor
tezroq kiring, kech qolasiz
bugun guruhda jonlanish bor, qo'shiling
sizsiz suhbat sust ketyapti
bir og'iz gap yozing, bo'ldi
""",
    "fol": """
bugun kutilmagan yaxshi xabar eshitasiz
yaqinda kimdir sizga yaxshi gap aytadi
bugungi omadingiz sizdan o'tmaydi
kechqurun kayfiyatingiz yanada ko'tariladi
kutilmagan sovg'a olishingiz mumkin
bu hafta yaxshi odam bilan uchrashasiz
yangi imkoniyat eshigingizni qoqadi
sevimli odamingizdan xabar kelishi mumkin
bugun yurgan yo'lingiz omadli bo'ladi
yulduzlar bugun sizga kulib turibdi
ichingizdagi niyat tez ushaladi
bugun bir yaxshilikka duch kelasiz
yaqinlaringizdan yoqimli xabar bor
yangi tanish topasiz, yaxshi odam chiqadi
pul bilan bog'liq yaxshi gap bo'ladi
orzuingizga bir qadam yaqinlashasiz
bugun nimani niyat qilsangiz, qabul bo'ladi
sizni kutilmagan quvonch kutyapti
bu kun sizniki, o'zingizni qo'yib bermang
yaxshi taklif keladi, rad qilmang
tasodifan uchrashgan odam sizga yordam beradi
bugun baxtli tasodiflar bo'ladi
taqdir sizga yaxshi sovg'a tayyorlayapti
yaxshi xabar uzoq emas, kuting
omad bugun sizning tomoningizda
""",
    "tilak": """
sog'-salomat bo'ling, boshqasi o'zi keladi
orzularingiz ushalsin, hammasi yaxshi bo'lsin
uyingizga tinchlik, dasturxoningizga baraka tilayman
ishlaringiz yurishib ketsin
oilangiz sog' bo'lsin, uyingiz obod bo'lsin
rizqingiz halol va mo'l bo'lsin
duolarimiz sizga hamroh bo'lsin
qiyinchiliklar yoningizdan o'tib ketsin
har kuningiz bayramdek o'tsin
niyatingizga yetish nasib qilsin
yuragingizda g'am bo'lmasin
yo'lingiz ochiq, ishingiz omadli bo'lsin
yaqinlaringiz bilan baxtli yashang
tilagingiz bo'lsa Alloh bersin
sizga uzoq umr tilayman
ko'nglingizdagi hamma narsa amalga oshsin
yuzingizdan kulgu arimasin
qaysi yo'lga chiqsangiz, omad yor bo'lsin
sizga yaxshi odamlar yo'liqsin
hech qachon xafa bo'lmang
baxt eshigingizni qoqsin
har bir kuningiz oldingisidan yaxshi bo'lsin
dunyodagi eng yaxshi narsalar sizniki bo'lsin
uyingiz doim to'la, dilingiz doim yorug' bo'lsin
sizga ezgu niyat bilan
""",
    "tabassum": """
bir tabassum qiling, hech narsaga zarar qilmaydi
kulib qo'ying, hozir
kulgingiz juda chiroyli, hech yashirmang
bitta kulgi bir kunni o'zgartiradi
siz kulsangiz atrofdagilar ham kuladi
tabassum qiling, kimdir ko'rib quvonadi
bugun kulib yurish kerak, qoida shunaqa
kulmagan odam yosharib ketmaydi
bir tabassum qimmat emas, bering
yuzingizga kulgi yarashadi, juda
ko'zlaringiz kulsa, hamma narsa yaxshi
kulmasangiz ham mayli, lekin yig'lamang
tabassumingiz bilan yo'lni yoriting
bir kishi kulsa, boshqasiga ham yuqadi
hozir bitta chiroyli tabassum qiling
tabassum qilib turing, dunyo sizga boshqacha qaraydi
kulishdan charchamang, hech kim charchamagan
siz kulganda quyosh ham orqada qoladi
bitta kulgi uchun bir kun kutaman
yuragingizdan kuling, sun'iy emas
tabassumingizni hech kimga bermang, o'zingizda qolsin, lekin ulashing
kulishga sabab kerak emas
siz kulsangiz men ham kulaman
eng chiroyli bezak bu tabassum
birgina kulgi, hammasi unutiladi
""",
}


def _build_phrase_bank() -> tuple[dict[str, list[str]], list[str]]:
    cats: dict[str, list[str]] = {}
    seen: set[str] = set()
    allp: list[str] = []
    for cat, src in _PHRASE_SRC.items():
        items: list[str] = []
        for line in src.splitlines():
            s = line.strip()
            key = s.lower()
            if s and key not in seen:
                seen.add(key)
                items.append(s)
                allp.append(s)
        cats[cat] = items
    return cats, allp


PHRASE_CATS, PHRASES = _build_phrase_bank()

# gap oxiriga tasodifiy qo'shiladigan emojilar (ba'zan, 55% ehtimol bilan)
PHRASE_EMOJIS = ["🍀", "😊", "😂", "☕", "😌", "🔥", "✨", "🌙", "💙", "👀", "😄", "🌟", "🤝", "🙌", "😉", "🌸",
                 "💫", "🎯", "🎲", "😎", "🥰", "☺️", "🌷", "🍃", "💎", "🫶", "😁", "🌞", "⭐️", "💛"]

DEFAULT_RANDOM_TEXTS = PHRASES   # eski nom bilan moslik uchun

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
    mention_on INTEGER DEFAULT 1, mention_delay INTEGER DEFAULT 0);
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
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS promos(
    code TEXT PRIMARY KEY, plan_key TEXT, days INTEGER, max_uses INTEGER DEFAULT 0,
    used INTEGER DEFAULT 0, active INTEGER DEFAULT 1, created REAL);
CREATE TABLE IF NOT EXISTS promo_uses(code TEXT, user_id INTEGER, ts REAL, PRIMARY KEY(code, user_id));
CREATE TABLE IF NOT EXISTS payments(
    id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_key TEXT, amount INTEGER, days INTEGER,
    ts REAL, by_id INTEGER);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, actor INTEGER, action TEXT, detail TEXT);
CREATE INDEX IF NOT EXISTS idx_coll_owner ON collected(owner_id);
CREATE INDEX IF NOT EXISTS idx_acc_owner ON accounts(owner_id);
CREATE TABLE IF NOT EXISTS react_bots(
    id INTEGER PRIMARY KEY AUTOINCREMENT, tg_id INTEGER UNIQUE, username TEXT, token TEXT,
    active INTEGER DEFAULT 1, created REAL);
CREATE TABLE IF NOT EXISTS react_channels(
    chat_id INTEGER PRIMARY KEY, owner_id INTEGER, title TEXT, username TEXT, auto INTEGER DEFAULT 0,
    emojis TEXT DEFAULT '', cnt INTEGER DEFAULT 0, total INTEGER DEFAULT 0, created REAL);
CREATE TABLE IF NOT EXISTS react_access(user_id INTEGER PRIMARY KEY, until REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS dm_access(user_id INTEGER PRIMARY KEY, quota INTEGER DEFAULT 0, used INTEGER DEFAULT 0);
"""


async def init_db() -> None:
    global DB
    DB = await aiosqlite.connect(DB_PATH)
    DB.row_factory = aiosqlite.Row
    await DB.execute("PRAGMA journal_mode=WAL")
    await DB.executescript(SCHEMA)
    for col in ("bonus_acc", "bonus_mention", "bonus_scrape", "bonus_export"):   # eski bazalar uchun migratsiya
        try:
            await DB.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")
        except Exception:  # noqa: BLE001
            pass
    for ddl in ("ALTER TABLE users ADD COLUMN mention_panel INTEGER DEFAULT 1",    # guruhda hisobot paneli
                "ALTER TABLE users ADD COLUMN stop_word TEXT DEFAULT ''"):          # foydalanuvchining o'z stop so'zi
        try:
            await DB.execute(ddl)
        except Exception:  # noqa: BLE001
            pass
    for ddl in ("ALTER TABLE accounts ADD COLUMN old_bio TEXT DEFAULT ''",     # akkauntning avvalgi bio'si (o'chirilganda qaytariladi)
                "ALTER TABLE accounts ADD COLUMN bio_done INTEGER DEFAULT 0"):
        try:
            await DB.execute(ddl)
        except Exception:  # noqa: BLE001
            pass
    await DB.commit()
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
    if not p:
        return None
    p = dict(p)
    try:   # admin bergan shaxsiy ustunliklar (bonuslar)
        p["max_accounts"] += int(u["bonus_acc"] or 0)
        if p["mention_daily"] >= 0:
            p["mention_daily"] += int(u["bonus_mention"] or 0)
        if p["scrape_daily"] >= 0:
            p["scrape_daily"] += int(u["bonus_scrape"] or 0)
        if u["bonus_export"]:
            p["can_export"] = 1
    except (KeyError, IndexError, TypeError):
        pass
    return p


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


# ══════════════════════════ SOZLAMALAR (bot ichidan boshqariladi) ══════════════════════════
CFG: dict[str, str] = {}
CFG_DEF = {
    "maintenance": "0", "reg_on": "1", "free_on": "1", "scrape_on": "1", "mention_on": "1",
    "export_on": "1", "addacc_on": "1", "ref_on": "1",
    "max_scrape": str(MAX_SCRAPE), "max_mention": str(MAX_MENTION_MEMBERS),
    "min_delay": "1", "max_delay": "10", "default_delay": "0",
    "random_texts": "", "pay_username": "", "pay_card_text": "",
    "gift_tiers": "", "admins": "[]", "owner_id": "0", "bio_on": "1", "bio_ad": "",
    "react_on": "1", "dm_on": "1", "dm_min_delay": "8", "dm_max_delay": "16",
    "sign_on": "1", "sign_text": "",
}
MAINT_DEFAULT = "🚧 <b>Botda texnik ishlar ketmoqda.</b>\nIltimos, birozdan so'ng qayta urinib ko'ring."


def cfg(k: str) -> str:
    return CFG.get(k, CFG_DEF.get(k, ""))


def cfg_on(k: str) -> bool:
    return cfg(k) == "1"


def cfg_int(k: str) -> int:
    try:
        return int(cfg(k))
    except (TypeError, ValueError):
        try:
            return int(CFG_DEF.get(k) or 0)
        except ValueError:
            return 0


async def cfg_set(k: str, v: str) -> None:
    CFG[k] = v
    await db_exec("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))


async def cfg_del(k: str) -> None:
    CFG.pop(k, None)
    await db_exec("DELETE FROM settings WHERE key=?", (k,))


async def load_cfg() -> None:
    global OWNER_ID, OWNER_USERNAME, ADMINS
    for r in await db_all("SELECT key, value FROM settings"):
        CFG[r["key"]] = r["value"]
    try:
        OWNER_ID = int(cfg("owner_id") or 0)
    except ValueError:
        OWNER_ID = 0
    if cfg("owner_username"):
        OWNER_USERNAME = cfg("owner_username")
    try:
        ADMINS = {int(x) for x in json.loads(cfg("admins") or "[]")}
    except Exception:  # noqa: BLE001
        ADMINS = set()
    log.info("Ega: @%s (id=%s) | adminlar: %s", OWNER_USERNAME, OWNER_ID or "hali biriktirilmagan", len(ADMINS))


async def save_admins() -> None:
    await cfg_set("admins", json.dumps(sorted(ADMINS)))


def is_owner(uid: int) -> bool:
    return bool(OWNER_ID) and uid == OWNER_ID


def is_staff(uid: int) -> bool:
    return bool(uid) and (uid == OWNER_ID or uid in ADMINS)


async def audit(actor: int, action: str, detail: str = "") -> None:
    try:
        await db_exec("INSERT INTO audit(ts,actor,action,detail) VALUES(?,?,?,?)", (time.time(), actor, action, detail[:300]))
    except Exception:  # noqa: BLE001
        pass


async def set_owner(uid: int, uname: str | None) -> None:
    global OWNER_ID, OWNER_USERNAME
    OWNER_ID = uid
    await cfg_set("owner_id", str(uid))
    if uname:
        OWNER_USERNAME = uname
        await cfg_set("owner_username", uname)
    if uid in ADMINS:
        ADMINS.discard(uid)
        await save_admins()


async def bind_owner_if_needed(user) -> None:
    """@OWNER_USERNAME egasi botga birinchi marta yozganda uning ID si bazaga biriktiriladi."""
    global OWNER_USERNAME
    uname = user.username or ""
    if OWNER_ID:
        if user.id == OWNER_ID and uname and uname != OWNER_USERNAME:
            OWNER_USERNAME = uname
            await cfg_set("owner_username", uname)
        return
    if uname and uname.lower() == OWNER_USERNAME.lower():
        await set_owner(user.id, uname)
        await audit(user.id, "owner_bind", f"@{uname}")
        log.info("Bot egasi biriktirildi: @%s (%s)", uname, user.id)


def T(name: str) -> str:
    base = {"welcome": WELCOME, "help": HELP_TEXT, "noplan": NO_PLAN_DEFAULT, "sub": SUB_TEXT_DEFAULT,
            "guide": GUIDE_TEXT, "maint": MAINT_DEFAULT}[name]
    return (cfg("t_" + name) or base).replace("{owner}", OWNER_USERNAME)


def gift_tiers() -> list[tuple[int, str, str]]:
    raw = cfg("gift_tiers")
    if raw:
        try:
            return sorted((int(a), str(b), str(c)) for a, b, c in json.loads(raw))
        except Exception:  # noqa: BLE001
            pass
    return list(GIFT_TIERS)


def custom_texts() -> list[str]:
    """Admin panelidan qo'shilgan qo'shimcha gaplar (asosiy bazadan tashqari)."""
    return [x.strip() for x in cfg("random_texts").split("\n") if x.strip()]


def random_texts() -> list[str]:
    """Asosiy baza + admin qo'shgan gaplar, takrorlarsiz."""
    seen: set[str] = set()
    out: list[str] = []
    for t in list(PHRASES) + custom_texts():
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


class PhraseDeck:
    """Gaplarni aralashtirib beradi: barcha gap ishlatilmaguncha hech biri takrorlanmaydi."""

    def __init__(self, texts: list[str], emoji: bool = True):
        self.src = list(texts) or ["Salom"]
        self.emoji = emoji
        self.deck: list[str] = []
        self.last = ""

    def _refill(self) -> None:
        self.deck = self.src[:]
        random.shuffle(self.deck)
        if len(self.deck) > 1 and self.deck[-1] == self.last:   # chegarada ketma-ket takror bo'lmasin
            self.deck[0], self.deck[-1] = self.deck[-1], self.deck[0]

    def next(self) -> str:
        if not self.deck:
            self._refill()
        t = self.deck.pop()
        self.last = t
        if self.emoji and random.random() < 0.55 and not re.search(r"[\U0001F300-\U0001FAFF☀-➿]\s*$", t):
            t = f"{t} {random.choice(PHRASE_EMOJIS)}"
        return t


def parse_phrase_arg(arg: str) -> tuple[list[str], bool, str]:
    """.r argumentini tahlil qiladi → (gaplar, emoji_qo'shish, xato matni).
       bo'sh → butun baza | #toifa #toifa → tanlangan toifalar | a | b | c → o'z gaplari"""
    arg = (arg or "").strip()
    if not arg:
        return random_texts(), True, ""
    if "|" in arg:
        return [t.strip() for t in arg.split("|") if t.strip()], False, ""
    tags = re.findall(r"#(\w+)", arg)
    if tags:
        picked: list[str] = []
        for tg in tags:
            key = tg.lower()
            if key not in PHRASE_CATS:
                return [], True, ("Bunday toifa yo'q: #" + tg + "\nMavjud toifalar: " +
                                  ", ".join("#" + c for c in PHRASE_CATS))
            picked += PHRASE_CATS[key]
        return picked, True, ""
    return [arg], False, ""


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
    if base <= 0:            # ⚡ TURBO: xabarlar orasida 0.3 soniya
        return TURBO_DELAY
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


BIO_AD_DEFAULT = "🤖 Reklama @LegionUatgerBot yordamida qo'yildi"


def bio_ad_text() -> str:
    return (cfg("bio_ad") or BIO_AD_DEFAULT).strip()


async def apply_bio_ad(client: TelegramClient, acc_id: int) -> None:
    """Akkaunt ulanganda bioga bot reklamasini yozadi. Avvalgi bio saqlanadi va akkaunt o'chirilganda qaytariladi."""
    try:
        if not cfg_on("bio_on"):
            return
        row = await db_one("SELECT bio_done FROM accounts WHERE id=?", (acc_id,))
        if not row or row["bio_done"]:
            return
        me = await client.get_me()
        full = await client(GetFullUserRequest(me))
        old = (getattr(getattr(full, "full_user", full), "about", "") or "").strip()
        ad = bio_ad_text()
        limit = 140 if getattr(me, "premium", False) else 70
        ad = ad[:limit]
        if ad.lower() in old.lower():
            await db_exec("UPDATE accounts SET bio_done=1 WHERE id=?", (acc_id,))
            return
        await client(UpdateProfileRequest(about=ad))
        await db_exec("UPDATE accounts SET bio_done=1, old_bio=? WHERE id=?", (old, acc_id))
    except AUTH_ERRORS:
        raise
    except Exception as e:  # noqa: BLE001
        log.warning("bio ad %s: %s", acc_id, e)


async def restore_bio(client: TelegramClient, acc) -> None:
    """Akkaunt o'chirilganda avvalgi bio qaytariladi (agar hali reklama turgan bo'lsa)."""
    try:
        if not acc["bio_done"]:
            return
        me = await client.get_me()
        full = await client(GetFullUserRequest(me))
        cur = (getattr(getattr(full, "full_user", full), "about", "") or "")
        if bio_ad_text()[:70].lower() in cur.lower() or "legionuatgerbot" in cur.lower():
            await client(UpdateProfileRequest(about=(acc["old_bio"] or "")[:140]))
    except Exception as e:  # noqa: BLE001
        log.debug("restore bio: %s", e)


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
        spawn(apply_bio_ad(client, acc_id))
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


# ══════════════ UTAG: 3 XIL MENTION TURI ══════════════
#   1-tur  .r  / .ro   →  @user + har xil gap (jonli gaplar bazasi, takrorlanmaydi)
#   2-tur  .m  / .mo   →  faqat @user (matnsiz)
#   3-tur  .u  / .uo   →  @user + hamma uchun bir xil matn (+ emoji / premium emoji)
#   Oxiridagi «o» harfi = faqat onlayn a'zolar (.ro .mo .uo)
#   SON:   .uo 100  |  .ro 88  |  .m 50  |  .u 30 matn  |  .u matn 30     (0 yoki yozilmasa = hammasi)
#   .su  yoki  /stop   →  to'xtatadi (faqat akkaunt egasining o'zi yozganda)      /start → oxirgi utagni qayta boshlaydi
CMD_RE = re.compile(r"^\.(su|uo|u|ro|r|mo|m)(?:\s+(.*?))?\s*$", re.S)
ONLINE_CMDS = {"uo", "ro", "mo"}
RESTART_WINDOW = 1800          # /start guruhda oxirgi utagni faqat shu soniya ichida qayta ishga tushiradi (30 daqiqa)
# (acc_id, chat_id) → (cmd, son, matn, entitylar, vaqt)   — /start uchun oxirgi buyruq
LAST_CMD: dict[tuple[int, int], tuple[str, int, str, list, float]] = {}

# matn ichida saqlanadigan formatlash (premium custom emoji ham shu yerda)
_KEEP_ENT_NAMES = ("MessageEntityCustomEmoji", "MessageEntityBold", "MessageEntityItalic", "MessageEntityUnderline",
                   "MessageEntityStrike", "MessageEntityCode", "MessageEntitySpoiler", "MessageEntityBlockquote")
KEEP_ENTS = tuple(getattr(tl_types, n) for n in _KEEP_ENT_NAMES if hasattr(tl_types, n))


def u16(s: str) -> int:
    """Telegram entity offsetlari UTF-16 birligida hisoblanadi."""
    return len(s.encode("utf-16-le")) // 2


def split_count(arg: str) -> tuple[int | None, str, int]:
    """Sonni ajratadi: buyruqdan keyin (.uo 100 | .u 30 matn) yoki oxirida (.u matn 30).
       → (son yoki None, qolgan matn, qolgan matn arg ichida qaysi belgidan boshlanadi)
       Matn oxiri raqam bilan tugashi kerak bo'lsa, boshiga 0 qo'ying:  .u 0 soat 8"""
    m = re.match(r"^(\d{1,5})(?:\s+(.*))?$", arg, re.S)
    if m:
        return int(m.group(1)), (m.group(2) or ""), (m.start(2) if m.group(2) is not None else len(arg))
    m = re.match(r"^(.*\S)\s+(\d{1,5})$", arg, re.S)
    if m and not m.group(1).rstrip().endswith("|"):
        return int(m.group(2)), m.group(1), 0
    return None, arg, 0


def activity_rank(u) -> tuple[int, float]:
    """Kim yaqinda faolroq bo'lsa, shu oldinda turadi (0 = hozir onlayn)."""
    st = getattr(u, "status", None)
    if isinstance(st, UserStatusOnline):
        return (0, 0.0)
    if isinstance(st, UserStatusRecently):
        return (1, 0.0)
    if isinstance(st, UserStatusOffline):
        try:
            return (2, -st.was_online.timestamp())
        except Exception:  # noqa: BLE001
            return (2, 0.0)
    if isinstance(st, UserStatusLastWeek):
        return (3, 0.0)
    if isinstance(st, UserStatusLastMonth):
        return (4, 0.0)
    return (5, 0.0)


def pick_members(pool: list, online: bool, want: int) -> tuple[list, int]:
    """Yig'ilganlardan kerakli odamlarni tanlaydi → (tanlanganlar, onlayn soni).
       online rejim: avval onlaynlar, yetmasa qolganini TASODIFIY a'zolar bilan to'ldiradi (son berilgan bo'lsa).
       oddiy rejim: eng faollari oldinda; son berilsa shuncha."""
    users = list(pool)
    on = [u for u in users if is_online(u)]
    if online:
        if not want:
            return on, len(on)
        if len(on) >= want:
            return on[:want], len(on)
        on_ids = {u.id for u in on}
        rest = [u for u in users if u.id not in on_ids]
        random.shuffle(rest)
        return on + rest[:want - len(on)], len(on)
    users.sort(key=activity_rank)
    return (users[:want] if want else users), len(on)


async def collect_members(client, chat, me_id: int, stop: asyncio.Event, want: int, online: bool) -> tuple[list, int]:
    """A'zolarni imkon qadar to'liq yig'adi.
       1) Telegram katta guruhlarda oddiy ro'yxatdan atigi ~200 tani beradi → aggressive qidiruv ishlatiladi.
       2) Yetmasa, oxirgi xabarlar mualliflari qo'shiladi (aktiv odamlar, ko'pincha onlayn).
       → (a'zolar ro'yxati, guruhdagi jami a'zo soni)"""
    cap = max(cfg_int("max_mention"), 1)
    pool: dict[int, object] = {}
    on_cnt = 0

    def add(u) -> None:
        nonlocal on_cnt
        if isinstance(u, User) and not u.bot and not u.deleted and u.id != me_id and u.id not in pool and len(pool) < cap:
            pool[u.id] = u
            if is_online(u):
                on_cnt += 1

    total = 0
    try:
        total = int(getattr(await client.get_participants(chat, limit=0), "total", 0) or 0)
    except AUTH_ERRORS:
        raise
    except Exception:  # noqa: BLE001
        total = 0

    async def grab(**kw) -> None:
        async for u in client.iter_participants(chat, limit=cap, **kw):
            if stop.is_set():
                return
            add(u)

    try:
        try:
            await grab(aggressive=True)
        except TypeError:          # telethon versiyasida aggressive bo'lmasa
            await grab()
    except AUTH_ERRORS:
        raise
    except FloodWaitError as e:
        log.warning("participants flood %ss (yig'ilgani bilan davom etamiz)", getattr(e, "seconds", "?"))
    except (ChannelPrivateError, ChatAdminRequiredError):
        pass
    except Exception as e:  # noqa: BLE001
        log.warning("participants: %s", e)

    need = min(want or cap, cap)
    target = min(need, total) if total else need

    def enough() -> bool:
        return on_cnt >= need if online else len(pool) >= target

    if not enough() and not stop.is_set():
        try:
            async for msg in client.iter_messages(chat, limit=SCAN_MESSAGES):
                if stop.is_set():
                    break
                add(getattr(msg, "sender", None))
                if enough():
                    break
        except AUTH_ERRORS:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("scan messages: %s", e)
    return list(pool.values()), max(total, len(pool))


def build_mention(u, body: str = "", body_ents: list | None = None) -> tuple[str, list]:
    """Bitta a'zo uchun xabar: username bo'lsa oddiy @username, bo'lmasa ismi bosiladigan mention."""
    ents: list = []
    if u.username:
        label = "@" + u.username
    else:
        label = (user_title(u) or "user").replace("\n", " ")[:24]
        try:
            ents.append(tl_types.InputMessageEntityMentionName(0, u16(label), tl_utils.get_input_user(u)))
        except Exception:  # noqa: BLE001
            pass
    text = label
    if body:
        text += " " + body
        shift = u16(label + " ")
        for e in body_ents or []:
            ne = copy.copy(e)
            ne.offset = e.offset + shift
            ents.append(ne)
    return text, ents


def panel_text(title: str, sent: int, total: int, started: float, errors: int,
               want: int = 0, extra: list | None = None) -> str:
    el = max(time.monotonic() - started, 0.01)
    line = "────────────────────"
    rows = [line, title]
    if want:
        rows.append(f"🎯 Belgilangan: {want}")
    rows += [f"📊 Yuborildi: {sent}/{total}", f"⏱ Vaqt: {el:.2f}s", f"⚡ Tezlik: {sent / el:.1f}/s", f"❌ Xatolar: {errors}"]
    rows += list(extra or [])
    rows.append(line)
    return "\n".join(rows)


async def interruptible_sleep(stop: asyncio.Event, sec: float) -> None:
    """Kutish paytida ham stop darhol ishlaydi."""
    try:
        await asyncio.wait_for(stop.wait(), timeout=sec)
    except (asyncio.TimeoutError, TimeoutError):
        pass


def stop_job(acc_id: int, chat_id: int) -> bool:
    ev = RUNNING.get((acc_id, chat_id))
    if ev and not ev.is_set():
        ev.set()
        return True
    return False


def valid_stop_word(w: str) -> bool:
    """O'z stop so'zi: 1–20 belgi, bo'sh joysiz, boshqa buyruqlar bilan to'qnashmasin."""
    if not (1 <= len(w) <= 20) or re.search(r"\s", w):
        return False
    lw = w.lower()
    if lw in ("/start", "/stop") or CMD_RE.match(lw):
        return False
    return True


def attach_handlers(client: TelegramClient, acc_id: int, owner_id: int) -> None:
    async def on_msg(event):
        try:
            await on_outgoing(event, client, acc_id, owner_id)
        except Exception as e:  # noqa: BLE001
            log.warning("mention handler: %s", e)

    async def on_ctrl(event):
        try:
            await on_ctl(event, client, acc_id, owner_id)
        except Exception as e:  # noqa: BLE001
            log.warning("ctl handler: %s", e)

    client.add_event_handler(on_msg, events.NewMessage(outgoing=True, pattern=r"^\.(?:su|uo|u|ro|r|mo|m)(?:\s|$)"))
    # /stop, /start va foydalanuvchining o'z stop so'zi — faqat shu akkauntning O'ZI yozgan qisqa xabarlar
    client.add_event_handler(on_ctrl, events.NewMessage(outgoing=True,
                                                        func=lambda e: bool(e.is_group) and 0 < len(e.raw_text or "") <= 40))


async def on_ctl(event, client: TelegramClient, acc_id: int, owner_id: int) -> None:
    low = (event.raw_text or "").strip().lower()
    key = (acc_id, event.chat_id)
    if low == "/stop" or re.match(r"^/stop@\w+$", low):
        if stop_job(acc_id, event.chat_id):
            try:
                await event.delete()
            except Exception:  # noqa: BLE001
                pass
        return
    if low == "/start" or re.match(r"^/start@\w+$", low):
        last = LAST_CMD.get(key)
        if last and key not in RUNNING and time.time() - last[4] <= RESTART_WINDOW:
            await launch_mention(event, client, acc_id, owner_id, last[0], last[1], last[2], last[3])
        return
    if key in RUNNING:
        u = await get_user(owner_id)
        try:
            sw = (u["stop_word"] or "").strip().lower() if u else ""
        except (KeyError, IndexError):
            sw = ""
        if sw and low == sw and stop_job(acc_id, event.chat_id):
            try:
                await event.delete()
            except Exception:  # noqa: BLE001
                pass


async def on_outgoing(event, client: TelegramClient, acc_id: int, owner_id: int) -> None:
    if not event.is_group:
        return
    raw = event.raw_text or ""
    m = CMD_RE.match(raw)
    if not m:
        return
    cmd, arg = m.group(1), (m.group(2) or "")

    if cmd == "su":
        stop_job(acc_id, event.chat_id)
        try:
            await event.delete()
        except Exception:  # noqa: BLE001
            pass
        return

    count, rest, off = split_count(arg)

    # 3-tur uchun matn ichidagi formatlash/premium emoji'larni saqlab qolamiz
    arg_ents: list = []
    if rest and cmd[0] == "u" and getattr(event.message, "entities", None):
        s16 = u16(raw[:m.start(2)]) + u16(arg[:off])
        e16 = s16 + u16(rest)
        for e in event.message.entities:
            if isinstance(e, KEEP_ENTS) and e.offset >= s16 and e.offset + e.length <= e16:
                ne = copy.copy(e)
                ne.offset = e.offset - s16
                arg_ents.append(ne)
    await launch_mention(event, client, acc_id, owner_id, cmd, count or 0, rest, arg_ents)


async def launch_mention(event, client, acc_id: int, owner_id: int, cmd: str, count: int, rest: str, ents: list) -> None:
    """Ruxsatlarni tekshirib, utagni fonda ishga tushiradi."""
    key = (acc_id, event.chat_id)
    u = await get_user(owner_id)
    if owner_id != OWNER_ID and (not u or u["banned"]):
        return
    if u and not u["mention_on"]:
        return
    if not cfg_on("mention_on") and not is_staff(owner_id):
        await notify_user(owner_id, "🚧 Mention funksiyasi vaqtincha o'chirilgan. Keyinroq urinib ko'ring.", cooldown=600)
        return
    plan = await get_active_plan(owner_id)
    if not plan:
        await notify_user(owner_id, "⛔ Mention ishlamadi: faol tarifingiz yo'q.\n«💳 Tarif sotib olish» bo'limiga kiring.", cooldown=600)
        return
    if key in RUNNING:
        return
    LAST_CMD[key] = (cmd, count, rest, ents, time.time())
    stop = asyncio.Event()
    RUNNING[key] = stop
    spawn(run_mention(client, event, acc_id, owner_id, cmd, count, rest, ents, stop))


async def run_mention(client, event, acc_id, owner_id, cmd, want, arg, arg_ents, stop: asyncio.Event) -> None:
    key = (acc_id, event.chat_id)
    kind = cmd[0]                       # 'r' = gap bilan | 'm' = faqat mention | 'u' = bir xil matn
    online = cmd in ONLINE_CMDS
    sent = errors = 0
    started = time.monotonic()
    panel = None
    n = 0
    extras: list[str] = []
    try:
        chat = await event.get_input_chat()
        try:
            await event.delete()
        except Exception:  # noqa: BLE001
            pass

        deck = None
        if kind == "r":
            texts, use_emoji, err = parse_phrase_arg(arg)
            if err:
                await notify_user(owner_id, "⚠️ " + esc(err))
                return
            if not texts:
                await notify_user(owner_id, "⚠️ Gaplar topilmadi.")
                return
            deck = PhraseDeck(texts, use_emoji)

        urow = await get_user(owner_id)
        try:
            show_panel = bool(urow["mention_panel"]) if urow else True
        except (KeyError, IndexError):
            show_panel = True
        line = "────────────────────"
        if show_panel:
            try:
                panel = await client.send_message(chat, f"{line}\n🔎 A'zolar yig'ilmoqda...\n{line}", parse_mode=None)
            except Exception:  # noqa: BLE001
                panel = None

        async def edit_panel(text: str) -> None:
            if not panel:
                return
            try:
                await client.edit_message(chat, panel.id, text, parse_mode=None)
            except Exception:  # noqa: BLE001
                pass

        me = await client.get_me()
        want = min(max(int(want or 0), 0), cfg_int('max_mention'))
        pool, total = await collect_members(client, chat, me.id, stop, want, online)
        members, on_count = pick_members(pool, online, want)
        n = len(members)

        if len(pool) < total:
            extras.append(f"ℹ️ Telegram {len(pool)}/{total} a'zoni berdi")
        if online:
            extras.append(f"🟢 Onlayn topildi: {on_count}")
            if want and on_count < want and n > on_count:
                extras.append(f"➕ Qolgani ({n - on_count}) tasodifiy a'zolar bilan to'ldirildi")
        if want and n < want:
            extras.append(f"⚠️ Mos a'zo faqat {n} ta topildi")

        if stop.is_set():
            await edit_panel(panel_text("✅ Mention to'xtatildi!", 0, n, started, 0, want, extras))
            return
        if not members:
            if panel:
                await edit_panel(panel_text("ℹ️ Mention uchun mos a'zo topilmadi", 0, 0, started, 0, want, extras))
            else:
                await notify_user(owner_id, "ℹ️ Mention uchun mos a'zo topilmadi.", cooldown=60)
            return

        ud = int(urow["mention_delay"]) if urow else 2
        if ud <= 0:          # ⚡ TURBO (0.3s) — katta guruhda ham pauza kattalashtirilmaydi
            base = 0
        else:
            base = min(max(ud, cfg_int('min_delay')), max(cfg_int('max_delay'), cfg_int('min_delay')))
            if n > 500:
                base = max(base, 5)
            elif n > 100:
                base = max(base, 3)

        last_edit = 0.0
        await edit_panel(panel_text("⏳ Mention davom etmoqda...", 0, n, started, 0, want, extras))
        last_edit = time.monotonic()

        async def refresh(title: str, force: bool = False) -> None:
            nonlocal last_edit
            if not panel:
                return
            now = time.monotonic()
            if not force and now - last_edit < 8:
                return
            last_edit = now
            await edit_panel(panel_text(title, sent, n, started, errors, want, extras))

        title_end = "✅ Mention yakunlandi!"
        i = retries = fails_in_row = 0
        while i < n:
            if stop.is_set():
                title_end = "✅ Mention to'xtatildi!"
                break
            plan = await get_active_plan(owner_id)
            if not plan:
                await notify_user(owner_id, "⛔ Tarifingiz tugadi, mention to'xtatildi.")
                title_end = "⛔ Tarif tugadi, mention to'xtatildi!"
                break
            if plan["mention_daily"] >= 0:
                _, used = await usage_get(owner_id)
                if used + 1 > plan["mention_daily"]:
                    await notify_user(owner_id, f"📈 Kunlik mention limiti tugadi ({used}/{plan['mention_daily']}). "
                                                f"Ertaga davom ettiring yoki tarifni oshiring.")
                    title_end = "📈 Kunlik limit tugadi, mention to'xtatildi!"
                    break

            tick = time.monotonic()
            u = members[i]
            if kind == "r":
                text, ents = build_mention(u, with_sign(deck.next(), "\n"))
            elif kind == "u" and arg:
                text, ents = build_mention(u, with_sign(arg, "\n"), arg_ents)
            else:
                text, ents = build_mention(u)
            try:
                await client.send_message(chat, text, parse_mode=None, formatting_entities=ents or None, link_preview=False)
                sent += 1
                i += 1
                retries = fails_in_row = 0
                await usage_add(owner_id, mentions=1)
            except (FloodWaitError, SlowModeWaitError) as e:
                wait = int(getattr(e, "seconds", 30)) + 1
                retries += 1
                if wait > 900 or retries > 5:
                    await notify_user(owner_id, f"⏳ Telegram {wait} soniya kutishni talab qildi, mention to'xtatildi.")
                    title_end = "⏳ Telegram cheklovi, mention to'xtatildi!"
                    break
                await refresh(f"⏳ Telegram cheklovi: {wait}s kutilmoqda...", force=True)
                await interruptible_sleep(stop, wait)
                continue
            except (ChatWriteForbiddenError, UserBannedInChannelError, ChatAdminRequiredError) as e:
                await notify_user(owner_id, f"🚫 Guruhga yozish mumkin emas: {type(e).__name__}")
                title_end = "🚫 Guruhga yozib bo'lmadi!"
                break
            except AUTH_ERRORS:
                raise
            except Exception as e:  # noqa: BLE001
                log.warning("mention send: %s", e)
                errors += 1
                fails_in_row += 1
                i += 1
                if fails_in_row >= 5:
                    await notify_user(owner_id, f"⚠️ Ketma-ket xatolar ({esc(type(e).__name__)}), mention to'xtatildi.")
                    title_end = "⚠️ Ketma-ket xatolar, mention to'xtatildi!"
                    break
            await refresh("⏳ Mention davom etmoqda...")
            gap = calc_delay(base)
            if base <= 0:      # turbo: yuborish vaqtini hisobga olamiz, aniq 0.3s oralig'i
                gap = max(gap - (time.monotonic() - tick), 0.0)
            if gap > 0:
                await interruptible_sleep(stop, gap)

        if panel:
            await refresh(title_end, force=True)
        else:   # guruhda panel o'chirilgan bo'lsa, hisobot egasiga bot orqali boradi
            await notify_user(owner_id, "<code>" + esc(panel_text(title_end, sent, n, started, errors, want, extras)) + "</code>")
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
        async for u in client.iter_participants(ent, limit=cfg_int('max_scrape')):
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
B_PROMO = "🎟 Promokod"
B_REACT = "❤️ Reaksiya"
B_DM = "✉️ Shaxsiy xabar"
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
            [KeyboardButton(text=B_PLANS), KeyboardButton(text=B_PROMO), KeyboardButton(text=B_REF)],
            [KeyboardButton(text=B_REACT), KeyboardButton(text=B_DM)],
            [KeyboardButton(text=B_SET), KeyboardButton(text=B_STAT), KeyboardButton(text=B_HELP)]]
    if is_staff(uid):
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
    return f"https://t.me/{cfg('pay_username') or OWNER_USERNAME}?text=" + quote(f"Salom! {plan_title} tarifini sotib olmoqchiman. Mening ID: {uid}")


def plan_card(p) -> str:
    price = "BEPUL 🎁" if p["price"] == 0 else f"{p['price']:,} so'm".replace(",", " ")
    return (f"⭐ <b>{esc(p['title'])}</b>\n"
            f"┌──────────────────\n"
            f"├ 💰 Narx: <b>{price}</b>\n"
            f"├ ⏳ Muddati: <b>{p['days']} kun</b>\n"
            f"├ 👤 Akkauntlar: <b>{p['max_accounts']} ta</b>\n"
            f"├ 🧲 Odam yig'ish: <b>{'Cheksiz ♾' if p['scrape_daily'] < 0 else str(p['scrape_daily']) + ' ta/kun'}</b>\n"
            f"├ 📥 Userlarni yuklab olish: {yn(p['can_export'])}\n"
            f"├ 📣 Mention (.r .m .u): <b>{'Cheksiz ♾' if p['mention_daily'] < 0 else str(p['mention_daily']) + ' ta/kun'}</b>\n"
            f"└──────────────────")


NO_PLAN_DEFAULT = ("⛔ <b>Faol tarifingiz yo'q.</b>\n\nBepul tarifni olish uchun pastdagi tugmani bosing "
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
    "Buyruqni <b>ulangan akkauntingiz bilan guruhga</b> yozasiz. Har bir a'zo alohida xabarda belgilanadi.\n\n"
    "🎯 <b>3 xil utag turi:</b>\n\n"
    "1️⃣ <b>Gap bilan</b> (har kimga turli gap)\n"
    f"• <code>.r</code> — {len(PHRASES)} ta gapdan tasodifiy, hech biri takrorlanmaydi\n"
    "• <code>.r #hazil #salom</code> — faqat tanlangan toifalardan\n"
    "• <code>.r gap1 | gap2 | gap3</code> — o'z gaplaringizdan\n"
    "• Toifalar: " + ", ".join("#" + c for c in PHRASE_CATS) + "\n\n"
    "2️⃣ <b>Faqat mention</b> (matnsiz)\n"
    "• <code>.m</code> — hammani faqat @username bilan chaqiradi\n\n"
    "3️⃣ <b>Bir xil matn</b> (hammaga bitta xabar)\n"
    "• <code>.u matn</code> — masalan: <code>.u o'yinga qo'shiling 🔥</code>\n"
    "• Premium akkauntda matn ichidagi maxsus emoji ham saqlanadi\n\n"
    "🟢 <b>Faqat online a'zolar:</b> oxiriga <b>o</b> qo'shing → <code>.ro</code> <code>.mo</code> <code>.uo</code>\n"
    "🔢 <b>Son bilan:</b> buyruqdan keyin yoki oxiriga raqam yozing\n"
    "• <code>.uo 100</code> — 100 ta odamni utag qiladi (online yetmasa, qolganini tasodifiy a'zolar bilan to'ldiradi)\n"
    "• <code>.ro 88</code>, <code>.m 50</code>, <code>.u 30 matn</code>, <code>.u matn 30</code>\n"
    "• Son yozilmasa yoki <code>0</code> bo'lsa — hammasi\n\n"
    "🛑 <b>To'xtatish</b> (faqat o'zingiz yozganda ishlaydi):\n"
    "• <code>/stop</code> yoki <code>.su</code> — guruhda zudlik bilan to'xtatadi\n"
    "• <code>/start</code> — guruhda oxirgi utagni (turi va soni bilan) qayta boshlaydi\n"
    "• Botga <code>/stop</code> — barcha ishlayotgan utaglaringiz to'xtaydi\n"
    "• Sozlamalarda o'z stop so'zingizni belgilashingiz mumkin\n\n"
    "📊 Ish tugagach guruhda hisobot chiqadi: belgilangan son, yuborildi, vaqt, tezlik, xatolar.\n\n"
    "⚙️ <b>Sozlamalar:</b>\n"
    "• Mention YOQILGAN/O'CHIRILGAN — funksiyani yoqish yoki o'chirish\n"
    "• Tezlik — xabarlar orasidagi vaqt: 1–10s yoki ⚡ TURBO (0.3s, eng tez; Telegram cheklovi ehtimoli yuqoriroq)\n"
    "• Hisobot paneli — guruhda ko'rinsinmi yoki sizga bot orqali kelsinmi\n\n"
    "💡 <b>Maslahat:</b>\n"
    "• Kichik guruhlarda (50 tagacha) tezroq: 1–3s\n"
    "• Katta guruhlarda (100+) sekinroq: 5–10s (bot buni avtomatik ham moslaydi)\n"
    "• Telegram limitiga tushmaslik uchun online rejimlardan foydalaning\n"
    "• Bot xavfsizlik uchun pauzaga tasodifiy qo'shimcha qo'shadi"
)

HELP_TEXT = (
    "ℹ️ <b>Yordam</b>\n\n"
    "🚀 <b>Boshlash uchun 3 qadam:</b>\n"
    "1️⃣ <b>Akkaunt ulang:</b> 👤 Akkauntlarim bo'limi\n"
    "2️⃣ <b>Odam yig'ing:</b> 🧲 Odam yig'ish orqali guruhlardan user yig'ing\n"
    "3️⃣ <b>Mention qiling:</b> guruhda <code>.r</code>, <code>.m</code> yoki <code>.u</code> buyrug'ini yozing\n\n"
    "📥 Yig'ilgan userlarni yuklab olish pullik tarifda mavjud.\n"
    "🔗 Do'stlaringizni taklif qilib sovg'alar yuting.\n\n"
    "👑 Savollar uchun: @{owner}"
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


class StopS(StatesGroup):
    word = State()


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
    if ref == user.id or (ref and not await get_user(ref)) or not cfg_on("ref_on"):
        ref = None
    await db_exec("INSERT INTO users(id,username,full_name,joined,mention_delay) VALUES(?,?,?,?,?)",
                  (user.id, user.username, user.full_name, time.time(), cfg_int("default_delay")))
    if ref:
        await db_exec("INSERT OR IGNORE INTO referrals(invited_id,referrer_id,created) VALUES(?,?,?)",
                      (user.id, ref, time.time()))
        total = (await db_one("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (ref,)))["c"]
        ru = await get_user(ref)
        avail = max(total - ru["ref_used"], 0)
        await notify_user(ref, f"🎉 Yangi referal qo'shildi! Mavjud: <b>{avail}</b> ta.")
        if any(avail == need for need, _, _ in gift_tiers()):
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


SUB_TEXT_DEFAULT = "📢 <b>Botdan foydalanish uchun quyidagi kanal(lar)ga a'zo bo'ling</b>, so'ng «✅ Tekshirish» tugmasini bosing:"


class Gate(BaseMiddleware):
    """Ro'yxatga olish, ban tekshiruvi va majburiy obuna."""

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user is None or user.is_bot:
            return await handler(event, data)
        chat = event.chat if isinstance(event, Message) else (event.message.chat if event.message else None)
        if chat is not None and chat.type != "private":
            return None
        await bind_owner_if_needed(user)
        target = event if isinstance(event, Message) else event.message
        if not is_staff(user.id):
            if not cfg_on("reg_on") and not await get_user(user.id):
                if isinstance(event, CallbackQuery):
                    await event.answer("🚫 Ro'yxatdan o'tish vaqtincha yopilgan.", show_alert=True)
                else:
                    await event.answer("🚫 Ro'yxatdan o'tish vaqtincha yopilgan.")
                return None
            if cfg_on("maintenance"):
                if isinstance(event, CallbackQuery):
                    await event.answer("🚧 Texnik ishlar", show_alert=True)
                else:
                    await event.answer(T("maint"))
                return None
        await ensure_user(user, event.text if isinstance(event, Message) else None)
        if is_staff(user.id):
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
            await target.answer(T("sub"), reply_markup=sub_kb(miss))
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
    "3️⃣ <b>Mention qiling:</b> guruhda <code>.r</code>, <code>.m</code> yoki <code>.u</code> buyrug'ini yozing\n\n"
    "⚡ UTAG — Yangi imkoniyatlar sari!\n\n"
    "👇 Kerakli bo'limni pastdagi tugmalardan tanlang"
)


async def send_welcome(m: Message) -> None:
    text = T("welcome")
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


@router.message(Command("stop"))
async def cmd_stop(m: Message, state: FSMContext):
    """Botga /stop: faqat shu foydalanuvchining o'z akkauntlaridagi barcha ishlayotgan utaglar to'xtaydi."""
    uid = m.from_user.id
    await reset(state, uid)
    ids = {r["id"] for r in await db_all("SELECT id FROM accounts WHERE owner_id=?", (uid,))}
    n = 0
    for (aid, _cid), ev in list(RUNNING.items()):
        if aid in ids and not ev.is_set():
            ev.set()
            n += 1
    await m.answer(f"🛑 <b>{n}</b> ta utag jarayoni to'xtatildi." if n else "ℹ️ Hozir ishlayotgan utag yo'q.",
                   reply_markup=main_kb(uid))


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
            rows = [[("💳 Karta orqali to'lov", pay_url(p["title"], m.from_user.id))]]
            if cfg("pay_card_text"):
                rows.append([("🏦 Karta rekvizitlari", "paycard")])
            kb = ikb(*rows)
        await m.answer(plan_card(p), reply_markup=kb)


@router.callback_query(F.data == "getfree")
async def cb_getfree(cb: CallbackQuery):
    uid = cb.from_user.id
    p = await get_plan_row("free")
    if not p or not p["active"] or not cfg_on("free_on"):
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
        await restore_bio(client, acc)
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
    if not cfg_on("addacc_on") and not is_staff(uid):
        await m.answer("🚧 Yangi akkaunt ulash vaqtincha yopilgan.", reply_markup=acc_kb())
        return
    plan = await get_active_plan(uid)
    if not plan:
        await m.answer(T("noplan"), reply_markup=no_plan_kb())
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
        await apply_bio_ad(client, acc_id)
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
    if not cfg_on("scrape_on") and not is_staff(uid):
        await m.answer("🚧 Odam yig'ish vaqtincha o'chirilgan. Keyinroq urinib ko'ring.")
        return
    plan = await get_active_plan(uid)
    if not plan:
        await m.answer(T("noplan"), reply_markup=no_plan_kb())
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
    if not cfg_on("export_on") and not is_staff(uid):
        await cb.answer("🚧 Yuklab olish vaqtincha o'chirilgan.", show_alert=True)
        return
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
    if not cfg_on("ref_on") and not is_staff(uid):
        await m.answer("🚧 Referal tizimi vaqtincha o'chirilgan.")
        return
    total = (await db_one("SELECT COUNT(*) c FROM referrals WHERE referrer_id=?", (uid,)))["c"]
    u = await get_user(uid)
    used = u["ref_used"]
    avail = max(total - used, 0)
    link = f"https://t.me/{BOT_USERNAME}?start=ref{uid}"
    await m.answer(f"🔗 <b>Referal tizimi</b>\n\nDo'stlaringizni taklif qiling va bonuslarga ega bo'ling!\n\n"
                   f"<b>Sizning shaxsiy linkingiz:</b>\n<code>{link}</code>\n(ustiga bosing, nusxalanadi)\n\n"
                   f"📊 <b>Statistika:</b>\n• Jami takliflar: {total} ta\n• Ishlatilgan: {used} ta\n• Mavjud: {avail} ta")
    for need, title, desc in gift_tiers():
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
    await m.answer(T("help"))


# ───────────── Sozlamalar (mention) ─────────────
def settings_view(u) -> tuple[str, InlineKeyboardMarkup]:
    on = bool(u["mention_on"])
    d = u["mention_delay"]
    state_txt = "YOQILGAN" if on else "O'CHIRILGAN"
    text = (f"⚙️ <b>MENTION SOZLAMALARI</b>\n\n{'🟢' if on else '🔴'} Holat: <b>{state_txt}</b>\n"
            f"⏱ Tezlik: <b>{'⚡ 0.3 soniya (TURBO)' if d <= 0 else f'{d} soniya'}</b>\n\n<i>Katta guruhlarda bot pauzani avtomatik kattalashtiradi.</i>\n\n"
            f"👇 Kerakli sozlamani tanlang:")
    toggle = ("✅ MENTION YOQILGAN (o'chirish uchun bosing)" if on else "❌ MENTION O'CHIRILGAN (yoqish uchun bosing)")
    try:
        panel_on = bool(u["mention_panel"])
    except (KeyError, IndexError):
        panel_on = True
    ptoggle = ("📊 Guruhda hisobot: YOQILGAN" if panel_on else "📊 Guruhda hisobot: O'CHIRILGAN (botga keladi)")
    text += f"\n📊 Hisobot: <b>{'guruhda' if panel_on else 'bot orqali sizga'}</b>"
    try:
        sw = (u["stop_word"] or "").strip()
    except (KeyError, IndexError):
        sw = ""
    text += f"\n🛑 Stop so'zi: <b>{esc(sw) if sw else 'belgilanmagan'}</b> (/stop va .su doim ishlaydi)"
    row1 = [(("✅ " if d == i else "") + f"{i}s", f"std:{i}") for i in range(1, 6)]
    row2 = [(("✅ " if d == i else "") + f"{i}s", f"std:{i}") for i in range(6, 11)]
    row0 = [(("✅ " if d <= 0 else "") + "⚡ 0.3s TURBO", "std:0")]
    return text, ikb([(toggle, "stt")], [(ptoggle, "stp")], [(f"🛑 Stop so'zi: {sw or 'belgilash'}", "stw")], [("--- ⏱ TEZLIK (sekund) ---", "noop")], row0, row1, row2,
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


@router.callback_query(F.data.in_({"stt", "stp"}) | F.data.startswith("std:"))
async def cb_settings(cb: CallbackQuery):
    uid = cb.from_user.id
    if cb.data == "stt":
        await db_exec("UPDATE users SET mention_on=1-mention_on WHERE id=?", (uid,))
    elif cb.data == "stp":
        await db_exec("UPDATE users SET mention_panel=1-COALESCE(mention_panel,1) WHERE id=?", (uid,))
    else:
        await db_exec("UPDATE users SET mention_delay=? WHERE id=?", (min(max(int(cb.data.split(":")[1]), 0), 10), uid))
    u = await get_user(uid)
    text, kb = settings_view(u)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass
    await cb.answer("Saqlandi ✅")


@router.callback_query(F.data == "stw")
async def cb_stopword(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(StopS.word)
    await cb.message.answer(
        "🛑 <b>O'z stop so'zingiz</b>\n\nGuruhda utag ketayotganda shu so'zni yozsangiz, utag darhol to'xtaydi. "
        "Faqat <b>sizning akkauntingiz</b> yozgan so'z hisobga olinadi, boshqalarniki emas.\n\n"
        "Masalan: <code>.x</code> yoki <code>toxta</code> (1–20 belgi, bo'sh joysiz).\n"
        "<code>/stop</code> va <code>.su</code> har doim ishlaydi.\n\n"
        "Yangi so'zni yuboring. O'chirish uchun <code>-</code> yuboring.", reply_markup=cancel_kb())


@router.message(StopS.word)
async def stopword_set(m: Message, state: FSMContext):
    w = (m.text or "").strip()
    if w == "-":
        await db_exec("UPDATE users SET stop_word='' WHERE id=?", (m.from_user.id,))
        await state.clear()
        await m.answer("✅ Stop so'zi o'chirildi (/stop va .su ishlayveradi).", reply_markup=main_kb(m.from_user.id))
        return
    if not valid_stop_word(w):
        await m.answer("❌ So'z yaroqsiz. 1–20 belgi, bo'sh joysiz bo'lsin va .r .m .u .su /start /stop bilan bir xil bo'lmasin.")
        return
    await db_exec("UPDATE users SET stop_word=? WHERE id=?", (w, m.from_user.id))
    await state.clear()
    await m.answer(f"✅ Stop so'zi saqlandi: <b>{esc(w)}</b>\nEndi guruhda utag paytida shuni yozsangiz, to'xtaydi.",
                   reply_markup=main_kb(m.from_user.id))


@router.callback_query(F.data == "stg")
async def cb_guide(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer(T("guide"), reply_markup=ikb([("🔙 Sozlamalarga qaytish", "stback")]))


@router.callback_query(F.data == "stback")
async def cb_stback(cb: CallbackQuery):
    await cb.answer()
    u = await get_user(cb.from_user.id)
    text, kb = settings_view(u)
    await cb.message.answer(text, reply_markup=kb)


# ══════════════════════════ OWNER / ADMIN PANEL ══════════════════════════
admin.message.filter(lambda m: is_staff(m.from_user.id))
admin.callback_query.filter(lambda c: is_staff(c.from_user.id))


async def owner_only(cb: CallbackQuery) -> bool:
    if is_owner(cb.from_user.id):
        return True
    await cb.answer("🔒 Bu bo'lim faqat bot egasi uchun.", show_alert=True)
    return False

PLAN_FIELDS = {"title": ("Nomi", str), "price": ("Narx (so'm)", int), "days": ("Muddat (kun)", int),
               "max_accounts": ("Maks. akkaunt", int), "scrape_daily": ("Kunlik odam yig'ish (-1 = ∞)", int),
               "mention_daily": ("Kunlik mention (-1 = ∞)", int), "sort": ("Tartib raqami", int)}


def admin_home_kb(uid: int) -> InlineKeyboardMarkup:
    rows = [[("📊 Statistika", "ad:stats"), ("💹 Hisobot", "ad:rep")],
            [("👥 Foydalanuvchilar", "ad:users:0"), ("🔎 Qidirish", "ad:find")],
            [("💰 Tariflar", "ad:pl"), ("🎟 Promokodlar", "ad:pr")],
            [("📢 E'lon yuborish", "ad:bc"), ("📌 Majburiy obuna", "ad:ch")],
            [("🎁 Referal giftlar", "ad:gf"), ("🎲 Gift o'yini", "ad:gift")],
            [("⏱ Hammaga kun qo'shish", "ad:massd"), ("🛡 Akkauntlar", "ad:acc")]]
    if is_owner(uid):
        rows += [[("⚙️ Bot sozlamalari", "ad:set"), ("📝 Matnlar", "ad:tx")],
                 [("🧹 Tozalash", "ad:cl"), ("💾 Backup", "ad:bk")],
                 [("📤 Userlar CSV", "ad:csv"), ("📜 Tarix", "ad:log")],
                 [("🤖 Reaksiya botlari", "ad:rb"), ("👮 Adminlar va ega", "ad:adm")]]
    else:
        rows.append([("📜 Tarix", "ad:log")])
    return ikb(*rows)


async def home_text() -> str:
    n = (await db_one("SELECT COUNT(*) c FROM users"))["c"]
    flags = []
    if cfg_on("maintenance"):
        flags.append("🚧 TEXNIK ISHLAR YOQILGAN")
    for k, lbl in (("scrape_on", "yig'ish"), ("mention_on", "mention"), ("free_on", "bepul tarif"), ("reg_on", "ro'yxat")):
        if not cfg_on(k):
            flags.append(f"⛔ {lbl} o'chiq")
    return (f"👑 <b>Admin panel</b>\n\n👥 Userlar: <b>{n}</b> | 🔌 Sessiyalar: {len(CLIENTS)}\n"
            f"👑 Ega: @{esc(OWNER_USERNAME)}" + ("\n" + "\n".join(flags) if flags else ""))


@admin.message(F.text == B_ADMIN)
async def admin_open(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    await m.answer(await home_text(), reply_markup=admin_home_kb(m.from_user.id))


@admin.callback_query(F.data == "ad:home")
async def ad_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    await cb.message.edit_text(await home_text(), reply_markup=admin_home_kb(cb.from_user.id))


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
    paid = (await db_one("SELECT COALESCE(SUM(amount),0) s FROM payments WHERE user_id=?", (uid,)))["s"]
    sc, mn = await usage_get(uid)
    tar = (f"{esc(plan['title'])} ({fmt_left(u['plan_until'])})" if plan and active else "❌ yo'q")
    role = " 👑 EGA" if is_owner(uid) else (" 👮 ADMIN" if uid in ADMINS else "")
    text = (f"👤 <b>{esc(u['full_name'] or '—')}</b>{role}\n🆔 <code>{uid}</code> | {('@' + u['username']) if u['username'] else '—'}\n"
            f"📅 Qo'shilgan: {fmt_date(u['joined'])}\n💳 Tarif: {tar}\n👤 Akkauntlar: {accs} | 📥 Yig'ilgan: {coll}\n"
            f"📈 Bugun: yig'ish {sc}, mention {mn}\n💰 To'lagan: {money(paid)}\n"
            f"🔗 Referal: {total_ref} (ishlatilgan {u['ref_used']})\n🚫 Ban: {'HA' if u['banned'] else 'yo`q'}")
    perks = []
    if u["bonus_acc"]:
        perks.append(f"+{u['bonus_acc']} akkaunt")
    if u["bonus_mention"]:
        perks.append(f"+{u['bonus_mention']} mention/kun")
    if u["bonus_scrape"]:
        perks.append(f"+{u['bonus_scrape']} yig'ish/kun")
    if u["bonus_export"]:
        perks.append("📥 yuklab olish ruxsati")
    if perks:
        text += "\n🌟 <b>Maxsus ustunliklar:</b> " + ", ".join(perks)
    ru = await react_until(uid)
    if not ru:
        rx_txt = "❌ yo'q"
    elif is_owner(uid):
        rx_txt = "cheksiz"
    else:
        rx_txt = fmt_left(ru)
    dm_rem = await dm_remaining(uid)
    dm_row = await db_one("SELECT quota, used FROM dm_access WHERE user_id=?", (uid,))
    if is_owner(uid):
        dm_txt = "∞"
    elif dm_row:
        dm_txt = f"{dm_rem} qoldi (ishlatilgan {dm_row['used']}/{dm_row['quota']})"
    else:
        dm_txt = "❌ yo'q"
    text += f"\n❤️ Reaksiya: {rx_txt}\n✉️ Xabar limiti: {dm_txt}"
    rows = [[("✅ Unban" if u["banned"] else "🚫 Ban", f"ad:{'unban' if u['banned'] else 'ban'}:{uid}")],
            [("🏷 Tarif berish", f"ad:gp:{uid}"), ("⏱ Kun qo'shish", f"ad:ad:{uid}")],
            [("🚫 Tarifni olish", f"ad:tk:{uid}"), ("✉️ Xabar yuborish", f"ad:um:{uid}")],
            [("➕ Akkaunt limiti", f"ad:pk:{uid}:bonus_acc"), ("➕ Mention limiti", f"ad:pk:{uid}:bonus_mention")],
            [("➕ Yig'ish limiti", f"ad:pk:{uid}:bonus_scrape"),
             (f"📥 Yuklab olish: {yn(u['bonus_export'])}", f"ad:px:{uid}")],
            [("♻️ Bugungi limitni nolga", f"ad:rs:{uid}:usage"), ("🎁 Bepulni qayta ochish", f"ad:rs:{uid}:free")],
            [("🌟 Ustunliklarni olib tashlash", f"ad:rs:{uid}:perks"), ("👤 Akkauntlari", f"ad:ua:{uid}")]]
    rows.append([("❤️ Reaksiya muddati", f"ad:rx:{uid}"), ("✉️ Xabar limiti", f"ad:dq:{uid}")])
    for need, _, _ in gift_tiers():
        rows.append([(f"🎁 Gift berildi (-{need})", f"ad:rg:{uid}:{need}")])
    rows.append([("🗑 Userni o'chirish", f"ad:udel:{uid}"), ("🔙 Orqaga", "ad:users:0")])
    return text, ikb(*rows)


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
    if act == "ban" and (is_owner(uid) or (uid in ADMINS and not is_owner(cb.from_user.id))):
        await cb.answer("🔒 Egani yoki adminni bloklab bo'lmaydi.", show_alert=True)
        return
    await audit(cb.from_user.id, act, str(uid))
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


PENDING_GIVE: dict[int, tuple[int, str, int]] = {}


async def finish_give(actor: int, uid: int, key: str, days: int, paid: bool) -> str:
    p = await get_plan_row(key)
    until = await activate_plan(uid, key, days)
    await notify_user(uid, f"🎉 Sizga <b>{esc(p['title'])}</b> tarifi berildi!\n⏳ {days} kun ({fmt_date(until)} gacha)")
    amount = 0
    if paid and p["price"] > 0:
        amount = int(p["price"] * days / max(p["days"], 1))
        await db_exec("INSERT INTO payments(user_id,plan_key,amount,days,ts,by_id) VALUES(?,?,?,?,?,?)",
                      (uid, key, amount, days, time.time(), actor))
    await audit(actor, "give_plan", f"{uid} {key} {days}k paid={amount}")
    return f"✅ Tarif berildi: {esc(p['title'])} — {days} kun" + (f" | 💰 {money(amount)} daromadga yozildi" if amount else "")


@admin.message(AdminS.give_days)
async def ad_give_days(m: Message, state: FSMContext):
    if not (m.text or "").strip().lstrip("-").isdigit():
        await m.answer("❌ Raqam yuboring.")
        return
    d = await state.get_data()
    await state.clear()
    p = await get_plan_row(d["key"])
    days = int(m.text) or p["days"]
    await m.answer("👑", reply_markup=main_kb(OWNER_ID))
    if p["price"] > 0:
        PENDING_GIVE[m.from_user.id] = (d["uid"], d["key"], days)
        amount = int(p["price"] * days / max(p["days"], 1))
        await m.answer(f"💰 <b>{esc(p['title'])}</b> — {days} kun. Hisoblangan summa: <b>{money(amount)}</b>\n"
                       f"To'lov qilinganmi?",
                       reply_markup=ikb([("💰 Ha, pullik (daromadga yoziladi)", "ad:gpay:1")],
                                        [("🎁 Yo'q, sovg'a / bepul", "ad:gpay:0")]))
        return
    msg = await finish_give(m.from_user.id, d["uid"], d["key"], days, False)
    card = await user_card(d["uid"])
    await m.answer(msg)
    await m.answer(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:gpay:[01]$"))
async def ad_give_pay(cb: CallbackQuery):
    pend = PENDING_GIVE.pop(cb.from_user.id, None)
    if not pend:
        await cb.answer("Muddati o'tgan, qaytadan urinib ko'ring.", show_alert=True)
        return
    uid, key, days = pend
    msg = await finish_give(cb.from_user.id, uid, key, days, cb.data.endswith("1"))
    await cb.answer("✅")
    card = await user_card(uid)
    await cb.message.edit_text(msg + "\n\n" + card[0], reply_markup=card[1])


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
    if not await owner_only(cb):
        return
    await cb.answer()
    await render_plans(cb)


async def render_plans(cb: CallbackQuery) -> None:
    plans = await db_all("SELECT * FROM plans ORDER BY sort")
    rows = [[(f"{'✅' if p['active'] else '⛔'} {p['title']} — {p['price']} so'm", f"ad:pls:{p['key']}")] for p in plans]
    rows.append([("➕ Yangi tarif", "ad:pln")])
    rows.append([("🔙 Orqaga", "ad:home")])
    await cb.message.edit_text("💰 <b>Tariflar</b> (tahrirlash uchun tanlang):", reply_markup=ikb(*rows))


async def plan_edit_view(key: str):
    p = await get_plan_row(key)
    rows = [[(f"✏️ {lbl}", f"ad:pe:{key}:{f}")] for f, (lbl, _) in PLAN_FIELDS.items()]
    rows.append([(f"📥 Yuklab olish: {yn(p['can_export'])} (almashtirish)", f"ad:pt:{key}:can_export")])
    rows.append([(f"🔌 Faol: {yn(p['active'])} (almashtirish)", f"ad:pt:{key}:active")])
    if key != "free":
        rows.append([("🗑 Tarifni o'chirish", f"ad:pld:{key}")])
    rows.append([("🔙 Orqaga", "ad:pl")])
    return plan_card(p), ikb(*rows)


@admin.callback_query(F.data.startswith("ad:pls:"))
async def ad_plan_view(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer()
    text, kb = await plan_edit_view(cb.data.split(":")[2])
    await cb.message.edit_text(text, reply_markup=kb)


@admin.callback_query(F.data.startswith("ad:pt:"))
async def ad_plan_toggle(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    _, _, key, field = cb.data.split(":")
    if field not in ("can_export", "active"):
        return
    await db_exec(f"UPDATE plans SET {field}=1-{field} WHERE key=?", (key,))
    await cb.answer("Saqlandi ✅")
    text, kb = await plan_edit_view(key)
    await cb.message.edit_text(text, reply_markup=kb)


@admin.callback_query(F.data.startswith("ad:pe:"))
async def ad_plan_edit(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
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
    await audit(m.from_user.id, "plan_edit", f"{d['key']} {field}={v}")
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
    await m.answer("👑", reply_markup=main_kb(OWNER_ID))
    rows = []
    for key, lbl in SEGMENTS.items():
        n = len(await seg_ids(key))
        rows.append([(f"{lbl} ({n})", f"ad:bcgo:{m.message_id}:{key}")])
    rows.append([("❌ Bekor", "ad:home")])
    await m.reply("👆 Shu xabar kimlarga yuborilsin?", reply_markup=ikb(*rows))


SEGMENTS = {"all": "👥 Hammaga", "paid": "💳 Pullik tarifdagilar", "free": "🎁 Bepul tarifdagilar",
            "active": "🟢 Faol tarifdagilar", "expired": "⌛ Tarifi tugaganlar", "noplan": "🆕 Tarif olmaganlar"}


async def seg_ids(seg: str) -> list[int]:
    now = time.time()
    q = {"all": ("SELECT id FROM users WHERE banned=0", ()),
         "paid": ("SELECT id FROM users WHERE banned=0 AND plan_until>? AND plan_key NOT IN ('free','')", (now,)),
         "free": ("SELECT id FROM users WHERE banned=0 AND plan_until>? AND plan_key='free'", (now,)),
         "active": ("SELECT id FROM users WHERE banned=0 AND plan_until>?", (now,)),
         "expired": ("SELECT id FROM users WHERE banned=0 AND plan_until>0 AND plan_until<=?", (now,)),
         "noplan": ("SELECT id FROM users WHERE banned=0 AND plan_until=0", ())}.get(seg, ("SELECT id FROM users WHERE banned=0", ()))
    return [r["id"] for r in await db_all(*q)]


async def send_to_ids(ids: list[int], fn) -> tuple[int, int]:
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
        except Exception:  # noqa: BLE001
            fail += 1
        await asyncio.sleep(0.05)
    return ok, fail


async def send_all(owner_chat: int, fn, seg: str = "all") -> tuple[int, int]:
    return await send_to_ids(await seg_ids(seg), fn)


@admin.callback_query(F.data.startswith("ad:bcgo:"))
async def ad_bc_go(cb: CallbackQuery):
    _, _, mid, seg = cb.data.split(":")
    mid = int(mid)
    await cb.answer("Yuborilmoqda...")
    await cb.message.edit_text(f"⏳ Yuborilmoqda... ({SEGMENTS.get(seg, seg)})")
    await audit(cb.from_user.id, "broadcast", seg)
    actor = cb.from_user.id

    async def job():
        ok, fail = await send_all(actor, lambda uid: BOT.copy_message(uid, actor, mid), seg)
        await notify_user(actor, f"📢 E'lon yakunlandi ({SEGMENTS.get(seg, seg)}): ✅ {ok} | ❌ {fail}")
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
    if not await owner_only(cb):
        return
    await cb.answer()
    await send_backup(cb.from_user.id)


# ══════════════════════════ ADMIN PANEL — YANGI IMKONIYATLAR ══════════════════════════
class AdminS2(StatesGroup):
    set_num = State()
    text_edit = State()
    promo_new = State()
    gift_add = State()
    plan_new = State()
    admin_add = State()
    owner_set = State()
    user_msg = State()
    perk_val = State()
    mass_days = State()


class PromoS(StatesGroup):
    code = State()


def money(n: int) -> str:
    return f"{int(n):,}".replace(",", " ") + " so'm"


# ── Foydalanuvchi tomoni: promokod va karta rekvizitlari ──
async def redeem_promo(uid: int, code: str) -> str:
    code = (code or "").strip().upper()
    pr = await db_one("SELECT * FROM promos WHERE code=?", (code,))
    if not pr or not pr["active"]:
        return "❌ Bunday promokod topilmadi yoki o'chirilgan."
    if pr["max_uses"] and pr["used"] >= pr["max_uses"]:
        return "❌ Bu promokod limiti tugagan."
    if await db_one("SELECT 1 FROM promo_uses WHERE code=? AND user_id=?", (code, uid)):
        return "⚠️ Siz bu promokodni allaqachon ishlatgansiz."
    p = await get_plan_row(pr["plan_key"])
    if not p:
        return "❌ Promokod tarifi mavjud emas. Egaga xabar bering."
    until = await activate_plan(uid, pr["plan_key"], pr["days"])
    await db_exec("INSERT INTO promo_uses(code,user_id,ts) VALUES(?,?,?)", (code, uid, time.time()))
    await db_exec("UPDATE promos SET used=used+1 WHERE code=?", (code,))
    await audit(uid, "promo", code)
    return f"🎉 Promokod qabul qilindi!\n💳 Tarif: <b>{esc(p['title'])}</b>\n⏳ {pr['days']} kun ({fmt_date(until)} gacha)"


@router.message(F.text == B_PROMO)
async def promo_start(m: Message, state: FSMContext):
    await reset(state, m.from_user.id)
    await state.set_state(PromoS.code)
    await m.answer("🎟 Promokodingizni yuboring:", reply_markup=cancel_kb())


@router.message(PromoS.code)
async def promo_enter(m: Message, state: FSMContext):
    res = await redeem_promo(m.from_user.id, m.text or "")
    if res.startswith("🎉"):
        await state.clear()
        await m.answer(res, reply_markup=main_kb(m.from_user.id))
    else:
        await m.answer(res + "\n\nQayta yuboring yoki «❌ Bekor qilish» ni bosing.")


@router.callback_query(F.data == "paycard")
async def cb_paycard(cb: CallbackQuery):
    await cb.answer()
    txt = cfg("pay_card_text")
    if txt:
        await cb.message.answer(txt)


# ── Hisobot ──
@admin.callback_query(F.data == "ad:rep")
async def ad_report(cb: CallbackQuery):
    await cb.answer()
    now = time.time()
    day0 = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

    async def s(since: float):
        r = await db_one("SELECT COALESCE(SUM(amount),0) a, COUNT(*) c FROM payments WHERE ts>=?", (since,))
        return r["a"], r["c"]
    t, w, mo, al = await s(day0), await s(now - 7 * 86400), await s(now - 30 * 86400), await s(0)
    by_plan = await db_all("SELECT plan_key, COUNT(*) c, SUM(amount) a FROM payments GROUP BY plan_key ORDER BY a DESC LIMIT 6")
    days = []
    for i in range(6, -1, -1):
        st = day0 - i * 86400
        n = (await db_one("SELECT COUNT(*) c FROM users WHERE joined>=? AND joined<?", (st, st + 86400)))["c"]
        days.append(f"{datetime.fromtimestamp(st, TZ):%d.%m} — {'█' * min(n, 20)} {n}")
    top = await db_all("SELECT referrer_id, COUNT(*) c FROM referrals GROUP BY referrer_id ORDER BY c DESC LIMIT 5")
    txt = (f"💹 <b>Daromad hisoboti</b>\n\n📅 Bugun: <b>{money(t[0])}</b> ({t[1]} ta)\n🗓 7 kun: <b>{money(w[0])}</b> ({w[1]} ta)\n"
           f"📆 30 kun: <b>{money(mo[0])}</b> ({mo[1]} ta)\n💰 Jami: <b>{money(al[0])}</b> ({al[1]} ta)\n")
    if by_plan:
        txt += "\n🏷 <b>Tariflar bo'yicha:</b>\n" + "\n".join(f"• {esc(r['plan_key'])}: {r['c']} ta — {money(r['a'] or 0)}" for r in by_plan) + "\n"
    txt += "\n🆕 <b>Oxirgi 7 kunda yangi userlar:</b>\n" + "\n".join(days)
    if top:
        txt += "\n\n🔗 <b>Top referalchilar:</b>\n" + "\n".join(f"• <code>{r['referrer_id']}</code> — {r['c']} ta" for r in top)
    await cb.message.edit_text(txt, reply_markup=ikb([("🔙 Orqaga", "ad:home")]))


# ── Bot sozlamalari (yoqish/o'chirish va raqamlar) ──
TOGGLES = [("maintenance", "🚧 Texnik ishlar rejimi"), ("reg_on", "🆕 Yangi userlar kirishi"),
           ("free_on", "🎁 Bepul tarif olish"), ("scrape_on", "🧲 Odam yig'ish"), ("mention_on", "📣 Mention"),
           ("export_on", "📥 Yuklab olish"), ("addacc_on", "👤 Akkaunt ulash"), ("ref_on", "🔗 Referal tizimi"),
           ("bio_on", "🤖 Ulangan akkaunt bioga reklama"), ("react_on", "❤️ Reaksiya xizmati"),
           ("dm_on", "✉️ Shaxsiy xabar xizmati"), ("sign_on", "🏷 Matnlarga bot imzosini qo'shish")]
NUMS = {"max_scrape": ("Bir marta yig'iladigan maks. user", 100, 500000),
        "max_mention": ("Bir marta mention qilinadigan maks. a'zo", 10, 100000),
        "min_delay": ("Minimal tezlik (sekund)", 1, 10), "max_delay": ("Maksimal tezlik (sekund)", 1, 60),
        "default_delay": ("Yangi userlar uchun standart tezlik (s, 0 = TURBO 0.3s)", 0, 10),
        "dm_min_delay": ("Shaxsiy xabar: minimal pauza (s)", 1, 120),
        "dm_max_delay": ("Shaxsiy xabar: maksimal pauza (s)", 1, 300)}


def settings_admin_view() -> tuple[str, InlineKeyboardMarkup]:
    rows = []
    for k, lbl in TOGGLES:
        on = cfg_on(k)
        icon = ("🔴 YOQILGAN" if on else "⚪️ o'chiq") if k == "maintenance" else ("🟢 yoqilgan" if on else "🔴 o'chirilgan")
        rows.append([(f"{lbl}: {icon}", f"ad:st:{k}")])
    for k, (lbl, _, _) in NUMS.items():
        rows.append([(f"✏️ {lbl}: {cfg_int(k)}", f"ad:sn:{k}")])
    rows.append([("🔙 Orqaga", "ad:home")])
    return ("⚙️ <b>Bot sozlamalari</b>\n\nBu yerdan botni kod yozmasdan boshqarasiz. Tugmani bossangiz o'zgaradi.\n"
            "🚧 Texnik ishlar yoqilsa, oddiy userlar botdan foydalana olmaydi (siz va adminlar ishlayveradi)."), ikb(*rows)


@admin.callback_query(F.data == "ad:set")
async def ad_settings(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer()
    txt, kb = settings_admin_view()
    await cb.message.edit_text(txt, reply_markup=kb)


@admin.callback_query(F.data.startswith("ad:st:"))
async def ad_setting_toggle(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    k = cb.data.split(":")[2]
    if k not in dict(TOGGLES):
        return
    await cfg_set(k, "0" if cfg_on(k) else "1")
    await audit(cb.from_user.id, "setting", f"{k}={cfg(k)}")
    await cb.answer("Saqlandi ✅")
    txt, kb = settings_admin_view()
    await cb.message.edit_text(txt, reply_markup=kb)


@admin.callback_query(F.data.startswith("ad:sn:"))
async def ad_setting_num(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    k = cb.data.split(":")[2]
    if k not in NUMS:
        return
    lbl, lo, hi = NUMS[k]
    await cb.answer()
    await state.set_state(AdminS2.set_num)
    await state.update_data(key=k)
    await cb.message.answer(f"✏️ <b>{lbl}</b>\nHozirgi: <b>{cfg_int(k)}</b>\nYangi qiymat ({lo} … {hi}) yuboring:", reply_markup=cancel_kb())


@admin.message(AdminS2.set_num)
async def ad_setting_num_do(m: Message, state: FSMContext):
    d = await state.get_data()
    lbl, lo, hi = NUMS[d["key"]]
    t = (m.text or "").strip()
    if not t.isdigit() or not (lo <= int(t) <= hi):
        await m.answer(f"❌ {lo} dan {hi} gacha butun son yuboring.")
        return
    await state.clear()
    await cfg_set(d["key"], t)
    await audit(m.from_user.id, "setting", f"{d['key']}={t}")
    txt, kb = settings_admin_view()
    await m.answer("✅ Saqlandi", reply_markup=main_kb(OWNER_ID))
    await m.answer(txt, reply_markup=kb)


# ── Matnlar (start, yordam, to'lov rekvizitlari va h.k.) ──
TEXT_ITEMS = {
    "welcome": ("👋 Start xabari", "t_welcome", "html"),
    "help": ("ℹ️ Yordam matni", "t_help", "html"),
    "noplan": ("⛔ «Tarif yo'q» xabari", "t_noplan", "html"),
    "sub": ("📢 Majburiy obuna xabari", "t_sub", "html"),
    "guide": ("📖 Mention qo'llanmasi", "t_guide", "html"),
    "maint": ("🚧 Texnik ishlar xabari", "t_maint", "html"),
    "paycard": ("🏦 Karta rekvizitlari", "pay_card_text", "html"),
    "payuser": ("💳 To'lov qabul qiluvchi @username", "pay_username", "user"),
    "bioad": ("🤖 Bio reklama matni (70 belgigacha)", "bio_ad", "plain"),
    "rnd": ("🎲 .r uchun QO'SHIMCHA gaplar (asosiy baza ustiga)", "random_texts", "plain"),
    "sign": ("🏷 Bot imzosi (tarqatilgan matn oxiriga)", "sign_text", "plain"),
}


def text_current(name: str) -> str:
    _, key, kind = TEXT_ITEMS[name]
    if name in ("welcome", "help", "noplan", "sub", "guide", "maint"):
        return T(name)
    if name == "rnd":
        return "\n".join(custom_texts())   # asosiy baza (kodda) alohida; bu yerda faqat qo'shimchalar
    return cfg(key)


@admin.callback_query(F.data == "ad:tx")
async def ad_texts(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer()
    rows = [[(lbl, f"ad:txv:{n}")] for n, (lbl, _, _) in TEXT_ITEMS.items()]
    rows.append([("🔙 Orqaga", "ad:home")])
    await cb.message.edit_text("📝 <b>Matnlar</b>\n\nBot xabarlarini kod yozmasdan o'zgartiring. "
                               "Start va yordam matnida <code>{owner}</code> yozsangiz, ega username'i qo'yiladi.", reply_markup=ikb(*rows))


@admin.callback_query(F.data.startswith("ad:txv:"))
async def ad_text_view(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    name = cb.data.split(":")[2]
    if name not in TEXT_ITEMS:
        return
    await cb.answer()
    lbl, key, kind = TEXT_ITEMS[name]
    cur = text_current(name)
    await cb.message.answer(f"<b>{lbl}</b> — hozirgi holati:")
    if cur:
        try:
            await cb.message.answer(cur if kind == "html" else esc(cur))
        except TelegramBadRequest:
            await cb.message.answer(esc(cur))
    else:
        await cb.message.answer("— (bo'sh) —")
    await cb.message.answer("Nima qilamiz?", reply_markup=ikb([("✏️ Tahrirlash", f"ad:txe:{name}")],
                                                              [("♻️ Standartga qaytarish", f"ad:txr:{name}")],
                                                              [("🔙 Matnlar", "ad:tx")]))


@admin.callback_query(F.data.startswith("ad:txr:"))
async def ad_text_reset(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    name = cb.data.split(":")[2]
    if name not in TEXT_ITEMS:
        return
    await cfg_del(TEXT_ITEMS[name][1])
    await audit(cb.from_user.id, "text_reset", name)
    await cb.answer("♻️ Standartga qaytdi", show_alert=True)


@admin.callback_query(F.data.startswith("ad:txe:"))
async def ad_text_edit(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    name = cb.data.split(":")[2]
    if name not in TEXT_ITEMS:
        return
    await cb.answer()
    lbl, _, kind = TEXT_ITEMS[name]
    hint = {"html": "Yangi matnni yuboring (qalin, kursiv, havola formatlash ishlaydi).",
            "user": "Username yuboring (masalan: <code>Mirkamilovic</code>).",
            "plain": "Har bir matnni alohida qatorga yozing."}[kind]
    await state.set_state(AdminS2.text_edit)
    await state.update_data(name=name)
    await cb.message.answer(f"✏️ <b>{lbl}</b>\n\n{hint}", reply_markup=cancel_kb())


@admin.message(AdminS2.text_edit)
async def ad_text_edit_do(m: Message, state: FSMContext):
    d = await state.get_data()
    name = d["name"]
    lbl, key, kind = TEXT_ITEMS[name]
    if kind == "html":
        val = m.html_text or ""
    else:
        val = (m.text or "").strip()
    if kind == "user":
        val = val.lstrip("@")
        if not re.match(r"^[A-Za-z]\w{3,31}$", val):
            await m.answer("❌ Username noto'g'ri. Qayta yuboring.")
            return
    if not val or len(val) > 3800:
        await m.answer("❌ Matn bo'sh yoki juda uzun (3800 belgigacha).")
        return
    if kind == "html":
        try:
            await m.answer(val.replace("{owner}", OWNER_USERNAME))   # ko'rib chiqish + HTML tekshiruvi
        except TelegramBadRequest as e:
            await m.answer(f"❌ Matnda format xatosi: {esc(str(e))[:150]}")
            return
    await state.clear()
    await cfg_set(key, val)
    await audit(m.from_user.id, "text_edit", name)
    await m.answer("✅ Saqlandi (yuqoridagi ko'rinishda ishlaydi).", reply_markup=main_kb(OWNER_ID))


# ── Promokodlar ──
@admin.callback_query(F.data == "ad:pr")
async def ad_promos(cb: CallbackQuery):
    await cb.answer()
    await render_promos(cb)


async def render_promos(cb: CallbackQuery) -> None:
    rows_db = await db_all("SELECT * FROM promos ORDER BY created DESC LIMIT 30")
    rows = [[(f"{'✅' if r['active'] else '⛔'} {r['code']} | {r['plan_key']} {r['days']}k | {r['used']}/{r['max_uses'] or '∞'}",
              f"ad:prv:{r['code']}")] for r in rows_db]
    rows.append([("➕ Yangi promokod", "ad:prn")])
    rows.append([("🔙 Orqaga", "ad:home")])
    await cb.message.edit_text("🎟 <b>Promokodlar</b>\n\nUserlar «🎟 Promokod» tugmasi orqali kiritib, tarif oladi.", reply_markup=ikb(*rows))


@admin.callback_query(F.data.startswith("ad:prv:"))
async def ad_promo_view(cb: CallbackQuery):
    await cb.answer()
    await render_promo(cb, cb.data.split(":", 2)[2])


async def render_promo(cb: CallbackQuery, code: str) -> None:
    r = await db_one("SELECT * FROM promos WHERE code=?", (code,))
    if not r:
        return
    await cb.message.edit_text(
        f"🎟 <code>{esc(code)}</code>\n💳 Tarif: {esc(r['plan_key'])} — {r['days']} kun\n"
        f"👥 Ishlatilgan: {r['used']} / {r['max_uses'] or '∞'}\n🔌 Holat: {yn(r['active'])}",
        reply_markup=ikb([("🔁 Yoqish/o'chirish", f"ad:prt:{code}")], [("🗑 O'chirish", f"ad:prd:{code}")],
                         [("🔙 Orqaga", "ad:pr")]))


@admin.callback_query(F.data.startswith("ad:prt:"))
async def ad_promo_toggle(cb: CallbackQuery):
    code = cb.data.split(":", 2)[2]
    await db_exec("UPDATE promos SET active=1-active WHERE code=?", (code,))
    await cb.answer("Saqlandi ✅")
    await render_promo(cb, code)


@admin.callback_query(F.data.startswith("ad:prd:"))
async def ad_promo_del(cb: CallbackQuery):
    code = cb.data.split(":", 2)[2]
    await db_exec("DELETE FROM promos WHERE code=?", (code,))
    await audit(cb.from_user.id, "promo_del", code)
    await cb.answer("🗑 O'chirildi")
    await render_promos(cb)


@admin.callback_query(F.data == "ad:prn")
async def ad_promo_new(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    plans = await db_all("SELECT key, title FROM plans ORDER BY sort")
    await state.set_state(AdminS2.promo_new)
    await cb.message.answer(
        "🎟 Yangi promokod. Bitta xabarda quyidagicha yozing:\n\n<code>KOD | tarif_kaliti | kun | maks_ishlatish</code>\n\n"
        "Masalan: <code>YANGI30 | start | 7 | 50</code>\n• KOD o'rniga <code>-</code> yozsangiz, tasodifiy kod yaratiladi\n"
        "• maks_ishlatish: <code>0</code> = cheksiz\n\n<b>Tarif kalitlari:</b> " + ", ".join(f"<code>{p['key']}</code>" for p in plans),
        reply_markup=cancel_kb())


@admin.message(AdminS2.promo_new)
async def ad_promo_new_do(m: Message, state: FSMContext):
    parts = [x.strip() for x in (m.text or "").split("|")]
    if len(parts) != 4 or not parts[2].isdigit() or not parts[3].isdigit() or int(parts[2]) <= 0:
        await m.answer("❌ Format noto'g'ri. Misol: <code>YANGI30 | start | 7 | 50</code>")
        return
    code, key, days, mx = parts[0].upper(), parts[1], int(parts[2]), int(parts[3])
    if code in ("-", "AUTO"):
        code = "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    if not re.match(r"^[A-Z0-9_\-]{3,32}$", code):
        await m.answer("❌ Kod 3–32 ta lotin harf/raqamdan iborat bo'lsin.")
        return
    if not await get_plan_row(key):
        await m.answer("❌ Bunday tarif kaliti yo'q.")
        return
    if await db_one("SELECT 1 FROM promos WHERE code=?", (code,)):
        await m.answer("❌ Bu kod allaqachon mavjud.")
        return
    await state.clear()
    await db_exec("INSERT INTO promos(code,plan_key,days,max_uses,used,active,created) VALUES(?,?,?,?,0,1,?)",
                  (code, key, days, mx, time.time()))
    await audit(m.from_user.id, "promo_new", code)
    await m.answer(f"✅ Yaratildi: <code>{code}</code> → {key}, {days} kun, limit: {mx or '∞'}", reply_markup=main_kb(OWNER_ID))


# ── Referal giftlar ──
def save_tiers_json(tiers: list) -> str:
    return json.dumps([[a, b, c] for a, b, c in tiers], ensure_ascii=False)


@admin.callback_query(F.data == "ad:gf")
async def ad_gifts_cfg(cb: CallbackQuery):
    await cb.answer()
    await render_gifts(cb)


async def render_gifts(cb: CallbackQuery) -> None:
    tiers = gift_tiers()
    rows = [[(f"🗑 {need} ta referal", f"ad:gfd:{need}")] for need, _, _ in tiers]
    rows.append([("➕ Gift qo'shish", "ad:gfa")])
    rows.append([("🔙 Orqaga", "ad:home")])
    txt = "🎁 <b>Referal giftlar</b>\n\n" + ("\n\n".join(f"• <b>{need} ta</b> referal → {title}\n{desc}" for need, title, desc in tiers) or "Hozircha yo'q.")
    await cb.message.edit_text(txt, reply_markup=ikb(*rows))


@admin.callback_query(F.data.startswith("ad:gfd:"))
async def ad_gift_del(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    need = int(cb.data.split(":")[2])
    await cfg_set("gift_tiers", save_tiers_json([t for t in gift_tiers() if t[0] != need]) if len(gift_tiers()) > 1 else "[]")
    await cb.answer("🗑 O'chirildi")
    await render_gifts(cb)


@admin.callback_query(F.data == "ad:gfa")
async def ad_gift_add(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    await cb.answer()
    await state.set_state(AdminS2.gift_add)
    await cb.message.answer("🎁 Yangi gift. Bitta xabarda yozing:\n\n<code>referal_soni | sarlavha | tavsif</code>\n\n"
                            "Masalan: <code>50 | 🎁 Super gift | 50 ta do'st taklif qiling va yutib oling!</code>", reply_markup=cancel_kb())


@admin.message(AdminS2.gift_add)
async def ad_gift_add_do(m: Message, state: FSMContext):
    parts = [x.strip() for x in (m.text or "").split("|", 2)]
    if len(parts) != 3 or not parts[0].isdigit() or int(parts[0]) <= 0 or not parts[1] or not parts[2]:
        await m.answer("❌ Format noto'g'ri. Misol: <code>50 | 🎁 Super gift | tavsif</code>")
        return
    tiers = [t for t in gift_tiers() if t[0] != int(parts[0])] + [(int(parts[0]), parts[1], parts[2])]
    await state.clear()
    await cfg_set("gift_tiers", save_tiers_json(sorted(tiers)))
    await m.answer("✅ Saqlandi", reply_markup=main_kb(OWNER_ID))


# ── Yangi tarif / tarifni o'chirish ──
@admin.callback_query(F.data == "ad:pln")
async def ad_plan_new(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    await cb.answer()
    await state.set_state(AdminS2.plan_new)
    await cb.message.answer(
        "➕ Yangi tarif. Bitta xabarda yozing:\n\n<code>kalit | nom | narx | kun | akkaunt | yig'ish/kun | mention/kun | yuklab(1/0)</code>\n\n"
        "Masalan: <code>gold | GOLD | 79000 | 30 | 7 | -1 | 20000 | 1</code>\n(-1 = cheksiz)", reply_markup=cancel_kb())


@admin.message(AdminS2.plan_new)
async def ad_plan_new_do(m: Message, state: FSMContext):
    parts = [x.strip() for x in (m.text or "").split("|")]
    try:
        if len(parts) != 8:
            raise ValueError
        key, title = parts[0].lower(), parts[1]
        price, days, accs, sc, mn, ex = (int(x) for x in parts[2:])
        if not re.match(r"^[a-z0-9_]{2,20}$", key) or not title or days <= 0 or accs <= 0 or ex not in (0, 1):
            raise ValueError
    except ValueError:
        await m.answer("❌ Format noto'g'ri. Misol: <code>gold | GOLD | 79000 | 30 | 7 | -1 | 20000 | 1</code>")
        return
    if await get_plan_row(key):
        await m.answer("❌ Bu kalit band.")
        return
    mx = (await db_one("SELECT COALESCE(MAX(sort),0) s FROM plans"))["s"]
    await state.clear()
    await db_exec("INSERT INTO plans VALUES(?,?,?,?,?,?,?,?,?,?)", (key, title, price, days, accs, ex, sc, mn, 1, mx + 1))
    await audit(m.from_user.id, "plan_new", key)
    await m.answer(f"✅ Tarif qo'shildi: {esc(title)}", reply_markup=main_kb(OWNER_ID))


@admin.callback_query(F.data.startswith("ad:pld:"))
async def ad_plan_del(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    key = cb.data.split(":")[2]
    if key == "free":
        await cb.answer("Bepul tarifni o'chirib bo'lmaydi.", show_alert=True)
        return
    n = (await db_one("SELECT COUNT(*) c FROM users WHERE plan_key=? AND plan_until>?", (key, time.time())))["c"]
    if n:
        await cb.answer(f"Bu tarifda {n} ta faol user bor. Avval «Faol» ni o'chiring (yashiring).", show_alert=True)
        return
    await db_exec("DELETE FROM plans WHERE key=?", (key,))
    await audit(cb.from_user.id, "plan_del", key)
    await cb.answer("🗑 O'chirildi")
    await render_plans(cb)


# ── Foydalanuvchi ustida amallar ──
@admin.callback_query(F.data.regexp(r"^ad:um:\d+$"))
async def ad_user_msg(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(AdminS2.user_msg)
    await state.update_data(uid=int(cb.data.split(":")[2]))
    await cb.message.answer("✉️ Userga yuboriladigan xabarni yuboring (matn, rasm, istalgani):", reply_markup=cancel_kb())


@admin.message(AdminS2.user_msg)
async def ad_user_msg_do(m: Message, state: FSMContext):
    d = await state.get_data()
    await state.clear()
    try:
        await BOT.copy_message(d["uid"], m.chat.id, m.message_id)
        res = "✅ Yuborildi"
    except Exception as e:  # noqa: BLE001
        res = f"❌ Yuborilmadi: {esc(str(e))[:100]}"
    await m.answer(res, reply_markup=main_kb(OWNER_ID))


@admin.callback_query(F.data.regexp(r"^ad:pk:\d+:(bonus_acc|bonus_mention|bonus_scrape)$"))
async def ad_perk(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    _, _, uid, field = cb.data.split(":")
    u = await get_user(int(uid))
    names = {"bonus_acc": "qo'shimcha AKKAUNT soni", "bonus_mention": "qo'shimcha KUNLIK MENTION", "bonus_scrape": "qo'shimcha KUNLIK YIG'ISH"}
    await state.set_state(AdminS2.perk_val)
    await state.update_data(uid=int(uid), field=field)
    await cb.message.answer(f"🌟 <b>{names[field]}</b>\nHozirgi: <b>{u[field] or 0}</b>\nYangi qiymatni yuboring (0 = olib tashlash).\n"
                            f"<i>Eslatma: kunlik limit tarifda «cheksiz» bo'lsa, bonus kerak emas.</i>", reply_markup=cancel_kb())


@admin.message(AdminS2.perk_val)
async def ad_perk_do(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t.isdigit():
        await m.answer("❌ Musbat butun son yuboring.")
        return
    d = await state.get_data()
    await state.clear()
    await db_exec(f"UPDATE users SET {d['field']}=? WHERE id=?", (int(t), d["uid"]))
    await audit(m.from_user.id, "perk", f"{d['uid']} {d['field']}={t}")
    await notify_user(d["uid"], "🌟 Hisobingizga qo'shimcha ustunlik berildi! «📊 Statistika» bo'limida ko'ring.")
    card = await user_card(d["uid"])
    await m.answer("✅ Saqlandi", reply_markup=main_kb(OWNER_ID))
    await m.answer(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:px:\d+$"))
async def ad_perk_export(cb: CallbackQuery):
    uid = int(cb.data.split(":")[2])
    await db_exec("UPDATE users SET bonus_export=1-COALESCE(bonus_export,0) WHERE id=?", (uid,))
    await audit(cb.from_user.id, "perk_export", str(uid))
    await cb.answer("Saqlandi ✅")
    card = await user_card(uid)
    await cb.message.edit_text(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:rs:\d+:(usage|free|perks)$"))
async def ad_reset(cb: CallbackQuery):
    _, _, uid, what = cb.data.split(":")
    uid = int(uid)
    if what == "usage":
        await db_exec("DELETE FROM usage WHERE user_id=? AND day=?", (uid, today()))
    elif what == "free":
        await db_exec("UPDATE users SET free_used=0 WHERE id=?", (uid,))
    else:
        await db_exec("UPDATE users SET bonus_acc=0, bonus_mention=0, bonus_scrape=0, bonus_export=0 WHERE id=?", (uid,))
    await audit(cb.from_user.id, f"reset_{what}", str(uid))
    await cb.answer("Bajarildi ✅")
    card = await user_card(uid)
    await cb.message.edit_text(card[0], reply_markup=card[1])


async def remove_account_full(acc_id: int, logout: bool = True) -> None:
    acc = await db_one("SELECT * FROM accounts WHERE id=?", (acc_id,))
    if not acc:
        return
    client = CLIENTS.pop(acc_id, None)
    if client is None and logout and acc["status"] == "active":
        try:
            client = new_client(FERNET.decrypt(acc["session"].encode()).decode())
            await client.connect()
        except Exception:  # noqa: BLE001
            client = None
    if client:
        if logout:
            await restore_bio(client, acc)
            try:
                await client.log_out()
            except Exception:  # noqa: BLE001
                pass
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
    await db_exec("DELETE FROM accounts WHERE id=?", (acc_id,))


@admin.callback_query(F.data.regexp(r"^ad:ua:\d+$"))
async def ad_user_accounts(cb: CallbackQuery):
    await cb.answer()
    await render_user_accounts(cb, int(cb.data.split(":")[2]))


async def render_user_accounts(cb: CallbackQuery, uid: int) -> None:
    accs = await db_all("SELECT * FROM accounts WHERE owner_id=? ORDER BY id", (uid,))
    rows = [[(f"🗑 {a['name']} {a['phone']} [{a['status']}]", f"ad:uac:{a['id']}:{uid}")] for a in accs]
    rows.append([("🔙 Orqaga", f"ad:u:{uid}")])
    await cb.message.edit_text(f"👤 <b>Akkauntlari</b> ({len(accs)} ta). Uzish uchun bosing:" if accs else "👤 Akkaunt yo'q.",
                               reply_markup=ikb(*rows))


@admin.callback_query(F.data.regexp(r"^ad:uac:\d+:\d+$"))
async def ad_user_acc_del(cb: CallbackQuery):
    _, _, acc_id, uid = cb.data.split(":")
    await remove_account_full(int(acc_id))
    await audit(cb.from_user.id, "acc_remove", f"{acc_id} user {uid}")
    await cb.answer("🗑 Uzildi va o'chirildi")
    await render_user_accounts(cb, int(uid))


@admin.callback_query(F.data.regexp(r"^ad:udel:\d+$"))
async def ad_user_del_ask(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    uid = int(cb.data.split(":")[2])
    if is_staff(uid):
        await cb.answer("Ega/adminni o'chirib bo'lmaydi.", show_alert=True)
        return
    await cb.answer()
    await cb.message.edit_text(f"⚠️ User <code>{uid}</code> va uning barcha ma'lumotlari (akkauntlar, yig'ilgan userlar) "
                               f"butunlay o'chirilsinmi?",
                               reply_markup=ikb([("✅ Ha, o'chirish", f"ad:udok:{uid}")], [("↩️ Yo'q", f"ad:u:{uid}")]))


@admin.callback_query(F.data.regexp(r"^ad:udok:\d+$"))
async def ad_user_del(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    uid = int(cb.data.split(":")[2])
    if is_staff(uid):
        return
    for a in await db_all("SELECT id FROM accounts WHERE owner_id=?", (uid,)):
        await remove_account_full(a["id"])
    for sql in ("DELETE FROM collected WHERE owner_id=?", "DELETE FROM sources WHERE owner_id=?", "DELETE FROM usage WHERE user_id=?",
                "DELETE FROM referrals WHERE invited_id=? OR referrer_id=?", "DELETE FROM promo_uses WHERE user_id=?",
                "DELETE FROM react_access WHERE user_id=?", "DELETE FROM dm_access WHERE user_id=?",
                "DELETE FROM react_channels WHERE owner_id=?",
                "DELETE FROM users WHERE id=?"):
        await db_exec(sql, (uid, uid) if "OR" in sql else (uid,))
    await audit(cb.from_user.id, "user_delete", str(uid))
    await cb.answer("🗑 O'chirildi", show_alert=True)
    await cb.message.edit_text("🗑 User o'chirildi.", reply_markup=ikb([("🔙 Userlar", "ad:users:0")]))


# ── Hammaga kun qo'shish ──
@admin.callback_query(F.data == "ad:massd")
async def ad_mass_days(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    n = (await db_one("SELECT COUNT(*) c FROM users WHERE plan_until>?", (time.time(),)))["c"]
    await state.set_state(AdminS2.mass_days)
    await cb.message.answer(f"⏱ Faol tarifdagi <b>{n}</b> ta userga necha kun qo'shilsin?\n(masalan, bot to'xtab qolgan bo'lsa — kompensatsiya)\n"
                            f"Raqam yuboring:", reply_markup=cancel_kb())


@admin.message(AdminS2.mass_days)
async def ad_mass_days_do(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t.isdigit() or not (1 <= int(t) <= 365):
        await m.answer("❌ 1 dan 365 gacha son yuboring.")
        return
    await state.clear()
    await m.answer("👑", reply_markup=main_kb(OWNER_ID))
    n = (await db_one("SELECT COUNT(*) c FROM users WHERE plan_until>?", (time.time(),)))["c"]
    await m.answer(f"⚠️ <b>{n}</b> ta userga <b>{t}</b> kun qo'shilsinmi?",
                   reply_markup=ikb([("✅ Ha, qo'shish", f"ad:massok:{t}")], [("❌ Bekor", "ad:home")]))


@admin.callback_query(F.data.regexp(r"^ad:massok:\d+$"))
async def ad_mass_days_go(cb: CallbackQuery):
    days = int(cb.data.split(":")[2])
    now = time.time()
    ids = [r["id"] for r in await db_all("SELECT id FROM users WHERE plan_until>?", (now,))]
    await db_exec("UPDATE users SET plan_until=plan_until+?, exp_notified=0 WHERE plan_until>?", (days * 86400, now))
    await audit(cb.from_user.id, "mass_days", f"{days}k x {len(ids)}")
    await cb.answer("✅ Qo'shildi")
    await cb.message.edit_text(f"✅ {len(ids)} ta userga {days} kun qo'shildi. Xabar yuborilmoqda...")
    actor = cb.from_user.id

    async def job():
        ok, fail = await send_to_ids(ids, lambda x: BOT.send_message(x, f"🎁 Tarifingizga <b>{days}</b> kun bonus qo'shildi!"))
        await notify_user(actor, f"⏱ Xabar yuborildi: ✅ {ok} | ❌ {fail}")
    spawn(job())


# ── Tozalash ──
CLEAN_ITEMS = {
    "dead": "🔴 O'lgan akkauntlarni o'chirish",
    "expired": "📉 Tarifi tugagan userlarning yig'ilgan bazasi",
    "old": "🗓 30 kundan eski yig'ilgan bazalar",
    "usage": "📊 60 kundan eski limit yozuvlari",
    "vacuum": "🗜 Bazani siqish (VACUUM)",
}


async def clean_count(kind: str) -> int:
    now = time.time()
    if kind == "dead":
        return (await db_one("SELECT COUNT(*) c FROM accounts WHERE status!='active'"))["c"]
    if kind == "expired":
        return (await db_one("SELECT COUNT(*) c FROM collected WHERE owner_id IN (SELECT id FROM users WHERE plan_until<?) AND owner_id!=?",
                             (now, OWNER_ID)))["c"]
    if kind == "old":
        return (await db_one("SELECT COUNT(*) c FROM collected WHERE source_id IN (SELECT id FROM sources WHERE created<?)",
                             (now - 30 * 86400,)))["c"]
    if kind == "usage":
        cut_day = (datetime.now(TZ) - timedelta(days=60)).strftime("%Y-%m-%d")
        return (await db_one("SELECT COUNT(*) c FROM usage WHERE day<?", (cut_day,)))["c"]
    return 0


async def clean_do(kind: str) -> str:
    now = time.time()
    n = await clean_count(kind)
    if kind == "dead":
        for a in await db_all("SELECT id FROM accounts WHERE status!='active'"):
            await remove_account_full(a["id"], logout=False)
    elif kind == "expired":
        await db_exec("DELETE FROM collected WHERE owner_id IN (SELECT id FROM users WHERE plan_until<?) AND owner_id!=?", (now, OWNER_ID))
        await db_exec("DELETE FROM sources WHERE owner_id IN (SELECT id FROM users WHERE plan_until<?) AND owner_id!=?", (now, OWNER_ID))
    elif kind == "old":
        await db_exec("DELETE FROM collected WHERE source_id IN (SELECT id FROM sources WHERE created<?)", (now - 30 * 86400,))
        await db_exec("DELETE FROM sources WHERE created<?", (now - 30 * 86400,))
    elif kind == "usage":
        cut_day = (datetime.now(TZ) - timedelta(days=60)).strftime("%Y-%m-%d")
        await db_exec("DELETE FROM usage WHERE day<?", (cut_day,))
    elif kind == "vacuum":
        await DB.commit()
        await DB.execute("VACUUM")
        return "✅ Baza siqildi."
    return f"✅ Tozalandi: {n} ta yozuv."


@admin.callback_query(F.data == "ad:cl")
async def ad_clean(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer()
    rows = []
    for k, lbl in CLEAN_ITEMS.items():
        n = await clean_count(k)
        rows.append([(f"{lbl}" + (f" ({n})" if k != "vacuum" else ""), f"ad:clq:{k}")])
    rows.append([("🔙 Orqaga", "ad:home")])
    await cb.message.edit_text("🧹 <b>Tozalash</b>\n\nKerak bo'lmagan ma'lumotlarni o'chirib, bazani yengillashtiring.", reply_markup=ikb(*rows))


@admin.callback_query(F.data.startswith("ad:clq:"))
async def ad_clean_ask(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    k = cb.data.split(":")[2]
    if k not in CLEAN_ITEMS:
        return
    await cb.answer()
    await cb.message.edit_text(f"⚠️ <b>{CLEAN_ITEMS[k]}</b>\nTasdiqlaysizmi? Bu amalni qaytarib bo'lmaydi.",
                               reply_markup=ikb([("✅ Ha", f"ad:clok:{k}")], [("↩️ Yo'q", "ad:cl")]))


@admin.callback_query(F.data.startswith("ad:clok:"))
async def ad_clean_do(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    k = cb.data.split(":")[2]
    if k not in CLEAN_ITEMS:
        return
    await cb.answer("Bajarilmoqda...")
    res = await clean_do(k)
    await audit(cb.from_user.id, "clean", f"{k}: {res}")
    await cb.message.edit_text(res, reply_markup=ikb([("🔙 Tozalash", "ad:cl")]))


# ── CSV, tarix ──
@admin.callback_query(F.data == "ad:csv")
async def ad_csv(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer("Tayyorlanmoqda...")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "username", "full_name", "joined", "banned", "plan", "plan_until", "free_used",
                "bonus_acc", "bonus_mention", "bonus_scrape", "bonus_export"])
    for u in await db_all("SELECT * FROM users ORDER BY joined"):
        w.writerow([u["id"], u["username"] or "", u["full_name"] or "", fmt_date(u["joined"]), u["banned"], u["plan_key"],
                    fmt_date(u["plan_until"]) if u["plan_until"] else "", u["free_used"], u["bonus_acc"], u["bonus_mention"],
                    u["bonus_scrape"], u["bonus_export"]])
    await BOT.send_document(cb.from_user.id, BufferedInputFile(buf.getvalue().encode("utf-8-sig"),
                                                               filename=f"users_{datetime.now(TZ):%Y%m%d}.csv"),
                            caption="📤 Foydalanuvchilar ro'yxati")


@admin.callback_query(F.data == "ad:log")
async def ad_log(cb: CallbackQuery):
    await cb.answer()
    rows = await db_all("SELECT * FROM audit ORDER BY id DESC LIMIT 25")
    txt = "📜 <b>Oxirgi harakatlar</b>\n\n" + ("\n".join(
        f"{datetime.fromtimestamp(r['ts'], TZ):%d.%m %H:%M} | <code>{r['actor']}</code> | {esc(r['action'])} {esc(r['detail'] or '')}"
        for r in rows) or "Hozircha bo'sh.")
    await cb.message.edit_text(txt, reply_markup=ikb([("🔙 Orqaga", "ad:home")]))


# ── Adminlar va egalikni topshirish ──
async def find_user_by_ref(text: str):
    q = (text or "").strip().lstrip("@")
    if q.isdigit():
        return await get_user(int(q))
    return await db_one("SELECT * FROM users WHERE LOWER(username)=?", (q.lower(),))


async def admins_view() -> tuple[str, InlineKeyboardMarkup]:
    rows = []
    lines = [f"👑 <b>Ega:</b> @{esc(OWNER_USERNAME)} (<code>{OWNER_ID}</code>)\n", "👮 <b>Adminlar:</b>"]
    for aid in sorted(ADMINS):
        u = await get_user(aid)
        nm = (f"@{u['username']}" if u and u["username"] else (u["full_name"] if u else "—"))
        lines.append(f"• {esc(str(nm))} (<code>{aid}</code>)")
        rows.append([(f"🗑 {nm} ni adminlikdan olish", f"ad:admd:{aid}")])
    if not ADMINS:
        lines.append("Hozircha yo'q.")
    lines.append("\n<i>Adminlar: userlar, tarif berish, e'lon, promokod, majburiy obuna, gift bilan ishlay oladi. "
                 "Sozlamalar, matnlar, narxlar, backup, tozalash va adminlarni faqat ega boshqaradi.</i>")
    rows.append([("➕ Admin qo'shish", "ad:adma")])
    rows.append([("🔁 Egalikni topshirish", "ad:own")])
    rows.append([("🔙 Orqaga", "ad:home")])
    return "\n".join(lines), ikb(*rows)


@admin.callback_query(F.data == "ad:adm")
async def ad_admins(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer()
    txt, kb = await admins_view()
    await cb.message.edit_text(txt, reply_markup=kb)


@admin.callback_query(F.data == "ad:adma")
async def ad_admin_add(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    await cb.answer()
    await state.set_state(AdminS2.admin_add)
    await cb.message.answer("👮 Admin qilinadigan user ID yoki @username yuboring\n(u botga kamida bir marta /start bosgan bo'lishi kerak):",
                            reply_markup=cancel_kb())


@admin.message(AdminS2.admin_add)
async def ad_admin_add_do(m: Message, state: FSMContext):
    u = await find_user_by_ref(m.text or "")
    if not u:
        await m.answer("❌ Topilmadi. User botga /start bosganini tekshiring.")
        return
    if u["id"] == OWNER_ID:
        await m.answer("Bu — bot egasi.")
        return
    await state.clear()
    ADMINS.add(u["id"])
    await save_admins()
    await audit(m.from_user.id, "admin_add", str(u["id"]))
    await notify_user(u["id"], "👮 Siz botda <b>admin</b> etib tayinlandingiz. «👑 Admin panel» tugmasi chiqadi (/start bosing).")
    await m.answer("✅ Admin qo'shildi", reply_markup=main_kb(OWNER_ID))


@admin.callback_query(F.data.startswith("ad:admd:"))
async def ad_admin_del(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    ADMINS.discard(int(cb.data.split(":")[2]))
    await save_admins()
    await audit(cb.from_user.id, "admin_del", cb.data.split(":")[2])
    await cb.answer("Olib tashlandi")
    txt, kb = await admins_view()
    await cb.message.edit_text(txt, reply_markup=kb)


@admin.callback_query(F.data == "ad:own")
async def ad_owner_transfer(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    await cb.answer()
    await state.set_state(AdminS2.owner_set)
    await cb.message.answer("🔁 <b>Egalikni topshirish</b>\nYangi ega ID yoki @username'ini yuboring "
                            "(u botga /start bosgan bo'lishi kerak).\n⚠️ Siz admin bo'lib qolasiz.", reply_markup=cancel_kb())


@admin.message(AdminS2.owner_set)
async def ad_owner_transfer_do(m: Message, state: FSMContext):
    u = await find_user_by_ref(m.text or "")
    if not u or u["id"] == OWNER_ID:
        await m.answer("❌ Topilmadi yoki bu o'zingiz.")
        return
    await state.clear()
    await m.answer("👑", reply_markup=main_kb(OWNER_ID))
    await m.answer(f"⚠️ Egalik <b>{esc(u['full_name'] or '')}</b> (<code>{u['id']}</code>) ga topshirilsinmi?",
                   reply_markup=ikb([("✅ Ha, topshirish", f"ad:ownok:{u['id']}")], [("❌ Bekor", "ad:adm")]))


@admin.callback_query(F.data.regexp(r"^ad:ownok:\d+$"))
async def ad_owner_transfer_go(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    new_id = int(cb.data.split(":")[2])
    u = await get_user(new_id)
    if not u:
        return
    old = OWNER_ID
    await set_owner(new_id, u["username"])
    ADMINS.add(old)
    await save_admins()
    await audit(old, "owner_transfer", f"{old} -> {new_id}")
    await cb.answer("✅")
    await cb.message.edit_text(f"✅ Egalik @{esc(u['username'] or str(new_id))} ga topshirildi. Siz endi adminsiz.")
    await notify_user(new_id, "👑 Siz botning yangi <b>egasi</b> bo'ldingiz! /start bosing.")


# ══════════════════════════════════════════════════════════════════════════
#   ❤️ REAKSIYA XIZMATI (yordamchi botlar)  +  ✉️ SHAXSIY XABAR (@userlarga)
# ══════════════════════════════════════════════════════════════════════════
class ReactS(StatesGroup):
    chan = State()
    post = State()
    cnt = State()


class DmS(StatesGroup):
    text = State()
    users = State()
    confirm = State()


class AdminS3(StatesGroup):
    rb_add = State()
    rx_days = State()
    dm_quota = State()


REACT_PALETTE = ["👍", "❤", "🔥", "🥰", "👏", "😁", "🎉", "🤩", "💯", "😍", "🙏", "⚡"]
REACT_BOTS: dict[int, Bot] = {}          # react_bots.id -> Bot (yordamchi botlar)
TOKEN_RE = re.compile(r"\d{6,12}:[A-Za-z0-9_-]{30,}")
UNAME_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
POST_RE = re.compile(r"(?:https?://)?t\.me/(?:c/(\d+)|([A-Za-z]\w{3,}))/(\d+)")
DM_JOBS: dict[int, asyncio.Event] = {}   # user_id -> stop flag
LAST_POST: dict[int, int] = {}           # kanal chat_id -> oxirgi ko'rilgan post ID (test uchun)
_ALLOWED_CACHE: dict[int, tuple[float, list[str] | None]] = {}
NOLIMIT_TEXT = "⛔ <b>Sizda bu xizmat uchun limit yo'q.</b>\n\nAvval ownerdan limit sotib oling 👇"


SIGN_DEFAULT = "@LegionUatgerBot shu bot orqali tarqatildi"


def sign_line() -> str:
    return (cfg("sign_text") or SIGN_DEFAULT).strip()


def with_sign(text: str, sep: str = "\n") -> str:
    """Tarqatiladigan matn oxiriga bot imzosini qo'shadi (allaqachon bo'lsa, qayta qo'shmaydi)."""
    if not cfg_on("sign_on"):
        return text
    s = sign_line()
    if not s or s.lower() in (text or "").lower():
        return text
    return f"{text}{sep}{s}" if text else s


def buy_kb(what: str, uid: int) -> InlineKeyboardMarkup:
    return ikb([("💬 Ownerdan sotib olish", pay_url(what, uid))])


# ───────────── ruxsatlar / limitlar ─────────────
async def react_until(uid: int) -> float:
    if is_owner(uid):
        return float("inf")
    r = await db_one("SELECT until FROM react_access WHERE user_id=?", (uid,))
    return float(r["until"]) if r and r["until"] > time.time() else 0.0


async def react_allowed(uid: int) -> bool:
    return bool(await react_until(uid)) and (cfg_on("react_on") or is_staff(uid))


async def dm_remaining(uid: int) -> int:
    if is_owner(uid):
        return 10 ** 9
    r = await db_one("SELECT quota, used FROM dm_access WHERE user_id=?", (uid,))
    return max(int(r["quota"]) - int(r["used"]), 0) if r else 0


async def dm_consume(uid: int) -> None:
    if not is_owner(uid):
        await db_exec("UPDATE dm_access SET used=used+1 WHERE user_id=?", (uid,))


def rem_txt(n: int) -> str:
    return "∞" if n >= 10 ** 9 else str(n)


# ───────────── yordamchi botlar ─────────────
async def load_react_bots() -> None:
    for r in await db_all("SELECT * FROM react_bots WHERE active=1"):
        try:
            REACT_BOTS[r["id"]] = Bot(FERNET.decrypt(r["token"].encode()).decode())
        except Exception as e:  # noqa: BLE001
            log.warning("react bot %s yuklanmadi: %s", r["id"], e)


async def add_react_bots(text: str) -> tuple[list[tuple[int, str]], list[str]]:
    """Matndagi barcha bot tokenlarini tekshirib, havzaga qo'shadi."""
    added: list[tuple[int, str]] = []
    errs: list[str] = []
    for tok in dict.fromkeys(TOKEN_RE.findall(text or "")):
        b = Bot(tok)
        try:
            me = await b.get_me()
        except Exception:  # noqa: BLE001
            await b.session.close()
            errs.append(f"{tok[:10]}… — token yaroqsiz")
            continue
        if await db_one("SELECT 1 FROM react_bots WHERE tg_id=?", (me.id,)):
            await b.session.close()
            errs.append(f"@{me.username} — allaqachon qo'shilgan")
            continue
        cur = await db_exec("INSERT INTO react_bots(tg_id,username,token,active,created) VALUES(?,?,?,1,?)",
                            (me.id, me.username or "", FERNET.encrypt(tok.encode()).decode(), time.time()))
        REACT_BOTS[cur.lastrowid] = b
        added.append((me.id, me.username or str(me.id)))
    return added, errs


async def _promote_userbot(owner_id: int, chat_id: int, pairs: list[tuple[int, str]]) -> set[int]:
    """Zaxira yo'l: Bot API bilan bo'lmasa, foydalanuvchining ulangan akkaunti (agar kanal admini bo'lsa) orqali qo'shadi."""
    done: set[int] = set()
    accs = await db_all("SELECT id FROM accounts WHERE owner_id=? AND status='active'", (owner_id,))
    for a in accs:
        cl = await get_client(a["id"])
        if not cl:
            continue
        ch = None
        for attempt in range(2):
            try:
                ch = await cl.get_input_entity(tl_types.PeerChannel(-chat_id - 10 ** 12))
                break
            except Exception:  # noqa: BLE001
                if attempt == 0:
                    try:
                        async for _d in cl.iter_dialogs(limit=400):   # entity keshini to'ldiramiz
                            pass
                    except Exception:  # noqa: BLE001
                        pass
        if ch is None:
            continue
        rights = tl_types.ChatAdminRights(other=True)
        for tid, uname in pairs:
            if tid in done or not uname:
                continue
            try:
                await cl(EditAdminRequest(ch, await cl.get_input_entity(uname), rights, rank=""))
                done.add(tid)
            except Exception as e:  # noqa: BLE001
                log.debug("userbot promote %s: %s", uname, e)
            await asyncio.sleep(0.5)
        if len(done) == len(pairs):
            break
    return done


async def promote_helpers(chat_id: int, owner_id: int, only_tg_ids: list[int] | None = None,
                          use_api: bool = True) -> tuple[int, list[str]]:
    """Yordamchi botlarni kanalga admin qilib qo'shadi → (muvaffaqiyatli soni, xatolar)."""
    rows = await db_all("SELECT tg_id, username FROM react_bots WHERE active=1")
    ok = 0
    failed: dict[int, tuple[str, str]] = {}
    for r in rows:
        if only_tg_ids is not None and r["tg_id"] not in only_tg_ids:
            continue
        if not use_api:
            failed[r["tg_id"]] = (r["username"], "")
            continue
        for _ in range(2):
            try:
                await BOT.promote_chat_member(chat_id, r["tg_id"], can_manage_chat=True)
                ok += 1
                break
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception as e:  # noqa: BLE001
                failed[r["tg_id"]] = (r["username"], str(e)[:70])
                break
        await asyncio.sleep(0.4)
    if failed:
        done = await _promote_userbot(owner_id, chat_id, [(t, u) for t, (u, _) in failed.items()])
        ok += len(done)
        for t in done:
            failed.pop(t, None)
    return ok, [f"@{u}: {e}" for u, e in failed.values()]


async def sync_helpers(only_tg_ids: list[int] | None = None) -> None:
    """Havzadagi (yangi) botlarni barcha ulangan kanallarga qo'shadi."""
    for c in await db_all("SELECT chat_id, owner_id FROM react_channels"):
        try:
            await promote_helpers(c["chat_id"], c["owner_id"], only_tg_ids)
        except Exception as e:  # noqa: BLE001
            log.warning("sync_helpers %s: %s", c["chat_id"], e)


def react_err_hint(e: Exception) -> str:
    """Telegram xatosini tushunarli sababga aylantiradi."""
    s = f"{type(e).__name__}: {e}".lower()
    if isinstance(e, AttributeError):
        return "aiogram versiyasi eski (set_message_reaction yo'q): pip install -U aiogram"
    if "reaction_invalid" in s or ("reaction" in s and "invalid" in s):
        return "kanalda bu reaksiya ruxsat etilmagan yoki reaksiyalar o'chirilgan (Kanal → Reaksiyalar)"
    if "unauthorized" in s or "401" in s:
        return "bot tokeni yaroqsiz yoki yangilangan"
    if any(k in s for k in ("not a member", "not enough rights", "chat_admin_required", "chat not found",
                            "peer_id_invalid", "forbidden", "kicked", "participant", "member not found")):
        return "bot kanalda admin emas (yoki chiqarib yuborilgan)"
    if "message_id_invalid" in s or "message to react" in s or "message not found" in s:
        return "post topilmadi (havola yoki post ID noto'g'ri)"
    if "too many requests" in s or "retry after" in s or "flood" in s:
        return "Telegram tezlik cheklovi"
    return f"{type(e).__name__}: {str(e)[:80]}"


def err_summary(errs: Counter) -> str:
    return "\n".join(f"• {esc(h)} — {n} ta" for h, n in errs.most_common(3))


def _norm_em(e: str) -> str:
    return (e or "").replace("\ufe0f", "")


async def chan_allowed(chat_id: int) -> list[str] | None:
    """Kanalda ruxsat etilgan emoji'lar (None = hammasi, [] = reaksiyalar o'chirilgan)."""
    c = _ALLOWED_CACHE.get(chat_id)
    if c and time.time() - c[0] < 300:
        return c[1]
    res: list[str] | None = None
    try:
        chat = await BOT.get_chat(chat_id)
        ar = getattr(chat, "available_reactions", None)
        if ar is not None:
            res = [_norm_em(getattr(r, "emoji", "")) for r in ar if getattr(r, "emoji", None)]
    except Exception:  # noqa: BLE001
        res = None
    _ALLOWED_CACHE[chat_id] = (time.time(), res)
    return res


async def helper_status(cid: int) -> tuple[int, int, list[str], list[int]]:
    """Kanalda nechta yordamchi bot admin ekanini tekshiradi → (adminlar, jami, yetishmaganlar @nomi, admin bot idlari)."""
    rows = await db_all("SELECT id, tg_id, username FROM react_bots WHERE active=1")
    admins: list[int] = []
    missing: list[str] = []
    for r in rows:
        try:
            cm = await BOT.get_chat_member(cid, r["tg_id"])
            is_adm = cm.status in ("administrator", "creator")
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            is_adm = False
        except Exception:  # noqa: BLE001
            is_adm = False
        if is_adm:
            admins.append(r["id"])
        else:
            missing.append(r["username"])
        await asyncio.sleep(0.03)
    return len(admins), len(rows), missing, admins


async def do_reactions(chat_id: int, msg_id: int, emojis: list[str], cnt: int) -> tuple[int, int, Counter]:
    """Yordamchi botlar bilan postga reaksiya bosadi (cnt=0 → barcha botlar) → (muvaffaqiyatli, xato, sabablar)."""
    rows = await db_all("SELECT id FROM react_bots WHERE active=1")
    bots = [REACT_BOTS[r["id"]] for r in rows if r["id"] in REACT_BOTS]
    errs: Counter = Counter()
    if not bots:
        return 0, 0, Counter({"yordamchi botlar yo'q": 1})
    random.shuffle(bots)
    if cnt > 0:
        bots = bots[:cnt]
    pal = [e for e in emojis if e in REACT_PALETTE] or REACT_PALETTE
    allowed = await chan_allowed(chat_id)
    if allowed is not None:
        pal2 = [e for e in pal if _norm_em(e) in allowed] or [e for e in REACT_PALETTE if _norm_em(e) in allowed]
        if not pal2:
            return 0, len(bots), Counter({"kanalda reaksiyalar o'chirilgan yoki mos emoji ruxsat etilmagan (Kanal → Reaksiyalar)": len(bots)})
        pal = pal2
    ok = fail = 0

    async def one(b: Bot) -> str | None:
        try:
            await b.set_message_reaction(chat_id=chat_id, message_id=msg_id,
                                         reaction=[ReactionTypeEmoji(emoji=random.choice(pal))])
            return None
        except TelegramRetryAfter as e:
            await asyncio.sleep(min(e.retry_after, 20))
            return "Telegram tezlik cheklovi"
        except Exception as e:  # noqa: BLE001
            h = react_err_hint(e)
            log.warning("reaction xatosi: %s | %s", h, e)
            return h

    for i in range(0, len(bots), 5):          # 5 tadan guruh, orasida tabiiy pauza
        res = await asyncio.gather(*(one(b) for b in bots[i:i + 5]))
        for x in res:
            if x is None:
                ok += 1
            else:
                fail += 1
                errs[x] += 1
        await asyncio.sleep(random.uniform(0.3, 0.9))
    return ok, fail, errs


def row_emojis(row) -> list[str]:
    return row["emojis"].split("|") if row["emojis"] else []


# ───────────── kanal ulash ─────────────
def rights_help() -> str:
    return ("⚠️ <b>Botni kanalga admin qiling</b>\n\n"
            f"1️⃣ Kanalingiz → Administratorlar → Administrator qo'shish → @{BOT_USERNAME}\n"
            "2️⃣ Huquqlarni o'zgartirmasangiz ham bo'ladi (asosiy bot faqat sizni tekshirish va yangi postlarni ko'rish uchun kerak)\n\n"
            "So'ng «✅ Tekshirish» ni bosing.")


async def main_bot_rights(chat_id: int, need_promote: bool = False) -> bool:
    try:
        cm = await BOT.get_chat_member(chat_id, BOT.id)
    except Exception:  # noqa: BLE001
        return False
    if cm.status == "creator":
        return True
    if cm.status != "administrator":
        return False
    return bool(getattr(cm, "can_promote_members", False)) if need_promote else True


async def _auto_promote_report(uid: int, cid: int, title: str, use_api: bool) -> None:
    """Fonda yordamchi botlarni kanalga qo'shishga urinadi va natijani egasiga xabar qiladi."""
    try:
        await promote_helpers(cid, uid, use_api=use_api)
        adm, tot, _, _ = await helper_status(cid)
    except Exception as e:  # noqa: BLE001
        log.warning("auto promote %s: %s", cid, e)
        return
    txt = f"🤖 <b>{esc(title)}</b>: avtomatik qo'shish yakunlandi.\nKanalda admin botlar: <b>{adm}/{tot}</b>"
    kb = None
    if adm < tot:
        txt += "\n\nQolganlarini «➕ Botlarni qo'lda qo'shish» orqali admin qiling (har biri 1 bosish)."
        kb = ikb([("➕ Botlarni qo'lda qo'shish", f"rcm:{cid}:0")])
    else:
        txt += "\n\n🎉 Hamma botlar tayyor!"
    await notify_user(uid, txt, reply_markup=kb)


async def connect_channel(uid: int, chat_id: int) -> tuple[bool, str]:
    try:
        chat = await BOT.get_chat(chat_id)
    except Exception:  # noqa: BLE001
        return False, "❌ Kanal topilmadi yoki bot kanalda emas.\n\n" + rights_help()
    if chat.type != "channel":
        return False, "❌ Bu kanal emas. Faqat kanallar qo'llab-quvvatlanadi."
    if not await main_bot_rights(chat.id):
        return False, rights_help()
    if not is_owner(uid):
        try:
            um = await BOT.get_chat_member(chat.id, uid)
        except Exception:  # noqa: BLE001
            um = None
        if not um or um.status not in ("administrator", "creator"):
            return False, "❌ Siz bu kanalning admini emassiz."
    ex = await db_one("SELECT owner_id FROM react_channels WHERE chat_id=?", (chat.id,))
    if ex and ex["owner_id"] != uid:
        return False, "⚠️ Bu kanal boshqa foydalanuvchiga ulangan."
    if not REACT_BOTS:
        return False, "⚠️ Hozircha yordamchi botlar yo'q. Egaga xabar bering."
    if not ex:
        await db_exec("INSERT INTO react_channels(chat_id,owner_id,title,username,created) VALUES(?,?,?,?,?)",
                      (chat.id, uid, chat.title or "Kanal", chat.username or "", time.time()))
    else:
        await db_exec("UPDATE react_channels SET title=?, username=? WHERE chat_id=?",
                      (chat.title or "Kanal", chat.username or "", chat.id))
    has_rights = await main_bot_rights(chat.id, need_promote=True)
    has_acc = bool(await db_one("SELECT 1 FROM accounts WHERE owner_id=? AND status='active'", (uid,)))
    text = f"✅ Kanal ulandi: <b>{esc(chat.title or '')}</b>\n🤖 Yordamchi botlar: <b>{len(REACT_BOTS)}</b> ta"
    if has_rights or has_acc:
        spawn(_auto_promote_report(uid, chat.id, chat.title or "Kanal", has_rights))
        text += "\n\n⏳ Botlar avtomatik qo'shilmoqda (fonda), natija xabar qilinadi."
    text += "\n\n👇 Xohlasangiz, «➕ Botlarni qo'lda qo'shish» tugmasi orqali o'zingiz ham admin qilishingiz mumkin."
    return True, text


def parse_chat_ref(text: str):
    ref = (text or "").strip()
    mc = re.search(r"t\.me/c/(\d+)", ref)
    if mc:
        return int("-100" + mc.group(1))
    mm = re.search(r"t\.me/([A-Za-z]\w{3,})", ref)
    if mm and mm.group(1).lower() not in ("c", "joinchat"):
        return "@" + mm.group(1)
    if re.match(r"^@?[A-Za-z]\w{3,}$", ref):
        return "@" + ref.lstrip("@")
    if re.match(r"^-?\d+$", ref):
        return int(ref)
    return None


# ───────────── foydalanuvchi: reaksiya menyusi ─────────────
async def react_home_view(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    chans = await db_all("SELECT * FROM react_channels WHERE owner_id=? ORDER BY created", (uid,))
    until = await react_until(uid)
    left = "cheksiz" if is_owner(uid) else fmt_left(until)
    text = (f"❤️ <b>Kanal reaksiyalari</b>\n\n⏳ Xizmat muddati: <b>{left}</b>\n"
            f"🤖 Yordamchi botlar: <b>{len(REACT_BOTS)}</b> ta\n📢 Ulangan kanallar: <b>{len(chans)}</b>\n\n"
            "Kanalni ulang, so'ng postga reaksiya bosdiring yoki avtomatik rejimni yoqing.")
    rows = [[(f"{'🟢' if c['auto'] else '⚪️'} {c['title'][:30]}", f"rc:{c['chat_id']}")] for c in chans]
    rows.append([("➕ Kanal qo'shish", "rc_add")])
    return text, ikb(*rows)


async def react_guard(cb: CallbackQuery) -> bool:
    uid = cb.from_user.id
    if await react_until(uid) and (cfg_on("react_on") or is_staff(uid)):
        return True
    await cb.answer("⛔ Limit yo'q", show_alert=True)
    await cb.message.answer(NOLIMIT_TEXT, reply_markup=buy_kb("Reaksiya xizmati", uid))
    return False


async def rc_row(cb: CallbackQuery, cid: int):
    if not await react_guard(cb):
        return None
    row = await db_one("SELECT * FROM react_channels WHERE chat_id=? AND owner_id=?", (cid, cb.from_user.id))
    if not row:
        await cb.answer("Kanal topilmadi.", show_alert=True)
    return row


def channel_view(row) -> tuple[str, InlineKeyboardMarkup]:
    cid = row["chat_id"]
    n = len(REACT_BOTS)
    cnt_txt = f"{row['cnt']} ta" if 0 < row["cnt"] <= n else f"hammasi ({n} ta)"
    em = row_emojis(row)
    text = (f"📢 <b>{esc(row['title'])}</b>\n\n"
            f"🔄 Avtomatik (yangi postlarga): <b>{'YOQILGAN' if row['auto'] else 'ochiq emas'}</b>\n"
            f"😀 Emoji: <b>{' '.join(em) if em else 'tasodifiy'}</b>\n"
            f"🔢 Har postga reaksiya: <b>{cnt_txt}</b>\n"
            f"📊 Jami bosilgan: <b>{row['total']}</b>")
    return text, ikb(
        [(("🟢 Avtomatik: YOQILGAN" if row["auto"] else "⚪️ Avtomatik: o'chiq") + " (almashtirish)", f"rca:{cid}")],
        [("🔗 Postga reaksiya bosdirish", f"rcp:{cid}")],
        [("😀 Emoji tanlash", f"rce:{cid}"), ("🔢 Reaksiya soni", f"rcn:{cid}")],
        [("➕ Botlarni qo'lda qo'shish", f"rcm:{cid}:0")],
        [("🩺 Tekshirish va test", f"rct:{cid}"), ("🔄 Avto qo'shish", f"rcs:{cid}")],
        [("🗑 Kanalni olib tashlash", f"rcd:{cid}"), ("🔙 Orqaga", "rc_home")])


@router.message(F.text == B_REACT)
async def react_menu(m: Message, state: FSMContext):
    uid = m.from_user.id
    await reset(state, uid)
    if not cfg_on("react_on") and not is_staff(uid):
        await m.answer("🚧 Reaksiya xizmati vaqtincha o'chirilgan.")
        return
    if not await react_until(uid):
        await m.answer(NOLIMIT_TEXT, reply_markup=buy_kb("Reaksiya xizmati", uid))
        return
    text, kb = await react_home_view(uid)
    await m.answer(text, reply_markup=kb)


@router.callback_query(F.data == "rc_home")
async def rc_home(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    if not await react_guard(cb):
        return
    await cb.answer()
    text, kb = await react_home_view(cb.from_user.id)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "rc_add")
async def rc_add(cb: CallbackQuery, state: FSMContext):
    if not await react_guard(cb):
        return
    await cb.answer()
    await state.set_state(ReactS.chan)
    await cb.message.answer("📢 <b>Kanal qo'shish</b>\n\n" + rights_help() +
                            "\n\n👇 Endi kanal <b>@username</b>, havola yoki <b>-100…</b> ID sini yuboring.\n"
                            "Yopiq kanal bo'lsa, kanaldan istalgan postni shu yerga <b>forward</b> qiling.",
                            reply_markup=cancel_kb())


async def _connect_flow(target: Message, state: FSMContext, uid: int, chat_id: int) -> None:
    wait = await target.answer("⏳ Tekshirilmoqda, yordamchi botlar qo'shilmoqda...")
    ok, text = await connect_channel(uid, chat_id)
    if ok:
        await state.clear()
        await wait.edit_text(text, reply_markup=ikb([("➕ Botlarni qo'lda qo'shish", f"rcm:{chat_id}:0")],
                                                    [("⚙️ Kanal sozlamalari", f"rc:{chat_id}")]))
        await target.answer("🏠", reply_markup=main_kb(uid))
    else:
        await state.set_state(ReactS.chan)
        await state.update_data(chat_id=chat_id)
        await wait.edit_text(text, reply_markup=ikb([("✅ Tekshirish", "rc_chk")]))


@router.message(ReactS.chan)
async def rc_chan_msg(m: Message, state: FSMContext):
    uid = m.from_user.id
    fo = getattr(m, "forward_origin", None)
    if fo is not None and getattr(fo, "type", "") == "channel":
        chat_id = fo.chat.id
    else:
        ref = parse_chat_ref(m.text or "")
        if ref is None:
            await m.answer("❌ Tushunmadim. @username, havola, -100… ID yuboring yoki kanaldan post forward qiling.")
            return
        try:
            chat_id = (await BOT.get_chat(ref)).id
        except Exception:  # noqa: BLE001
            await m.answer("❌ Kanal topilmadi yoki bot kanalda emas.\n\n" + rights_help())
            return
    await _connect_flow(m, state, uid, chat_id)


@router.callback_query(F.data == "rc_chk")
async def rc_chk(cb: CallbackQuery, state: FSMContext):
    if not await react_guard(cb):
        return
    d = await state.get_data()
    if not d.get("chat_id"):
        await cb.answer("Jarayon eskirgan. Kanalni qaytadan qo'shing.", show_alert=True)
        return
    await cb.answer()
    await _connect_flow(cb.message, state, cb.from_user.id, d["chat_id"])


@router.callback_query(F.data.regexp(r"^rc:-?\d+$"))
async def rc_open(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    row = await rc_row(cb, int(cb.data.split(":")[1]))
    if not row:
        return
    await cb.answer()
    text, kb = channel_view(row)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp(r"^rca:-?\d+$"))
async def rc_auto(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    row = await rc_row(cb, cid)
    if not row:
        return
    await db_exec("UPDATE react_channels SET auto=1-auto WHERE chat_id=?", (cid,))
    row = await db_one("SELECT * FROM react_channels WHERE chat_id=?", (cid,))
    await cb.answer("Saqlandi ✅")
    text, kb = channel_view(row)
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except TelegramBadRequest:
        pass


def emoji_kb(cid: int, sel: list[str]) -> InlineKeyboardMarkup:
    rows: list[list] = []
    line: list = []
    for i, e in enumerate(REACT_PALETTE):
        line.append((("✅" if e in sel else "") + e, f"rcet:{cid}:{i}"))
        if len(line) == 4:
            rows.append(line)
            line = []
    if line:
        rows.append(line)
    rows.append([("🎲 Tasodifiy (hammasi)", f"rce0:{cid}")])
    rows.append([("🔙 Orqaga", f"rc:{cid}")])
    return ikb(*rows)


@router.callback_query(F.data.regexp(r"^rce:-?\d+$"))
async def rc_emoji(cb: CallbackQuery):
    row = await rc_row(cb, int(cb.data.split(":")[1]))
    if not row:
        return
    await cb.answer()
    await cb.message.edit_text("😀 <b>Emoji tanlash</b>\n\nBelgilanganlardan botlar tasodifiy tanlab bosadi. "
                               "Hech biri belgilanmasa — hammasidan tasodifiy.",
                               reply_markup=emoji_kb(row["chat_id"], row_emojis(row)))


@router.callback_query(F.data.regexp(r"^rcet:-?\d+:\d+$"))
async def rc_emoji_toggle(cb: CallbackQuery):
    _, cid, idx = cb.data.split(":")
    row = await rc_row(cb, int(cid))
    if not row or int(idx) >= len(REACT_PALETTE):
        return
    sel = row_emojis(row)
    e = REACT_PALETTE[int(idx)]
    sel = [x for x in sel if x != e] if e in sel else sel + [e]
    await db_exec("UPDATE react_channels SET emojis=? WHERE chat_id=?", ("|".join(sel), row["chat_id"]))
    await cb.answer()
    try:
        await cb.message.edit_reply_markup(reply_markup=emoji_kb(row["chat_id"], sel))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp(r"^rce0:-?\d+$"))
async def rc_emoji_reset(cb: CallbackQuery):
    row = await rc_row(cb, int(cb.data.split(":")[1]))
    if not row:
        return
    await db_exec("UPDATE react_channels SET emojis='' WHERE chat_id=?", (row["chat_id"],))
    await cb.answer("Tasodifiy ✅")
    try:
        await cb.message.edit_reply_markup(reply_markup=emoji_kb(row["chat_id"], []))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp(r"^rcn:-?\d+$"))
async def rc_count(cb: CallbackQuery, state: FSMContext):
    row = await rc_row(cb, int(cb.data.split(":")[1]))
    if not row:
        return
    await cb.answer()
    await state.set_state(ReactS.cnt)
    await state.update_data(cid=row["chat_id"])
    await cb.message.answer(f"🔢 Har postga nechta reaksiya bosilsin?\n\nHozirda <b>{len(REACT_BOTS)}</b> ta yordamchi bot bor. "
                            f"1 dan {len(REACT_BOTS)} gacha son yuboring, <code>0</code> = barcha botlar.",
                            reply_markup=cancel_kb())


@router.message(ReactS.cnt)
async def rc_count_do(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t.isdigit() or int(t) > max(len(REACT_BOTS), 0):
        await m.answer(f"❌ 0 dan {len(REACT_BOTS)} gacha butun son yuboring.")
        return
    d = await state.get_data()
    await state.clear()
    await db_exec("UPDATE react_channels SET cnt=? WHERE chat_id=? AND owner_id=?", (int(t), d["cid"], m.from_user.id))
    row = await db_one("SELECT * FROM react_channels WHERE chat_id=?", (d["cid"],))
    await m.answer("✅ Saqlandi", reply_markup=main_kb(m.from_user.id))
    if row:
        text, kb = channel_view(row)
        await m.answer(text, reply_markup=kb)


@router.callback_query(F.data.regexp(r"^rcp:-?\d+$"))
async def rc_post(cb: CallbackQuery, state: FSMContext):
    row = await rc_row(cb, int(cb.data.split(":")[1]))
    if not row:
        return
    await cb.answer()
    await state.set_state(ReactS.post)
    await cb.message.answer("🔗 Post havolasini yuboring (bir nechta bo'lsa, har birini yangi qatorga):\n"
                            "<code>https://t.me/kanal_nomi/123</code>\n<code>https://t.me/c/1234567890/45</code>",
                            reply_markup=cancel_kb())


async def post_react_job(uid: int, items: list) -> None:
    tot_ok = tot_fail = 0
    errs: Counter = Counter()
    for row, mid in items:
        ok, fail, e = await do_reactions(row["chat_id"], mid, row_emojis(row), row["cnt"])
        await db_exec("UPDATE react_channels SET total=total+? WHERE chat_id=?", (ok, row["chat_id"]))
        tot_ok += ok
        tot_fail += fail
        errs.update(e)
    msg = f"❤️ Reaksiya yakunlandi: ✅ {tot_ok} | ❌ {tot_fail}"
    if errs:
        msg += "\n\n⚠️ Sabablar:\n" + err_summary(errs)
    if tot_fail:
        msg += "\n\n🩺 Kanal sozlamalaridagi «Tekshirish va test» tugmasini bosing."
    await notify_user(uid, msg)


@router.message(ReactS.post)
async def rc_post_do(m: Message, state: FSMContext):
    uid = m.from_user.id
    if not await react_allowed(uid):
        await state.clear()
        await m.answer(NOLIMIT_TEXT, reply_markup=buy_kb("Reaksiya xizmati", uid))
        return
    items: list = []
    for mm in list(POST_RE.finditer(m.text or ""))[:20]:
        if mm.group(1):
            row = await db_one("SELECT * FROM react_channels WHERE chat_id=? AND owner_id=?",
                               (int("-100" + mm.group(1)), uid))
        else:
            row = await db_one("SELECT * FROM react_channels WHERE LOWER(username)=? AND owner_id=?",
                               (mm.group(2).lower(), uid))
        if row:
            items.append((row, int(mm.group(3))))
    if not items:
        await m.answer("❌ Mos havola topilmadi. Havola sizning ulangan kanalingiznikidan bo'lishi kerak.")
        return
    await state.clear()
    await m.answer(f"⏳ {len(items)} ta postga reaksiya bosilmoqda...", reply_markup=main_kb(uid))
    spawn(post_react_job(uid, items))


@router.callback_query(F.data.regexp(r"^rcs:-?\d+$"))
async def rc_resync(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    row = await rc_row(cb, cid)
    if not row:
        return
    await cb.answer("⏳ Urinilmoqda...")
    await promote_helpers(cid, cb.from_user.id, use_api=await main_bot_rights(cid, need_promote=True))
    adm, tot, _, _ = await helper_status(cid)
    txt = f"🔄 Kanalda admin botlar: <b>{adm}/{tot}</b>"
    kb = None
    if adm < tot:
        txt += "\n\nTelegram botlarni avtomatik qo'shishni cheklaydi. Qolganlarini «➕ Botlarni qo'lda qo'shish» orqali admin qiling."
        kb = ikb([("➕ Botlarni qo'lda qo'shish", f"rcm:{cid}:0")])
    await cb.message.answer(txt, reply_markup=kb)


BOTS_PER_PAGE = 10


@router.callback_query(F.data.regexp(r"^rcm:-?\d+:\d+$"))
async def rc_manual(cb: CallbackQuery):
    _, cid_s, page_s = cb.data.split(":")
    cid = int(cid_s)
    row = await rc_row(cb, cid)
    if not row:
        return
    rows_db = await db_all("SELECT tg_id, username FROM react_bots WHERE active=1 ORDER BY id")
    total = len(rows_db)
    if not total:
        await cb.answer("Yordamchi botlar yo'q.", show_alert=True)
        return
    pages = (total + BOTS_PER_PAGE - 1) // BOTS_PER_PAGE
    page = min(max(int(page_s), 0), pages - 1)
    chunk = rows_db[page * BOTS_PER_PAGE:(page + 1) * BOTS_PER_PAGE]
    await cb.answer()
    buttons: list[list] = []
    added = 0
    for r in chunk:
        try:
            cm = await BOT.get_chat_member(cid, r["tg_id"])
            is_adm = cm.status in ("administrator", "creator")
        except Exception:  # noqa: BLE001
            is_adm = False
        if is_adm:
            added += 1
            buttons.append([(f"✅ @{r['username']} — qo'shilgan", "noop")])
        else:
            buttons.append([(f"👍 @{r['username']} — Admin qilish",
                             f"https://t.me/{r['username']}?startchannel&admin=manage_chat")])
    buttons.append([("⬅️ Oldingi", f"rcm:{cid}:{max(page - 1, 0)}"), (f"{page + 1} / {pages}", "noop"),
                    ("Keyingi ➡️", f"rcm:{cid}:{min(page + 1, pages - 1)}")])
    buttons.append([("🔄 Holatni yangilash", f"rcm:{cid}:{page}")])
    buttons.append([("🩺 Tekshirish va test", f"rct:{cid}"), ("🔙 Orqaga", f"rc:{cid}")])
    text = (f"➕ <b>Botlarni qo'lda qo'shish</b> — {esc(row['title'])}\n\n"
            f"📄 {page + 1} / {pages} sahifa · Jami {total} ta bot\n"
            f"✅ Shu sahifada qo'shilgan: {added}/{len(chunk)}\n\n"
            "👇 Bot tugmasini bosing → kanalingizni tanlang → «Admin qilish» ni tasdiqlang. "
            "Keyin «🔄 Holatni yangilash» ni bosing.\nKeyingi botlar uchun «Keyingi» tugmasini bosing:")
    try:
        await cb.message.edit_text(text, reply_markup=ikb(*buttons))
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.regexp(r"^rct:-?\d+$"))
async def rc_test(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    row = await rc_row(cb, cid)
    if not row:
        return
    await cb.answer("⏳ Tekshirilmoqda...")
    lines = ["🩺 <b>Tekshiruv natijasi</b>\n"]
    main_ok = await main_bot_rights(cid)
    lines.append(("✅" if main_ok else "❌") + " Asosiy bot kanalda admin" +
                 ("" if main_ok else " — yangi postlarni ko'rmaydi (avtomatik reaksiya ishlamaydi)"))
    allowed = await chan_allowed(cid)
    if allowed is None:
        lines.append("✅ Kanalda barcha reaksiyalar ruxsat etilgan")
    elif not allowed:
        lines.append("❌ Kanalda reaksiyalar o'chirilgan — Kanal sozlamalari → Reaksiyalar ni yoqing")
    else:
        lines.append(f"⚠️ Kanalda faqat ba'zi reaksiyalar ruxsat: {' '.join(allowed[:10])}")
    adm, tot, missing, admin_ids = await helper_status(cid)
    lines.append(("✅" if adm == tot and tot else "❌") + f" Kanalda admin yordamchi botlar: {adm}/{tot}")
    if missing:
        lines.append("Admin emas: " + ", ".join("@" + esc(u) for u in missing[:8]) + (" …" if len(missing) > 8 else ""))
    mid = LAST_POST.get(cid)
    if mid and admin_ids and REACT_BOTS.get(admin_ids[0]):
        pal = [e for e in REACT_PALETTE if allowed is None or _norm_em(e) in allowed] or ["👍"]
        try:
            await REACT_BOTS[admin_ids[0]].set_message_reaction(
                chat_id=cid, message_id=mid, reaction=[ReactionTypeEmoji(emoji=pal[0])])
            lines.append("✅ Test reaksiya muvaffaqiyatli bosildi")
        except Exception as e:  # noqa: BLE001
            lines.append(f"❌ Test reaksiya xatosi: {esc(react_err_hint(e))}\n<code>{esc(str(e)[:160])}</code>")
    elif not admin_ids:
        lines.append("ℹ️ Test uchun kamida bitta bot kanalda admin bo'lishi kerak.")
    else:
        lines.append("ℹ️ Test uchun kanalga yangi post joylang (bot uni ko'radi), so'ng shu tugmani qayta bosing. "
                     "Yoki «Postga reaksiya bosdirish» orqali post havolasini yuboring.")
    await cb.message.answer("\n".join(lines), reply_markup=ikb([("➕ Botlarni qo'lda qo'shish", f"rcm:{cid}:0")],
                                                              [("🔙 Kanal sozlamalari", f"rc:{cid}")]))


@router.callback_query(F.data.regexp(r"^rcd:-?\d+$"))
async def rc_del_ask(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    if not await rc_row(cb, cid):
        return
    await cb.answer()
    await cb.message.edit_text("⚠️ Kanal ro'yxatdan olib tashlansinmi? (Botlar kanalda qoladi, faqat xizmat to'xtaydi.)",
                               reply_markup=ikb([("✅ Ha", f"rcdok:{cid}"), ("↩️ Yo'q", f"rc:{cid}")]))


@router.callback_query(F.data.regexp(r"^rcdok:-?\d+$"))
async def rc_del(cb: CallbackQuery):
    cid = int(cb.data.split(":")[1])
    if not await rc_row(cb, cid):
        return
    await db_exec("DELETE FROM react_channels WHERE chat_id=?", (cid,))
    await cb.answer("🗑 Olib tashlandi")
    text, kb = await react_home_view(cb.from_user.id)
    await cb.message.edit_text(text, reply_markup=kb)


# ───────────── yangi kanal postlariga avtomatik reaksiya ─────────────
async def auto_react(row, mid: int) -> None:
    await asyncio.sleep(random.uniform(2, 6))
    ok, fail, errs = await do_reactions(row["chat_id"], mid, row_emojis(row), row["cnt"])
    if ok:
        await db_exec("UPDATE react_channels SET total=total+? WHERE chat_id=?", (ok, row["chat_id"]))
    if fail and not ok:
        await notify_user(row["owner_id"], f"⚠️ <b>{esc(row['title'])}</b>: avtomatik reaksiya bosilmadi.\n"
                                           + err_summary(errs) + "\n\n🩺 Kanal sozlamalaridan «Tekshirish va test» ni bosing.",
                          cooldown=1800)


@router.channel_post()
async def on_channel_post(m: Message):
    row = await db_one("SELECT * FROM react_channels WHERE chat_id=?", (m.chat.id,))
    if not row:
        return
    LAST_POST[m.chat.id] = m.message_id
    if not row["auto"] or not await react_allowed(row["owner_id"]):
        return
    spawn(auto_react(row, m.message_id))


# ───────────── ✉️ SHAXSIY XABAR (@userlarga) ─────────────
def parse_usernames(raw: str) -> list[str]:
    """Faqat @username yoki t.me/username ko'rinishidagilar olinadi (oddiy so'zlar emas)."""
    out: dict[str, str] = {}
    for tok in re.split(r"[\s,;]+", raw or ""):
        tok = tok.strip().strip("()[]<>.")
        if not tok:
            continue
        mm = re.match(r"^(?:https?://)?(?:t\.me|telegram\.me)/([A-Za-z]\w+)/?$", tok)
        if mm:
            u = mm.group(1)
        elif tok.startswith("@"):
            u = tok[1:]
        else:
            continue
        if UNAME_OK.match(u):
            out.setdefault(u.lower(), u)
    return list(out.values())


def dm_delays() -> tuple[int, int]:
    lo = max(cfg_int("dm_min_delay"), 1)
    return lo, max(cfg_int("dm_max_delay"), lo)


async def dm_ask_text(target: Message, state: FSMContext, acc_id: int, rem: int) -> None:
    await state.update_data(acc_id=acc_id)
    await state.set_state(DmS.text)
    await target.answer(f"✉️ <b>Shaxsiy xabar yuborish</b>\n\n📊 Qolgan limit: <b>{rem_txt(rem)}</b> ta xabar\n\n"
                        "1️⃣ Yuboriladigan <b>matnni</b> yuboring.\n"
                        "⚠️ Matnda guruhingizning <b>taklif havolasi</b> (https://t.me/...) bo'lishi shart.",
                        reply_markup=cancel_kb())


@router.message(F.text == B_DM)
async def dm_menu(m: Message, state: FSMContext):
    uid = m.from_user.id
    await reset(state, uid)
    if not cfg_on("dm_on") and not is_staff(uid):
        await m.answer("🚧 Shaxsiy xabar xizmati vaqtincha o'chirilgan.")
        return
    if uid in DM_JOBS:
        await m.answer("⏳ Sizda xabar yuborish jarayoni ketmoqda.", reply_markup=ikb([("🛑 To'xtatish", "dmstop")]))
        return
    rem = await dm_remaining(uid)
    if rem <= 0:
        await m.answer(NOLIMIT_TEXT, reply_markup=buy_kb("Shaxsiy xabar limiti", uid))
        return
    accs = await db_all("SELECT * FROM accounts WHERE owner_id=? AND status='active'", (uid,))
    if not accs:
        await m.answer("❌ <b>Akkaunt ulanmagan!</b>\n\nXabar yuborish uchun avval 👤 <b>Akkauntlarim</b> bo'limidan "
                       "akkaunt ulang.")
        return
    if len(accs) == 1:
        await dm_ask_text(m, state, accs[0]["id"], rem)
        return
    rows = [[(f"{a['name']} ({a['phone']})", f"dmacc:{a['id']}")] for a in accs]
    await m.answer("👤 Qaysi akkaunt orqali yuboramiz?", reply_markup=ikb(*rows))


@router.callback_query(F.data.regexp(r"^dmacc:\d+$"))
async def dm_pick_acc(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    acc = await db_one("SELECT id FROM accounts WHERE id=? AND owner_id=? AND status='active'",
                       (int(cb.data.split(":")[1]), uid))
    if not acc:
        await cb.answer("Akkaunt topilmadi.", show_alert=True)
        return
    rem = await dm_remaining(uid)
    if rem <= 0:
        await cb.answer("Limit yo'q", show_alert=True)
        return
    await cb.answer()
    await dm_ask_text(cb.message, state, acc["id"], rem)


@router.message(DmS.text)
async def dm_text(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    if not t or len(t) > 3500:
        await m.answer("❌ Matn bo'sh yoki juda uzun (3500 belgigacha).")
        return
    if not re.search(r"(?:t\.me|telegram\.me)/\S+", t, re.I):
        await m.answer("❌ Matnda <b>guruh taklif havolasi</b> yo'q. Havola (https://t.me/...) qo'shib qayta yuboring.")
        return
    await state.update_data(text=t)
    await state.set_state(DmS.users)
    ncoll = (await db_one("SELECT COUNT(DISTINCT username) c FROM collected WHERE owner_id=? AND username!=''",
                          (m.from_user.id,)))["c"]
    kb = ikb([(f"📁 Yig'ilgan userlardan ({ncoll})", "dmcoll")]) if ncoll else None
    await m.answer("2️⃣ Endi <b>@username</b>'larni yuboring (har birini yangi qatorga yoki vergul bilan).\n"
                   "Yoki <b>.txt / .csv</b> fayl yuboring (har qatorda @username, 5 MB gacha).\n\n"
                   "Soni cheksiz, lekin xabar faqat qolgan limitcha yuboriladi.", reply_markup=kb)


async def dm_confirm(target: Message, state: FSMContext, uid: int, names: list[str]) -> None:
    rem = await dm_remaining(uid)
    will = min(len(names), rem)
    lo, hi = dm_delays()
    eta = max(int(will * (lo + hi) / 2 / 60), 1)
    await state.update_data(names=names)
    await state.set_state(DmS.confirm)
    await target.answer(f"👥 Topildi: <b>{len(names)}</b> ta @username\n📊 Qolgan limit: <b>{rem_txt(rem)}</b>\n"
                        f"📤 Yuboriladi: <b>{will}</b> ta\n\n"
                        f"⏱ Xavfsizlik uchun xabarlar orasida {lo}–{hi} soniya pauza qilinadi (taxminan {eta} daqiqa).",
                        reply_markup=ikb([("🚀 Boshlash", "dmgo")], [("❌ Bekor", "dmcancel")]))


@router.message(DmS.users)
async def dm_users(m: Message, state: FSMContext):
    raw = m.text or ""
    if m.document:
        if (m.document.file_size or 0) > 5_000_000:
            await m.answer("❌ Fayl 5 MB dan katta.")
            return
        buf = io.BytesIO()
        try:
            await BOT.download(m.document, destination=buf)
        except Exception:  # noqa: BLE001
            await m.answer("❌ Faylni o'qib bo'lmadi.")
            return
        raw = buf.getvalue().decode("utf-8-sig", errors="ignore")
    names = parse_usernames(raw)
    if not names:
        await m.answer("❌ @username topilmadi. Har biri <code>@nom</code> ko'rinishida bo'lsin.")
        return
    await dm_confirm(m, state, m.from_user.id, names)


@router.callback_query(F.data == "dmcoll", DmS.users)
async def dm_from_collected(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    rows = await db_all("SELECT DISTINCT username FROM collected WHERE owner_id=? AND username!=''", (uid,))
    names = [r["username"] for r in rows if UNAME_OK.match(r["username"])]
    if not names:
        await cb.answer("Yig'ilgan username yo'q.", show_alert=True)
        return
    await cb.answer()
    await dm_confirm(cb.message, state, uid, names)


@router.callback_query(F.data == "dmcancel")
async def dm_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.answer()
    try:
        await cb.message.edit_text("↩️ Bekor qilindi.")
    except TelegramBadRequest:
        pass
    await cb.message.answer("🏠", reply_markup=main_kb(cb.from_user.id))


@router.callback_query(F.data == "dmgo", DmS.confirm)
async def dm_go(cb: CallbackQuery, state: FSMContext):
    uid = cb.from_user.id
    d = await state.get_data()
    names, text, acc_id = d.get("names"), d.get("text"), d.get("acc_id")
    if not (names and text and acc_id):
        await cb.answer("Jarayon eskirgan. Qaytadan boshlang.", show_alert=True)
        return
    if uid in DM_JOBS:
        await cb.answer("Jarayon allaqachon ketmoqda.", show_alert=True)
        return
    if await dm_remaining(uid) <= 0:
        await cb.answer("Limit tugagan.", show_alert=True)
        return
    if not await db_one("SELECT 1 FROM accounts WHERE id=? AND owner_id=? AND status='active'", (acc_id, uid)):
        await cb.answer("Akkaunt ishlamayapti.", show_alert=True)
        return
    await state.clear()
    await cb.answer("🚀 Boshlandi")
    DM_JOBS[uid] = asyncio.Event()
    await cb.message.answer("🏠", reply_markup=main_kb(uid))
    msg = await cb.message.answer("⏳ Yuborish boshlanmoqda...", reply_markup=ikb([("🛑 To'xtatish", "dmstop")]))
    spawn(run_dm(uid, acc_id, text, names, msg))


@router.callback_query(F.data == "dmstop")
async def dm_stop(cb: CallbackQuery):
    ev = DM_JOBS.get(cb.from_user.id)
    if ev and not ev.is_set():
        ev.set()
        await cb.answer("🛑 To'xtatilmoqda...")
    else:
        await cb.answer("Faol jarayon yo'q.", show_alert=True)


async def run_dm(uid: int, acc_id: int, text: str, names: list[str], msg: Message) -> None:
    stop = DM_JOBS.get(uid) or asyncio.Event()
    total = len(names)
    sent = fail = unk = retries = 0
    started = time.monotonic()
    last_edit = 0.0
    title = "✅ Yuborish yakunlandi!"
    stop_kb = ikb([("🛑 To'xtatish", "dmstop")])

    async def show(t: str, force: bool = False, final: bool = False) -> None:
        nonlocal last_edit
        now = time.monotonic()
        if not (force or final) and now - last_edit < 6:
            return
        last_edit = now
        extra = [f"📊 Qolgan limit: {rem_txt(await dm_remaining(uid))}"]
        body = "<code>" + esc(panel_text(t, sent, total, started, fail, 0, extra)) + "</code>"
        try:
            await BOT.edit_message_text(body, chat_id=msg.chat.id, message_id=msg.message_id,
                                        reply_markup=None if final else stop_kb)
        except Exception:  # noqa: BLE001
            pass

    try:
        client = await get_client(acc_id)
        if not client:
            title = "❌ Akkaunt ishlamayapti!"
        else:
            lo, hi = dm_delays()
            i = 0
            while i < total:
                if stop.is_set():
                    title = "🛑 To'xtatildi!"
                    break
                if await dm_remaining(uid) <= 0:
                    title = "📈 Limit tugadi!"
                    break
                try:
                    await client.send_message(names[i], with_sign(text, "\n\n"))
                    sent += 1
                    i += 1
                    retries = unk = 0
                    await dm_consume(uid)
                except (FloodWaitError, SlowModeWaitError) as e:
                    wait = int(getattr(e, "seconds", 30)) + 1
                    retries += 1
                    if wait > 600 or retries > 3:
                        title = f"⏳ Telegram cheklovi ({wait}s), to'xtatildi!"
                        break
                    await show(f"⏳ Telegram cheklovi: {wait}s kutilmoqda...", force=True)
                    await interruptible_sleep(stop, wait)
                    continue
                except PeerFloodError:
                    title = "🚫 Telegram spam cheklovi! Akkaunt dam olsin."
                    break
                except (UserPrivacyRestrictedError, UserIsBlockedError, InputUserDeactivatedError,
                        UsernameNotOccupiedError, UsernameInvalidError, ValueError):
                    fail += 1
                    i += 1
                except AUTH_ERRORS:
                    raise
                except Exception as e:  # noqa: BLE001
                    log.warning("dm send: %s", e)
                    fail += 1
                    i += 1
                    unk += 1
                    if unk >= 5:
                        title = "⚠️ Ketma-ket xatolar, to'xtatildi!"
                        break
                await show("⏳ Xabarlar yuborilmoqda...")
                await interruptible_sleep(stop, random.uniform(lo, hi))
    except AUTH_ERRORS as e:
        await mark_dead(acc_id, type(e).__name__)
        title = "❌ Akkaunt sessiyasi tugagan!"
    except Exception as e:  # noqa: BLE001
        log.warning("run_dm: %s", e)
        title = "❌ Xatolik yuz berdi!"
    finally:
        DM_JOBS.pop(uid, None)
    await show(title, final=True)
    await notify_user(uid, f"✉️ Yuborish tugadi: ✅ {sent} | ❌ {fail}\n📊 Qolgan limit: {rem_txt(await dm_remaining(uid))}")


# ───────────── ADMIN (faqat ega): yordamchi botlar, muddat va limit berish ─────────────
async def render_rb(cb: CallbackQuery) -> None:
    rows_db = await db_all("SELECT * FROM react_bots ORDER BY id")
    rows = [[(f"🗑 @{r['username']}", f"ad:rbd:{r['id']}")] for r in rows_db[:40]]
    rows.append([("➕ Bot qo'shish (token)", "ad:rba")])
    rows.append([("🔄 Barcha kanallarga qayta qo'shish", "ad:rbs")])
    rows.append([("🔙 Orqaga", "ad:home")])
    chs = (await db_one("SELECT COUNT(*) c FROM react_channels"))["c"]
    await cb.message.edit_text(
        f"🤖 <b>Reaksiya botlari:</b> {len(rows_db)} ta | 📢 ulangan kanallar: {chs}\n\n"
        "Yangi bot qo'shish: @BotFather dan olingan <b>API token</b>ni yuborsangiz bo'ldi "
        "(bir nechta bo'lsa, har birini yangi qatorga). Bot o'zi tekshiriladi va barcha ulangan kanallarga qo'shiladi."
        + ("\n\n<i>Faqat dastlabki 40 ta ko'rsatilgan.</i>" if len(rows_db) > 40 else ""),
        reply_markup=ikb(*rows))


@admin.callback_query(F.data == "ad:rb")
async def ad_rb(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer()
    await render_rb(cb)


@admin.callback_query(F.data == "ad:rba")
async def ad_rb_add(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    await cb.answer()
    await state.set_state(AdminS3.rb_add)
    await cb.message.answer("🤖 Bot token(lar)ini yuboring (har birini yangi qatorga).\n"
                            "Xavfsizlik uchun xabaringiz o'chirib yuboriladi.", reply_markup=cancel_kb())


@admin.message(AdminS3.rb_add)
async def ad_rb_add_do(m: Message, state: FSMContext):
    if not is_owner(m.from_user.id):
        return
    raw = m.text or ""
    try:
        await m.delete()
    except Exception:  # noqa: BLE001
        pass
    added, errs = await add_react_bots(raw)
    if not added and not errs:
        await m.answer("❌ Token topilmadi. Format: <code>123456789:AAH...</code>")
        return
    await state.clear()
    txt = ""
    if added:
        txt += f"✅ Qo'shildi: {', '.join('@' + esc(u) for _, u in added)}\n"
    if errs:
        txt += "⚠️ " + "\n⚠️ ".join(esc(e) for e in errs)
    if added:
        txt += "\n\n⏳ Ulangan kanallarga qo'shilmoqda (fonda)..."
        spawn(sync_helpers([t for t, _ in added]))
    await audit(m.from_user.id, "react_bot_add", str(len(added)))
    await m.answer(txt, reply_markup=main_kb(OWNER_ID))


@admin.callback_query(F.data.regexp(r"^ad:rbd:\d+$"))
async def ad_rb_del(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    bid = int(cb.data.split(":")[2])
    b = REACT_BOTS.pop(bid, None)
    if b:
        try:
            await b.session.close()
        except Exception:  # noqa: BLE001
            pass
    await db_exec("DELETE FROM react_bots WHERE id=?", (bid,))
    await audit(cb.from_user.id, "react_bot_del", str(bid))
    await cb.answer("🗑 O'chirildi")
    await render_rb(cb)


@admin.callback_query(F.data == "ad:rbs")
async def ad_rb_sync(cb: CallbackQuery):
    if not await owner_only(cb):
        return
    await cb.answer("⏳ Fonda boshlandi", show_alert=True)
    spawn(sync_helpers())


@admin.callback_query(F.data.regexp(r"^ad:rx:\d+$"))
async def ad_rx(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    await cb.answer()
    uid = int(cb.data.split(":")[2])
    until = await react_until(uid)
    left = "yo'q" if not until else ("cheksiz" if is_owner(uid) else fmt_left(until))
    await state.set_state(AdminS3.rx_days)
    await state.update_data(uid=uid)
    await cb.message.answer(f"❤️ <b>Reaksiya xizmati</b> — hozir: {left}\n\nNecha kun qo'shilsin?\n"
                            "• musbat son — kun qo'shadi\n• manfiy son — kun ayiradi\n• <code>0</code> — xizmatni o'chiradi",
                            reply_markup=cancel_kb())


@admin.message(AdminS3.rx_days)
async def ad_rx_do(m: Message, state: FSMContext):
    if not is_owner(m.from_user.id):
        return
    t = (m.text or "").strip()
    if not re.fullmatch(r"-?\d{1,4}", t):
        await m.answer("❌ Butun son yuboring.")
        return
    d = await state.get_data()
    uid, n = d["uid"], int(t)
    await state.clear()
    now = time.time()
    r = await db_one("SELECT until FROM react_access WHERE user_id=?", (uid,))
    cur = float(r["until"]) if r else 0.0
    new = 0.0 if n == 0 else (max(cur, now) + n * 86400 if n > 0 else cur + n * 86400)
    if new <= now:
        await db_exec("DELETE FROM react_access WHERE user_id=?", (uid,))
        await notify_user(uid, "ℹ️ Reaksiya xizmatingiz bekor qilindi.")
        res = "✅ Reaksiya xizmati o'chirildi."
    else:
        await db_exec("INSERT INTO react_access(user_id,until) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET until=excluded.until",
                      (uid, new))
        await notify_user(uid, f"❤️ Sizga <b>Reaksiya</b> xizmati berildi!\n⏳ {fmt_date(new)} gacha. «❤️ Reaksiya» tugmasini bosing.")
        res = f"✅ Reaksiya xizmati: {fmt_date(new)} gacha."
    await audit(m.from_user.id, "react_access", f"{uid} {n}k")
    card = await user_card(uid)
    await m.answer(res, reply_markup=main_kb(OWNER_ID))
    if card:
        await m.answer(card[0], reply_markup=card[1])


@admin.callback_query(F.data.regexp(r"^ad:dq:\d+$"))
async def ad_dq(cb: CallbackQuery, state: FSMContext):
    if not await owner_only(cb):
        return
    await cb.answer()
    uid = int(cb.data.split(":")[2])
    rem = await dm_remaining(uid)
    await state.set_state(AdminS3.dm_quota)
    await state.update_data(uid=uid)
    await cb.message.answer(f"✉️ <b>Shaxsiy xabar limiti</b> — hozir qolgan: <b>{rem_txt(rem)}</b>\n\n"
                            "Nechta xabar qo'shilsin?\n• musbat son — limit qo'shadi\n• manfiy son — ayiradi\n"
                            "• <code>0</code> — qolgan limitni nolga tushiradi", reply_markup=cancel_kb())


@admin.message(AdminS3.dm_quota)
async def ad_dq_do(m: Message, state: FSMContext):
    if not is_owner(m.from_user.id):
        return
    t = (m.text or "").strip()
    if not re.fullmatch(r"-?\d{1,7}", t):
        await m.answer("❌ Butun son yuboring.")
        return
    d = await state.get_data()
    uid, n = d["uid"], int(t)
    await state.clear()
    r = await db_one("SELECT quota, used FROM dm_access WHERE user_id=?", (uid,))
    used = int(r["used"]) if r else 0
    rem = 0 if n == 0 else max((int(r["quota"]) - used if r else 0) + n, 0)
    await db_exec("INSERT INTO dm_access(user_id,quota,used) VALUES(?,?,0) "
                  "ON CONFLICT(user_id) DO UPDATE SET quota=excluded.quota", (uid, used + rem))
    if n > 0:
        await notify_user(uid, f"✉️ Sizga <b>{n}</b> ta shaxsiy xabar limiti qo'shildi!\n📊 Qolgan: <b>{rem}</b>")
    await audit(m.from_user.id, "dm_quota", f"{uid} {n}")
    card = await user_card(uid)
    await m.answer(f"✅ Qolgan limit: <b>{rem}</b>", reply_markup=main_kb(OWNER_ID))
    if card:
        await m.answer(card[0], reply_markup=card[1])


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
                if OWNER_ID:
                    await send_backup(OWNER_ID)
        except Exception as e:  # noqa: BLE001
            log.warning("maintenance: %s", e)


async def main() -> None:
    global BOT, BOT_USERNAME
    missing = [k for k, v in dict(BOT_TOKEN=BOT_TOKEN, API_ID=API_ID, API_HASH=API_HASH).items() if not v]
    if missing:
        raise SystemExit(f"❌ Sozlanmagan: {', '.join(missing)}  (.env faylni to'ldiring)")
    await init_db()
    await load_cfg()
    await load_react_bots()
    if cfg("turbo_migrated") != "1":      # bir martalik: eski standart (2s) -> yangi standart (TURBO 0.3s)
        await db_exec("UPDATE users SET mention_delay=0 WHERE mention_delay=2")
        await cfg_set("turbo_migrated", "1")
    BOT = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    BOT_USERNAME = (await BOT.get_me()).username or ""
    try:
        await BOT.set_my_commands([BotCommand(command="start", description="Botni ishga tushirish / bosh menyu"),
                                   BotCommand(command="stop", description="Barcha ishlayotgan utaglarni to'xtatish")])
    except Exception as e:  # noqa: BLE001
        log.warning("set_my_commands: %s", e)
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
        for hb in REACT_BOTS.values():
            try:
                await hb.session.close()
            except Exception:  # noqa: BLE001
                pass
        await DB.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
