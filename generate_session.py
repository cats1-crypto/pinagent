#!/usr/bin/env python3
"""
generate_session.py
--------------------
شغل هاد السكريبت **مرة وحدة بوحدك، محليًا** (فـ Termux ولا الكومبيوتر ديالك،
ماشي فوق Render) باش تسجل الدخول بحسابك ديال Telegram وتولد "Session
String" — نص طويل كيسمح للسيرفر (Render) يقرا القنوات بلا ما يحتاج تعاود
تسجل الدخول (بلا رقم الهاتف، بلا كود OTP) فـ كل مرة.

الإعداد قبل ما تشغل:
    pip install telethon --break-system-packages
    export TELEGRAM_API_ID=123456
    export TELEGRAM_API_HASH=abcdef123456...

(API_ID و API_HASH كتجيهم من https://my.telegram.org → API development tools)

التشغيل:
    python generate_session.py

غادي يطلب منك رقم الهاتف، بعد كود التحقق (OTP) اللي غادي توصل ليك فـ
Telegram، وربما كلمة السر إلا كان عندك 2FA مفعلة. فـ الآخر غادي يطبع ليك
Session String طويلة — انسخها وحطها كـ environment variable اسمها
TELETHON_SESSION فـ Render.

⚠️ الـ Session String هادي كيفها كيف كلمة السر ديال الحساب بأكمله — ما
تشاركهاش مع حتى واحد، وما تكتبهاش فـ كود مرفوع لـ GitHub عمومي.
"""

import os

try:
    from telethon.sync import TelegramClient
    from telethon.sessions import StringSession
except ImportError:
    raise SystemExit(
        "❌ Telethon ماشي مثبتة. شغل: pip install telethon --break-system-packages"
    )

API_ID = os.environ.get("TELEGRAM_API_ID")
API_HASH = os.environ.get("TELEGRAM_API_HASH")

if not API_ID or not API_HASH:
    raise SystemExit(
        "❌ خاصك تضبط TELEGRAM_API_ID و TELEGRAM_API_HASH قبل ما تشغل هاد السكريبت.\n"
        "جيبهم من https://my.telegram.org → API development tools"
    )

with TelegramClient(StringSession(), int(API_ID), API_HASH) as client:
    session_string = client.session.save()
    print("\n" + "=" * 60)
    print("✅ Session String ديالك (احتفظ بيها بشكل آمن):")
    print("=" * 60)
    print(session_string)
    print("=" * 60)
    print("\nحطها فـ Render → Environment → TELETHON_SESSION")
