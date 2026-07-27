"""
telegram_scraper.py
--------------------
كيراقب قنوات Telegram خارجية (via Telethon، حساب مستخدم عادي — ماشي bot،
لأن البوتات ما يقدروش يقراو رسائل قنوات ما همهمش أدمن فيها) وكيلقط روابط
AliExpress جديدة، كيولد ليها رابط أفلييت حقيقي، وكينشرها فـ القناة ديالك
مباشرة (real-time) بلا ما ينتظر وقت الذروة — الصفقات حساسة للوقت.

الإعداد (مرة وحدة):
1) دخل لـ https://my.telegram.org → API development tools → خلق app
   جديد → خذ API_ID و API_HASH
2) شغل `python generate_session.py` محليًا (على جهازك، ماشي على Render)
   باش تسجل الدخول بحسابك وتولد Session String
3) حط API_ID, API_HASH, و TELETHON_SESSION كـ environment variables فـ Render

Telethon محتاج event loop ديالو (asyncio) منفصل عن Flask، فكيخدم هنا فـ
Thread فـ الخلفية.
"""

import re
import threading
import asyncio

PRODUCT_LINK_RE = re.compile(r"(https?://[^\s]*aliexpress\.[^\s]+)", re.IGNORECASE)
PRICE_RE = re.compile(r"R\$\s*([\d.,]+)")


class TelegramScraperService:
    """
    استعمال:
        scraper = TelegramScraperService(
            api_id, api_hash, session_string,
            source_channels=["canal1", "canal2"],
            on_deal_found=callback_function,
            log_fn=my_log,
        )
        scraper.start()  # كيبدا Thread فـ الخلفية، كيرجع فورًا

    on_deal_found(product_url: str) كتنادى فـ كل مرة كيلقى فيها رابط AliExpress
    جديد فـ رسالة من قنوات المراقبة. المنطق ديال fetch/generate/publish
    مسؤول عليه الكود اللي عيط على هاد السيرفيس (app.py)، باش هاد الملف يبقى
    مستقل بلا اعتماد على ali_engine/publisher مباشرة.
    """

    def __init__(self, api_id, api_hash, session_string, source_channels,
                 on_deal_found, log_fn=None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_string = session_string
        self.source_channels = [c.strip().lstrip("@") for c in source_channels if c.strip()]
        self.on_deal_found = on_deal_found
        self.log = log_fn or (lambda *a, **k: None)
        self._thread = None
        self._client = None

    @property
    def is_configured(self):
        return bool(self.api_id and self.api_hash and self.session_string and self.source_channels)

    def start(self):
        if not self.is_configured:
            self.log("Telegram scraper: credenciais/canais ausentes — desativado", "warn")
            return
        self._thread = threading.Thread(target=self._run_forever, daemon=True)
        self._thread.start()
        self.log(f"Telegram scraper: monitorando {len(self.source_channels)} canal(is)", "ok")

    def _run_forever(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_main())
        except Exception as e:
            self.log(f"Telegram scraper erro fatal: {e}", "err")

    async def _async_main(self):
        # استيراد Telethon هنا (بلا فـ رأس الملف) باش الملف يقدر يتقرا حتى بلا
        # ما تكون Telethon مثبتة، إلا كان المستخدم ما بغاش يستعمل هاد الميزة
        from telethon import TelegramClient, events
        from telethon.sessions import StringSession

        self._client = TelegramClient(
            StringSession(self.session_string), self.api_id, self.api_hash
        )

        @self._client.on(events.NewMessage(chats=self.source_channels))
        async def handler(event):
            self.log(f"Scraper: nova mensagem recebida em {getattr(event.chat, 'username', '') or event.chat_id}", "info")
            text = event.raw_text or ""
            match = PRODUCT_LINK_RE.search(text)
            product_url = None
            if match:
                product_url = match.group(1)
            else:
                # بزاف قنوات الصفقات كتحط الرابط فـ زر (inline button) بدل النص
                try:
                    if event.message.buttons:
                        for row in event.message.buttons:
                            for btn in row:
                                url = getattr(btn, "url", None)
                                if url and "aliexpress." in url.lower():
                                    product_url = url
                                    break
                            if product_url:
                                break
                except Exception:
                    pass
            if not product_url:
                return
            try:
                self.on_deal_found(product_url)
            except Exception as e:
                self.log(f"Telegram scraper: erro processando deal — {e}", "err")

        await self._client.start()
        self.log("Telegram scraper: conectado com sucesso", "ok")
        await self._client.run_until_disconnected()
