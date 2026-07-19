import os, json, hmac, hashlib, urllib.parse, urllib.request, ssl, threading, time
from flask import Flask, jsonify, request
from telegram_templates import build_telegram_message
from datetime import datetime, timezone, timedelta

app = Flask(__name__, static_folder="static")
ctx = ssl.create_default_context()

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_KEY", "")
ALI_KEY       = os.environ.get("ALI_KEY", "")
ALI_SECRET    = os.environ.get("ALI_SECRET", "")
ALI_TRACKING  = os.environ.get("ALI_TRACKING", "529958")
PIN_TOKEN     = os.environ.get("PIN_TOKEN", "")
PIN_BOARD_ID  = os.environ.get("PIN_BOARD_ID", "")
TG_TOKEN      = os.environ.get("TG_TOKEN", "")
TG_CHANNEL    = os.environ.get("TG_CHANNEL", "@Ofertassdiariasaliexpresss")
BLOGGER_TOKEN   = os.environ.get("BLOGGER_TOKEN", "")
BLOGGER_REFRESH = os.environ.get("BLOGGER_REFRESH", "")
BLOGGER_CLIENT  = os.environ.get("BLOGGER_CLIENT_ID", "")
BLOGGER_SECRET  = os.environ.get("BLOGGER_CLIENT_SECRET", "")
BLOGGER_BLOG_ID = os.environ.get("BLOGGER_BLOG_ID", "2781402232561095495")
BUFFER_TOKEN    = os.environ.get("BUFFER_TOKEN", "")
BUFFER_PROFILES = os.environ.get("BUFFER_PROFILES", "")  # comma-separated Buffer channel IDs

BUFFER_API_URL = "https://api.buffer.com"

POST_CHAR_LIMIT = 250

# هاشتاغات ترند فـ البرازيل لقطاع achadinhos/aliexpress (كتتبدل بالتناوب باش
# المنشورات ما تبقاش ديما بنفس الهاشتاغات).
TRENDING_HASHTAGS_BR = [
    "#achadinhos", "#achadinhosdodia", "#aliexpress", "#oferta",
    "#promocao", "#desconto", "#comprasonline", "#tiktokmademebuyit",
    "#viral", "#brasil", "#fretegratis", "#achadinhosaliexpress",
]

def pick_trending_hashtags(budget_chars, day_offset=0):
    """
    كتختار هاشتاغات ترند فـ البرازيل بقدر المساحة المتاحة (budget_chars) بلا
    ما تتعداها. day_offset كيبدل نقطة البداية فـ القائمة باش تتنوع المنشورات.
    """
    if budget_chars <= 0:
        return ""
    n = len(TRENDING_HASHTAGS_BR)
    rotated = TRENDING_HASHTAGS_BR[day_offset % n:] + TRENDING_HASHTAGS_BR[:day_offset % n]
    chosen, used = [], 0
    for tag in rotated:
        add_len = len(tag) + (1 if chosen else 0)
        if used + add_len > budget_chars:
            continue
        chosen.append(tag)
        used += add_len
    return " ".join(chosen)

def build_capped_post(title, sale, disc, aff_url, max_len=POST_CHAR_LIMIT, day_offset=0):
    """
    كتبني منشور مختصر (Telegram أو Buffer/X) ما كيتعداش max_len حرف، بما فيه
    السعر والرابط وهاشتاغات ترند فـ البرازيل. العنوان كيتقلص أولاً إلا خص المكان.
    """
    price_line = f"🔥 R$ {sale} (-{disc}%)"
    cta = f"👉 {aff_url}"
    # مساحة محجوزة للسعر + الرابط + الأسطر الفارغة بينهم
    reserved = len(price_line) + len(cta) + 2
    title_budget = max(15, max_len - reserved - 30)  # ~30 حرف محجوزين للهاشتاغات
    short_title = title if len(title) <= title_budget else title[:max(0, title_budget - 1)].rstrip() + "…"

    body = f"{price_line}\n{short_title}\n{cta}"
    remaining = max_len - len(body) - 1  # -1 للسطر الفارغ قبل الهاشتاغات
    hashtags = pick_trending_hashtags(remaining, day_offset)
    post = body + (f"\n{hashtags}" if hashtags else "")
    return post[:max_len]

PEAK = {
    0: ["09:00","12:00","20:00","21:00"],
    1: ["12:00","15:00","20:00","21:00"],
    2: ["09:00","13:00","20:00","21:00"],
    3: ["10:00","14:00","19:00","21:00"],
    4: ["10:00","12:00","19:00","20:00"],
    5: ["20:00","21:00"],
    6: ["09:00","10:00","20:00","21:00"],
}
KEYWORDS = [
    "fone bluetooth sem fio",
    "smartwatch barato 2024",
    "cabo usb tipo c carga rapida",
    "case celular transparente",
    "led strip rgb quarto",
    "organizador cozinha gaveta",
    "brinquedo educativo crianca",
]
DAYS = ["Dom","Seg","Ter","Qua","Qui","Sex","Sab"]

logs = []
stats = {"today": 0, "total": 0, "last_run": None}

def get_brt():
    return datetime.now(timezone(timedelta(hours=-3)))

def add_log(msg, level="info"):
    ts = get_brt().strftime("%H:%M:%S")
    entry = {"ts": ts, "msg": msg, "level": level}
    logs.append(entry)
    if len(logs) > 100:
        logs.pop(0)
    print(f"[{ts}] {msg}", flush=True)

def http_post(url, body, headers=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read())

def ali_sign(params, secret):
    """
    توقيع HMAC-SHA256 المطلوب من AliExpress Open Platform لـ endpoint /sync (v2).
    نفس الطريقة المستعملة فـ bot.py (Termux) — بلا "wrap" بالـ secret فالبداية/النهاية
    (تلك كانت صيغة MD5 القديمة لـ TOP Gateway وما كتخدمش مع sign_method=sha256).
    """
    sorted_params = sorted(params.items())
    base_string = "".join(f"{k}{v}" for k, v in sorted_params)
    return hmac.new(
        secret.encode("utf-8"), base_string.encode("utf-8"), hashlib.sha256
    ).hexdigest().upper()

def generate_affiliate_link(product_url, promotion_link_type="2"):
    """
    كتستدعي aliexpress.affiliate.link.generate الحقيقي وترجع رابط أفلييت
    حقيقي (بتتبع + خصم عملات على الموبايل). كترجع None إلا فشلت أو
    الـ credentials ناقصين، باش الكود اللي كيناديها يقدر يرجع لرابط عادي.
    """
    if not ALI_KEY or not ALI_SECRET:
        return None
    try:
        params = {
            "app_key": ALI_KEY,
            "method": "aliexpress.affiliate.link.generate",
            "sign_method": "sha256",
            "timestamp": str(int(time.time() * 1000)),
            "format": "json",
            "v": "2.0",
            "promotion_link_type": promotion_link_type,
            "source_values": product_url,
            "tracking_id": ALI_TRACKING,
        }
        params["sign"] = ali_sign(params, ALI_SECRET)
        url = "https://api-sg.aliexpress.com/sync?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, context=ctx, timeout=15) as r:
            data = json.loads(r.read())
        promo_links = (
            data.get("aliexpress_affiliate_link_generate_response", {})
            .get("resp_result", {})
            .get("result", {})
            .get("promotion_links", {})
            .get("promotion_link", [])
        )
        if promo_links:
            return promo_links[0]["promotion_link"]
        add_log(f"Link generate vazio (type={promotion_link_type}): {data}", "warn")
    except Exception as e:
        add_log(f"Link generate erro: {e}", "warn")
    return None


def mock_products(kw, n=2):
    return [
        {"product_id":"1005001","product_title":f"Fone Bluetooth 5.3 TWS {kw}",
         "sale_price":"29.90","original_price":"79.90","evaluate_rate":"96%",
         "product_main_image_url":"https://ae01.alicdn.com/kf/HTB1.jpg"},
        {"product_id":"1005002","product_title":f"Smartwatch {kw} Pro Max",
         "sale_price":"45.50","original_price":"120.00","evaluate_rate":"94%",
         "product_main_image_url":"https://ae01.alicdn.com/kf/HTB2.jpg"},
    ][:n]

def fetch_products(keyword, n=2):
    if not ALI_KEY or not ALI_SECRET:
        add_log("Demo mode — sem credenciais AliExpress", "warn")
        return mock_products(keyword, n)
    try:
        params = {
            "app_key": ALI_KEY,
            "method": "aliexpress.affiliate.product.query",
            "sign_method": "sha256",
            "timestamp": str(int(time.time() * 1000)),
            "format": "json",
            "v": "2.0",
            "keywords": keyword,
            "target_currency": "BRL",
            "target_language": "PT",
            "tracking_id": ALI_TRACKING,
            "page_no": "1",
            "page_size": str(n),
            "country": "BR",
        }
        params["sign"] = ali_sign(params, ALI_SECRET)
        url = "https://api-sg.aliexpress.com/sync?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, context=ctx, timeout=30) as r:
            data = json.loads(r.read())
        items = (data.get("aliexpress_affiliate_product_query_response",{})
                     .get("resp_result",{}).get("result",{})
                     .get("products",{}).get("product",[]))
        if items:
            add_log(f"AliExpress: {len(items)} produto(s)", "ok")
            return items[:n]
        else:
            add_log(f"AliExpress: resposta vazia — {data}", "warn")
    except Exception as e:
        add_log(f"AliExpress erro: {e}", "warn")
    return mock_products(keyword, n)

def generate_content(product, keyword):
    pid   = product.get("product_id","")
    title = product.get("product_title","")
    sale  = float(product.get("sale_price", 0) or 0)
    orig  = float(product.get("original_price", 0) or 0)
    disc  = round((1 - sale/orig)*100) if orig > 0 else 0
    rate  = product.get("evaluate_rate","95%")
    img   = product.get("product_main_image_url","")
    raw_url = f"https://www.aliexpress.com/item/{pid}.html"
    # promotion_link_type=2: رابط "hot product" — كيفعّل خصم العملات فـ التطبيق (موبايل)
    # promotion_link_type=0: رابط عام — كيخدم مزيان فـ المتصفح/PC
    aff_pin = generate_affiliate_link(raw_url, "2") or raw_url
    aff_tg  = generate_affiliate_link(raw_url, "0") or raw_url
    if aff_pin == raw_url:
        add_log(f"⚠️ Link de afiliado NÃO gerado para {pid} — usando link normal (sem tracking)", "warn")

    day_offset = get_brt().timetuple().tm_yday  # كيبدل الهاشتاغات كل يوم

    if not ANTHROPIC_KEY:
        capped = build_capped_post(title, sale, disc, aff_tg, POST_CHAR_LIMIT, day_offset)
        return {
            "pinterest_title": f"{title[:80]} — R$ {sale} (-{disc}%)",
            "pinterest_description": f"Achado incrível! {title} por R$ {sale}\n#achadinhos #aliexpress #oferta #desconto #brasil",
            "pinterest_alt_text": f"Produto AliExpress: {title}. Preço R$ {sale}",
            "telegram_text": capped,
            "buffer_text": capped,
            "aff_url_pin": aff_pin, "aff_url_tg": aff_tg, "image_url": img, "product": product,
        }

    prompt = f"""Copywriter afiliados Brasil — AliExpress achadinhos.
Produto: {title}
Preco: R$ {sale} (era R$ {orig}, -{disc}%)
Avaliacao: {rate} | Keyword: {keyword}
Link Pinterest: {aff_pin} | Link Telegram/Buffer: {aff_tg}
JSON SOMENTE:
{{"pinterest_title":"titulo Pin SEO max 95 chars keyword+beneficio+preco","pinterest_description":"descricao Pin 450 chars PT emojis beneficios urgencia CTA 8 hashtags #achadinhos #aliexpress #oferta #desconto #brasil #comprasonline #fretegratis #promocao","pinterest_alt_text":"alt text SEO descritivo max 300 chars","telegram_text":"mensagem CURTA max 250 caracteres TOTAL (incluindo link e hashtags) — emoji + preco + desconto + link + 2-3 hashtags trending Brasil (ex: #achadinhos #aliexpress #promocao)","buffer_text":"mesma regra do telegram_text: max 250 caracteres TOTAL, otimizado para X/Twitter, com hashtags trending Brasil"}}"""

    try:
        resp = http_post(
            "https://api.anthropic.com/v1/messages",
            {"model":"claude-sonnet-4-6","max_tokens":800,
             "messages":[{"role":"user","content":prompt}]},
            {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"}
        )
        text = next((b["text"] for b in resp.get("content",[]) if b.get("type")=="text"), "")
        content = json.loads(text.replace("```json","").replace("```","").strip())
        content.update({"aff_url_pin":aff_pin,"aff_url_tg":aff_tg,"image_url":img,"product":product})
        # حماية إضافية: Claude ممكن يتعدى الحد رغم التعليمات، فنقصو يدويًا
        for key in ("telegram_text", "buffer_text"):
            if len(content.get(key, "")) > POST_CHAR_LIMIT:
                content[key] = build_capped_post(title, sale, disc, aff_tg, POST_CHAR_LIMIT, day_offset)
        add_log(f"Claude OK: {title[:35]}...", "ok")
        return content
    except Exception as e:
        add_log(f"Claude erro: {e}", "warn")
        capped = build_capped_post(title, sale, disc, aff_tg, POST_CHAR_LIMIT, day_offset)
        return {
            "pinterest_title": f"{title[:80]} — R$ {sale} (-{disc}%)",
            "pinterest_description": f"Achado! {title} por R$ {sale}\n#achadinhos #aliexpress #oferta #brasil",
            "pinterest_alt_text": f"Produto AliExpress: {title}",
            "telegram_text": capped,
            "buffer_text": capped,
            "aff_url_pin":aff_pin,"aff_url_tg":aff_tg,"image_url":img,"product":product,
        }

def publish_pinterest(content):
    if not PIN_TOKEN or not PIN_BOARD_ID:
        return {"ok":False,"simulated":True,"ch":"pinterest"}
    try:
        resp = http_post(
            "https://api.pinterest.com/v5/pins",
            {"board_id":PIN_BOARD_ID,"title":content["pinterest_title"],
             "description":content["pinterest_description"],
             "alt_text":content["pinterest_alt_text"],
             "link":content["aff_url_pin"],
             "media_source":{"source_type":"image_url","url":content["image_url"]}},
            {"Authorization":f"Bearer {PIN_TOKEN}"}
        )
        pid = resp.get("id","")
        add_log(f"Pinterest Pin #{pid}", "ok")
        return {"ok":True,"ch":"pinterest","pin_id":pid,"url":f"https://pinterest.com/pin/{pid}"}
    except Exception as e:
        add_log(f"Pinterest erro: {e}", "err")
        return {"ok":False,"ch":"pinterest","error":str(e)}

def publish_telegram(content):
    if not TG_TOKEN:
        return {"ok":False,"simulated":True,"ch":"telegram"}
    try:
        # ✅ قوالب متنوعة بدل النص الثابت
        product = content.get("product", {})
        ali_product = {
            "title":    product.get("product_title", ""),
            "price":    float(product.get("sale_price", 0) or 0),
            "price_brl": f"R$ {product.get('sale_price','0')}",
            "original_price_brl": f"R$ {product.get('original_price','0')}",
            "discount": str(round((1 - float(product.get("sale_price",1) or 1) /
                           float(product.get("original_price",1) or 1)) * 100)),
            "rating":   product.get("evaluate_rate","4.5").replace("%",""),
            "reviews":  "500+",
            "affiliate_link": content.get("aff_url_tg",""),
            "category": "electronics",
        }
        caption = build_telegram_message(ali_product, template_type="auto")
        # القالب الخارجي (telegram_templates.py) ماشي مضمون يحترم حد الـ 250 حرف،
        # فكنرجعو للنص الجاهز المحدود مسبقًا إلا تعدى الحد (باش الرابط ما يتقطعش).
        if len(caption) > POST_CHAR_LIMIT:
            caption = content.get("telegram_text") or caption[:POST_CHAR_LIMIT]
        try:
            resp = http_post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                {"chat_id":TG_CHANNEL,"photo":content["image_url"],
                 "caption":caption,"parse_mode":"HTML"}
            )
        except Exception:
            fallback_text = content.get("telegram_text", "")
            if len(fallback_text) > POST_CHAR_LIMIT:
                fallback_text = fallback_text[:POST_CHAR_LIMIT]
            resp = http_post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                {"chat_id":TG_CHANNEL,"text":fallback_text,
                 "parse_mode":"HTML","disable_web_page_preview":False}
            )
        if resp.get("ok"):
            mid = resp.get("result",{}).get("message_id","")
            add_log(f"Telegram msg #{mid}", "ok")
            return {"ok":True,"ch":"telegram","msg_id":mid,
                    "url":f"https://t.me/{TG_CHANNEL.replace('@','')}"}
        raise Exception(resp.get("description","error"))
    except Exception as e:
        add_log(f"Telegram erro: {e}", "err")
        return {"ok":False,"ch":"telegram","error":str(e)}


def refresh_blogger_token():
    """Use refresh token to get new access token."""
    global BLOGGER_TOKEN
    if not BLOGGER_REFRESH or not BLOGGER_CLIENT or not BLOGGER_SECRET:
        return False
    try:
        resp = http_post(
            "https://oauth2.googleapis.com/token",
            {"client_id": BLOGGER_CLIENT, "client_secret": BLOGGER_SECRET,
             "refresh_token": BLOGGER_REFRESH, "grant_type": "refresh_token"}
        )
        BLOGGER_TOKEN = resp.get("access_token","")
        add_log("Blogger token refreshed OK", "ok")
        return bool(BLOGGER_TOKEN)
    except Exception as e:
        add_log(f"Blogger refresh erro: {e}", "err")
        return False

def generate_blogger_post(content, keyword):
    """Generate full HTML blog post for Blogger."""
    product = content.get("product", {})
    title   = product.get("product_title","")
    sale    = product.get("sale_price","0")
    orig    = product.get("original_price","0")
    rate    = product.get("evaluate_rate","95%")
    img     = content.get("image_url","")
    aff_url = content.get("aff_url_pin","")
    disc    = round((1-float(sale)/float(orig))*100) if float(orig)>0 else 0

    html = f"""<div style="max-width:800px;margin:0 auto;font-family:Arial,sans-serif">
<img src="{img}" alt="{title}" style="width:100%;max-width:500px;border-radius:12px;display:block;margin:0 auto 20px">
<h2 style="color:#e60023">{content.get("pinterest_title","")}</h2>
<div style="background:#fff3cd;border-left:4px solid #e60023;padding:15px;margin:20px 0;border-radius:8px">
  <p style="font-size:24px;font-weight:bold;color:#e60023;margin:0">R$ {sale}</p>
  <p style="color:#666;margin:5px 0">De <s>R$ {orig}</s> — Economia de {disc}%</p>
  <p style="color:#28a745;margin:5px 0">⭐ {rate} de aprovação dos compradores</p>
</div>
<h3>Por que comprar?</h3>
<ul style="line-height:2">
  <li>✅ Produto com alta avaliação dos compradores</li>
  <li>✅ Preço com desconto de {disc}%</li>
  <li>✅ Entrega para todo o Brasil</li>
  <li>✅ Compra segura pelo AliExpress</li>
</ul>
<div style="text-align:center;margin:30px 0">
  <a href="{aff_url}" target="_blank" rel="nofollow"
     style="background:#e60023;color:white;padding:15px 40px;border-radius:25px;text-decoration:none;font-size:18px;font-weight:bold;display:inline-block">
    🛒 Comprar Agora no AliExpress
  </a>
</div>
<p style="color:#888;font-size:12px;text-align:center">
  Preços e disponibilidade podem mudar. Verifique no site oficial.
  Links de afiliado — colaboramos com o AliExpress.
</p>
</div>"""
    return html

def publish_blogger(content, keyword):
    global BLOGGER_TOKEN
    if not BLOGGER_BLOG_ID:
        return {"ok":False,"simulated":True,"ch":"blogger"}
    # Refresh token if needed
    if not BLOGGER_TOKEN:
        if not refresh_blogger_token():
            return {"ok":False,"simulated":True,"ch":"blogger","error":"No token"}
    try:
        post_html = generate_blogger_post(content, keyword)
        product = content.get("product",{})
        labels  = ["AliExpress","Ofertas","Achadinhos","Brasil",keyword.split()[0].capitalize()]
        resp = http_post(
            f"https://www.googleapis.com/blogger/v3/blogs/{BLOGGER_BLOG_ID}/posts/",
            {"kind":"blogger#post",
             "title": content.get("pinterest_title","Oferta do Dia"),
             "content": post_html,
             "labels": labels},
            {"Authorization": f"Bearer {BLOGGER_TOKEN}"}
        )
        post_url = resp.get("url","")
        post_id  = resp.get("id","")
        add_log(f"Blogger post #{post_id}", "ok")
        return {"ok":True,"ch":"blogger","post_id":post_id,"url":post_url}
    except Exception as e:
        err = str(e)
        # Token expired — refresh and retry
        if "401" in err:
            add_log("Blogger token expirado — renovando...", "warn")
            if refresh_blogger_token():
                return publish_blogger(content, keyword)
        add_log(f"Blogger erro: {err}", "err")
        return {"ok":False,"ch":"blogger","error":err}


def _buffer_graphql(query, variables=None):
    """
    استدعاء عام لـ Buffer GraphQL API (endpoint واحد: https://api.buffer.com).
    كتستعمل Bearer token، وكترجع الـ 'data' أو كترمي Exception إلا كاين errors.
    """
    body = {"query": query}
    if variables:
        body["variables"] = variables
    resp = http_post(BUFFER_API_URL, body, {"Authorization": f"Bearer {BUFFER_TOKEN}"})
    if resp.get("errors"):
        raise Exception(resp["errors"][0].get("message", "Buffer GraphQL error"))
    return resp.get("data", {})

def _buffer_get_channel_ids():
    """كيجيب channel IDs ديال أول organization متاحة، كيستثني القنوات المفصولة."""
    data = _buffer_graphql("query { account { organizations { id } } }")
    orgs = (data.get("account") or {}).get("organizations", [])
    if not orgs:
        return []
    org_id = orgs[0]["id"]
    query = """
    query GetChannels($orgId: OrganizationId!) {
      channels(input: {organizationId: $orgId}) {
        id
        service
        isDisconnected
      }
    }
    """
    data = _buffer_graphql(query, {"orgId": org_id})
    channels = data.get("channels", []) or []
    return [c["id"] for c in channels if not c.get("isDisconnected")]

def publish_buffer(content, keyword):
    """
    ينشر مباشرة (shareNow) عبر Buffer GraphQL API الحالي (createPost mutation).
    الـ REST القديم (api.bufferapp.com/1/...) متوقف ومكانش كيخدم.
    BUFFER_PROFILES (اختياري): channel IDs مفصولة بفاصلة. إلا فارغة، كتجيب
    القنوات المتصلة تلقائيًا من الـ organization الأولى.
    """
    if not BUFFER_TOKEN:
        return {"ok": False, "simulated": True, "ch": "buffer"}
    try:
        channel_ids = [c.strip() for c in BUFFER_PROFILES.split(",") if c.strip()]
        if not channel_ids:
            channel_ids = _buffer_get_channel_ids()
        if not channel_ids:
            return {"ok": False, "ch": "buffer", "error": "No channels found"}

        product = content.get("product", {})
        title   = product.get("product_title", "")
        sale    = product.get("sale_price", "0")
        orig    = product.get("original_price", "0")
        disc    = round((1-float(sale)/float(orig))*100) if float(orig)>0 else 0
        aff_url = content.get("aff_url_pin", "")
        img     = content.get("image_url", "")
        rate    = product.get("evaluate_rate", "95%")

        text = content.get("buffer_text") or f"{title}\nR$ {sale} (-{disc}%)\n{aff_url}"
        if len(text) > POST_CHAR_LIMIT:
            text = text[:POST_CHAR_LIMIT]

        mutation = """
        mutation CreatePost($input: CreatePostInput!) {
          createPost(input: $input) {
            ... on PostActionSuccess { post { id status } }
            ... on InvalidInputError { message }
            ... on UnauthorizedError { message }
            ... on UnexpectedError { message }
            ... on RestProxyError { message }
            ... on LimitReachedError { message }
            ... on NotFoundError { message }
          }
        }
        """

        results = []
        for cid in channel_ids[:3]:  # حد أقصى 3 قنوات فـ كل دفعة
            try:
                assets = []
                if img:
                    assets = [{"image": {"url": img, "metadata": {"altText": (title[:100] or "AliExpress product")}}}]
                variables = {
                    "input": {
                        "channelId": cid,
                        "schedulingType": "automatic",
                        "mode": "shareNow",
                        "text": text,
                        "assets": assets,
                        "source": "PinAgentCloud",
                    }
                }
                data = _buffer_graphql(mutation, variables)
                payload = data.get("createPost", {}) or {}
                if payload.get("post"):
                    results.append(cid)
                else:
                    add_log(f"Buffer canal {cid}: {payload.get('message','erro desconhecido')}", "warn")
            except Exception as e:
                add_log(f"Buffer canal {cid}: {e}", "warn")

        if results:
            add_log(f"Buffer: {len(results)} canal(is) publicado(s)", "ok")
            return {"ok": True, "ch": "buffer", "profiles": len(results)}
        return {"ok": False, "ch": "buffer", "error": "All channels failed"}
    except Exception as e:
        add_log(f"Buffer erro: {e}", "err")
        return {"ok": False, "ch": "buffer", "error": str(e)}

def run_pipeline(manual=False):
    brt = get_brt()
    day_idx = (brt.weekday() + 1) % 7
    keyword = KEYWORDS[day_idx]
    add_log(f"Pipeline {'MANUAL' if manual else 'AUTO'} — '{keyword}'", "ok")
    products = fetch_products(keyword, n=2)
    results = []
    for p in products:
        content = generate_content(p, keyword)
        r_pin = publish_pinterest(content)
        r_tg  = publish_telegram(content)
        r_blog   = publish_blogger(content, keyword)
        r_buffer = publish_buffer(content, keyword)
        if r_pin.get("ok") or r_tg.get("ok"): stats["today"] += 1; stats["total"] += 1
        results.append({
            "product": p.get("product_title","")[:50],
            "pinterest": r_pin, "telegram": r_tg, "blogger": r_blog, "buffer": r_buffer,
            "content": {"title": content.get("pinterest_title",""),
                        "description": content.get("pinterest_description","")[:200],
                        "image": content.get("image_url","")}
        })
    stats["last_run"] = brt.strftime("%H:%M BRT")
    add_log(f"Concluido — {len(results)} produto(s)", "ok")
    return results

def scheduler():
    fired = set()
    while True:
        try:
            brt = get_brt()
            hhmm = brt.strftime("%H:%M")
            day  = (brt.weekday() + 1) % 7
            key  = f"{day}-{hhmm}"
            if hhmm in PEAK.get(day, []) and key not in fired:
                fired.add(key)
                add_log(f"Pico: {hhmm} BRT — publicando!", "ok")
                run_pipeline()
            # Clear fired keys every hour
            if brt.minute == 0 and brt.second < 30:
                fired.clear()
        except Exception as e:
            add_log(f"Scheduler: {e}", "err")
        time.sleep(30)

threading.Thread(target=scheduler, daemon=True).start()

HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<meta name="theme-color" content="#0A0A0F">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>PinAgent Cloud</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;}
:root{--bg:#0A0A0F;--s:#141420;--s2:#1E1E30;--bd:#2D2D44;--red:#E60023;--or:#FF6B35;--gr:#22C55E;--yw:#F59E0B;--tx:#F0F0F0;--mu:#888899;--fa:#44445A;--mono:'SF Mono','Courier New',monospace;}
html,body{background:var(--bg);color:var(--tx);font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;height:100%;overflow:hidden;-webkit-font-smoothing:antialiased;}
#app{display:flex;flex-direction:column;height:100dvh;}
#bar{background:var(--bg);border-bottom:1px solid var(--bd);padding:12px 18px;display:flex;align-items:center;gap:10px;flex-shrink:0;}
#logo{font-size:16px;font-weight:800;letter-spacing:-.5px;}
#logo span{color:var(--red);}
#cloud-badge{font-size:9px;background:rgba(230,0,35,.15);color:var(--red);border:1px solid rgba(230,0,35,.3);padding:2px 7px;border-radius:10px;font-weight:700;letter-spacing:.06em;}
#clock{margin-left:auto;font-family:var(--mono);font-size:14px;font-weight:700;}
#tz{font-size:9px;color:var(--mu);}
#content{flex:1;overflow-y:auto;padding:0 0 72px;-webkit-overflow-scrolling:touch;}
#tabs{position:fixed;bottom:0;left:0;right:0;background:rgba(20,20,32,.97);backdrop-filter:blur(20px);border-top:1px solid var(--bd);display:flex;padding-bottom:env(safe-area-inset-bottom,12px);z-index:100;}
.tab{flex:1;display:flex;flex-direction:column;align-items:center;gap:3px;padding:9px 4px 7px;background:none;border:none;color:var(--fa);font-size:10px;font-weight:600;cursor:pointer;transition:color .2s;}
.tab.on{color:var(--red);}
.tab svg{width:21px;height:21px;}
.sc{display:none;padding:16px;}
.sc.on{display:block;}
/* Ring */
#ring-wrap{position:relative;width:150px;height:150px;margin:20px auto 0;}
#ring-svg{position:absolute;inset:0;width:100%;height:100%;}
.rt{fill:none;stroke:var(--bd);stroke-width:3;}
.rp{fill:none;stroke-width:3;stroke:var(--red);stroke-linecap:round;transform-origin:center;transform:rotate(-90deg);transition:stroke-dashoffset 1s linear,stroke .5s;}
#ring-c{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;}
#ring-icon{font-size:26px;line-height:1;}
#ring-lbl{font-size:9px;color:var(--mu);letter-spacing:.1em;text-transform:uppercase;}
#ring-cd{font-family:var(--mono);font-size:14px;font-weight:700;margin-top:2px;}
@keyframes pulse{0%{transform:scale(1);opacity:.5;}50%{transform:scale(1.1);opacity:.15;}100%{transform:scale(1);opacity:.5;}}
.rpulse{position:absolute;inset:8px;border-radius:50%;border:2px solid var(--red);animation:pulse 2s ease-in-out infinite;pointer-events:none;}
/* Cards */
.card{background:var(--s);border:1px solid var(--bd);border-radius:14px;padding:14px;margin-bottom:10px;}
.ctitle{font-size:10px;font-weight:700;color:var(--mu);letter-spacing:.1em;text-transform:uppercase;margin-bottom:10px;}
/* Stats */
.srow{display:flex;gap:8px;margin-bottom:10px;}
.scard{flex:1;background:var(--s);border:1px solid var(--bd);border-radius:12px;padding:12px;text-align:center;}
.sval{font-size:22px;font-weight:800;line-height:1;}
.slbl{font-size:10px;color:var(--mu);margin-top:3px;}
/* Toggle */
.trow{display:flex;align-items:center;justify-content:space-between;}
.tlbl{font-size:14px;font-weight:600;}
.tsub{font-size:11px;color:var(--mu);margin-top:2px;}
.tsw{width:48px;height:26px;border-radius:13px;background:var(--bd);position:relative;transition:background .25s;flex-shrink:0;cursor:pointer;}
.tsw.on{background:var(--red);}
.tsw::after{content:'';position:absolute;width:20px;height:20px;background:#fff;border-radius:10px;top:3px;left:3px;transition:left .25s;}
.tsw.on::after{left:25px;}
/* Slots */
.slrow{display:flex;align-items:center;justify-content:space-between;padding:9px 0;border-bottom:1px solid var(--bd);}
.slrow:last-child{border-bottom:none;}
.slday{font-size:11px;color:var(--mu);width:22px;}
.sltime{font-family:var(--mono);font-size:13px;font-weight:600;}
.slkw{font-size:11px;color:var(--mu);flex:1;padding:0 8px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;}
.slbadge{font-size:9px;font-weight:700;padding:2px 7px;border-radius:5px;}
.peak{background:rgba(230,0,35,.15);color:var(--red);}
.nxt{background:rgba(255,107,53,.15);color:var(--or);}
.soon{background:var(--s2);color:var(--fa);}
/* Run btn */
#runbtn{width:100%;padding:15px;border-radius:13px;font-size:14px;font-weight:700;letter-spacing:.02em;background:var(--red);color:#fff;border:none;cursor:pointer;transition:all .2s;margin-top:4px;}
#runbtn:disabled{background:var(--bd);color:var(--fa);cursor:not-allowed;}
#runbtn:active:not(:disabled){transform:scale(.98);}
/* Config status dots */
.cfg-row{display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px solid var(--bd);}
.cfg-row:last-child{border-bottom:none;}
.cfg-dot{width:8px;height:8px;border-radius:50%;flex-shrink:0;}
.dot-ok{background:var(--gr);}
.dot-no{background:#F87171;}
/* Log */
#logbox{background:var(--s2);border-radius:10px;padding:10px;height:170px;overflow-y:auto;font-family:var(--mono);font-size:11px;}
.ll{padding:2px 0;line-height:1.6;}
.lok{color:var(--gr);}.lerr{color:#F87171;}.lwarn{color:var(--yw);}.linfo{color:var(--mu);}
.lts{color:var(--fa);margin-right:5px;}
/* Results */
.res{background:var(--s2);border-radius:10px;padding:11px;margin-bottom:7px;border-left:3px solid var(--bd);}
.res.ok{border-left-color:var(--gr);}
.res.demo{border-left-color:var(--yw);}
.res.err{border-left-color:#F87171;}
.rbadge{font-size:9px;font-weight:700;padding:2px 7px;border-radius:4px;display:inline-block;margin-bottom:5px;}
.rtitle{font-size:12px;font-weight:600;line-height:1.3;}
.rdesc{font-size:11px;color:var(--mu);margin-top:3px;line-height:1.5;}
.rimg{width:60px;height:60px;object-fit:cover;border-radius:8px;float:right;margin-left:8px;}
.rlink{font-size:11px;color:var(--red);margin-top:5px;text-decoration:none;display:block;}
/* Week grid */
.wday{margin-bottom:14px;}
.wlbl{font-size:11px;font-weight:700;color:var(--mu);letter-spacing:.07em;text-transform:uppercase;margin-bottom:7px;display:flex;align-items:center;gap:7px;}
.today-b{font-size:8px;background:var(--red);color:#fff;padding:2px 5px;border-radius:3px;}
.chips{display:flex;flex-wrap:wrap;gap:5px;}
.chip{font-family:var(--mono);font-size:11px;font-weight:600;padding:4px 9px;border-radius:7px;border:1px solid var(--bd);background:var(--s2);color:var(--fa);}
.chip.now{background:var(--red);border-color:var(--red);color:#fff;}
.chip.tod{background:rgba(230,0,35,.12);border-color:rgba(230,0,35,.4);color:var(--red);}
.chip.done{background:rgba(34,197,94,.1);border-color:rgba(34,197,94,.3);color:var(--gr);}
.kwtag{font-size:10px;color:var(--mu);margin-top:5px;}
::-webkit-scrollbar{width:3px;}::-webkit-scrollbar-thumb{background:var(--bd);border-radius:3px;}
#peak-bar{display:none;background:var(--red);padding:8px;text-align:center;font-size:11px;font-weight:700;letter-spacing:.05em;}
#peak-bar.on{display:block;}
</style>
</head>
<body>
<div id="app">
  <div id="peak-bar">🔥 HORÁRIO DE PICO — Publicando automaticamente...</div>
  <div id="bar">
    <div id="logo">Pin<span>Agent</span></div>
    <div id="cloud-badge">☁️ CLOUD</div>
    <div style="margin-left:auto;text-align:right">
      <div id="clock">--:--</div>
      <div id="tz">BRT (UTC−3)</div>
    </div>
  </div>
  <div id="content">
    <!-- HOME -->
    <div id="sc-home" class="sc on">
      <div id="ring-wrap">
        <div class="rpulse" id="rpulse"></div>
        <svg id="ring-svg" viewBox="0 0 150 150">
          <circle class="rt" cx="75" cy="75" r="64"/>
          <circle class="rp" id="rprog" cx="75" cy="75" r="64" stroke-dasharray="402.1" stroke-dashoffset="402.1"/>
        </svg>
        <div id="ring-c">
          <div id="ring-icon">📌</div>
          <div id="ring-lbl">próximo slot</div>
          <div id="ring-cd">--:--:--</div>
        </div>
      </div>
      <div style="padding:16px 0 0">
        <div class="srow">
          <div class="scard"><div class="sval" id="st-today" style="color:var(--red)">0</div><div class="slbl">Hoje</div></div>
          <div class="scard"><div class="sval" id="st-total" style="color:var(--or)">0</div><div class="slbl">Total</div></div>
          <div class="scard"><div class="sval" style="color:var(--gr)">26</div><div class="slbl">Slots/sem</div></div>
        </div>
        <!-- Config status -->
        <div class="card" id="cfg-status">
          <div class="ctitle">Status das APIs</div>
          <div class="cfg-row"><span>Anthropic Claude</span><div class="cfg-dot dot-no" id="d-anthropic"></div></div>
          <div class="cfg-row"><span>AliExpress</span><div class="cfg-dot dot-no" id="d-ali"></div></div>
          <div class="cfg-row"><span>Pinterest</span><div class="cfg-dot dot-no" id="d-pin"></div></div>
          <div class="cfg-row"><span>Telegram</span><div class="cfg-dot dot-no" id="d-tg"></div></div>
          <div class="cfg-row"><span>Blogger</span><div class="cfg-dot dot-no" id="d-blogger"></div></div>
          <div class="cfg-row"><span>Buffer</span><div class="cfg-dot dot-no" id="d-buffer"></div></div>
        </div>
        <div class="card"><div class="ctitle">Próximos horários de pico</div><div id="slots-list"></div></div>
        <button id="runbtn" onclick="runNow()">📌 Publicar agora</button>
        <div class="card" style="margin-top:10px">
          <div class="ctitle">Keyword de hoje</div>
          <div id="kw-today" style="font-size:17px;font-weight:700;color:var(--or)">—</div>
          <div id="kw-day" style="font-size:11px;color:var(--mu);margin-top:3px">—</div>
        </div>
        <div class="card"><div class="ctitle">Log de atividade</div><div id="logbox"></div></div>
        <div id="res-section" style="display:none;margin-top:4px">
          <div class="ctitle">Último lote publicado</div>
          <div id="res-list"></div>
        </div>
      </div>
    </div>
    <!-- SCHEDULE -->
    <div id="sc-schedule" class="sc">
      <div class="ctitle" style="padding-top:4px">Grade Semanal — Horários de Pico BRT</div>
      <div id="week-grid"></div>
    </div>
    <!-- INFO -->
    <div id="sc-info" class="sc">
      <div class="card">
        <div class="ctitle">☁️ Como funciona</div>
        <div style="font-size:12px;color:var(--mu);line-height:1.8">
          <p>Este serviço roda 24/7 na nuvem (Render.com).</p>
          <br>
          <p><b style="color:var(--tx)">Pipeline automático:</b></p>
          <p>① AliExpress API → produtos do dia</p>
          <p>② Claude AI → título SEO + descrição + hashtags + texto Telegram</p>
          <p>③ Pinterest API → Pin com imagem do produto</p>
          <p>④ Telegram Bot → mensagem com foto para o canal</p>
          <br>
          <p><b style="color:var(--tx)">Horários:</b> baseados em dados de 2M+ posts do público brasileiro (BRT)</p>
          <br>
          <p><b style="color:var(--tx)">SEO de imagem:</b></p>
          <p>• Alt text detalhado para busca visual</p>
          <p>• Título com keyword principal + benefício</p>
          <p>• 8-10 hashtags relevantes em português</p>
          <br>
          <p><b style="color:var(--tx)">Para configurar:</b> adicione as variáveis de ambiente no Render.com dashboard</p>
        </div>
      </div>
      <div class="card">
        <div class="ctitle">Variáveis de Ambiente</div>
        <div style="font-family:var(--mono);font-size:11px;color:var(--mu);line-height:2">
          <div>ANTHROPIC_KEY <span style="color:var(--yw)">← console.anthropic.com</span></div>
          <div>ALI_KEY + ALI_SECRET <span style="color:var(--yw)">← portals.aliexpress.com</span></div>
          <div>ALI_TRACKING <span style="color:var(--tx)">= 529958</span></div>
          <div>PIN_TOKEN <span style="color:var(--yw)">← developers.pinterest.com</span></div>
          <div>PIN_BOARD_ID <span style="color:var(--yw)">← ID do seu board</span></div>
          <div>TG_TOKEN <span style="color:var(--yw)">← @BotFather</span></div>
          <div>TG_CHANNEL <span style="color:var(--tx)">= @Ofertassdiariasaliexpresss</span></div>
          <div>BUFFER_TOKEN <span style="color:var(--yw)">← Buffer Dashboard → API</span></div>
          <div>BUFFER_PROFILES <span style="color:var(--tx)">(opcional, channel IDs separados por vírgula)</span></div>
        </div>
      </div>
    </div>
  </div>
  <nav id="tabs">
    <button class="tab on" id="tab-home" onclick="showTab('home')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>Início
    </button>
    <button class="tab" id="tab-schedule" onclick="showTab('schedule')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>Agenda
    </button>
    <button class="tab" id="tab-info" onclick="showTab('info')">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>Info
    </button>
  </nav>
</div>
<script>
var PEAK = [
  {day:0,label:"Dom",slots:["09:00","12:00","20:00","21:00"]},
  {day:1,label:"Seg",slots:["12:00","15:00","20:00","21:00"]},
  {day:2,label:"Ter",slots:["09:00","13:00","20:00","21:00"]},
  {day:3,label:"Qua",slots:["10:00","14:00","19:00","21:00"]},
  {day:4,label:"Qui",slots:["10:00","12:00","19:00","20:00"]},
  {day:5,label:"Sex",slots:["20:00","21:00"]},
  {day:6,label:"Sáb",slots:["09:00","10:00","20:00","21:00"]},
];
var KW = ["fone bluetooth sem fio","smartwatch barato 2024","cabo usb tipo c carga rapida","case celular transparente","led strip rgb quarto","organizador cozinha gaveta","brinquedo educativo crianca"];
var DAYS = ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"];
var DAYSFULL = ["Domingo","Segunda","Terça","Quarta","Quinta","Sexta","Sábado"];
function getBRT(){var n=new Date();return new Date(n.getTime()-3*3600000+n.getTimezoneOffset()*60000);}
function hhmm(d){return ("0"+d.getHours()).slice(-2)+":"+("0"+d.getMinutes()).slice(-2);}
function fmtMs(ms){ms=Math.max(0,ms);var h=Math.floor(ms/3600000),m=Math.floor((ms%3600000)/60000),s=Math.floor((ms%60000)/1000);return ("0"+h).slice(-2)+":"+("0"+m).slice(-2)+":"+("0"+s).slice(-2);}
function getAllSlots(){
  var brt=getBRT(),r=[];
  PEAK.forEach(function(d){d.slots.forEach(function(t){
    var p=t.split(":"),dt=new Date(brt);
    dt.setHours(+p[0],+p[1],0,0);
    var diff=(d.day-brt.getDay()+7)%7;
    dt.setDate(dt.getDate()+diff);
    if(dt<=brt)dt.setDate(dt.getDate()+7);
    r.push({dt:dt,day:d.label,time:t,kw:KW[d.day],dayIdx:d.day});
  });});
  return r.sort(function(a,b){return a.dt-b.dt;});
}
function showTab(name){
  document.querySelectorAll(".sc").forEach(function(s){s.classList.remove("on");});
  document.querySelectorAll(".tab").forEach(function(b){b.classList.remove("on");});
  document.getElementById("sc-"+name).classList.add("on");
  document.getElementById("tab-"+name).classList.add("on");
  if(name==="schedule")renderWeek();
}
function addLog(msg,type){
  var box=document.getElementById("logbox");
  var brt=getBRT();
  var ts=hhmm(brt)+":"+("0"+brt.getSeconds()).slice(-2);
  var d=document.createElement("div");
  d.className="ll l"+(type||"info");
  d.innerHTML='<span class="lts">'+ts+'</span>'+msg;
  box.appendChild(d);
  box.scrollTop=box.scrollHeight;
}
function tick(){
  var brt=getBRT();
  var cur=hhmm(brt);
  document.getElementById("clock").textContent=cur;
  var dayIdx=brt.getDay();
  var isPeak=PEAK[dayIdx]&&PEAK[dayIdx].slots.indexOf(cur)>=0;
  document.getElementById("peak-bar").className=isPeak?"on":"";
  document.getElementById("kw-today").textContent=KW[dayIdx];
  document.getElementById("kw-day").textContent=DAYSFULL[dayIdx];
  var slots=getAllSlots();
  if(!slots.length)return;
  var next=slots[0];
  var ms=Math.max(0,next.dt.getTime()-brt.getTime());
  document.getElementById("ring-cd").textContent=fmtMs(ms);
  var circ=2*Math.PI*64;
  var prog=Math.min(1,1-ms/(3*3600000));
  var rp=document.getElementById("rprog");
  rp.style.strokeDashoffset=circ*(1-prog);
  rp.style.stroke=isPeak?"#22C55E":"#E60023";
  document.getElementById("rpulse").style.borderColor=isPeak?"#22C55E":"#E60023";
  document.getElementById("ring-icon").textContent=isPeak?"🔥":"📌";
  document.getElementById("ring-lbl").textContent=isPeak?"PICO ATIVO":"próximo slot";
  renderSlots(slots,cur);
}
function renderSlots(slots,cur){
  var list=document.getElementById("slots-list");
  list.innerHTML="";
  slots.slice(0,5).forEach(function(s,i){
    var brt=getBRT();
    var ms=Math.max(0,s.dt.getTime()-brt.getTime());
    var isNow=(i===0&&ms<60000);
    var row=document.createElement("div");
    row.className="slrow";
    var bc=isNow?"slbadge peak":i===0?"slbadge nxt":"slbadge soon";
    var bt=isNow?"🔥 AGORA":i===0?"PRÓXIMO":"em breve";
    row.innerHTML='<span class="slday">'+s.day+'</span><span class="sltime" style="color:'+(i===0?'var(--or)':'var(--tx)')+'">'+s.time+'</span><span class="slkw">'+s.kw+'</span><span class="'+bc+'">'+bt+'</span>';
    list.appendChild(row);
  });
}
function renderWeek(){
  var brt=getBRT();
  var curDay=brt.getDay();
  var cur=hhmm(brt);
  var g=document.getElementById("week-grid");
  g.innerHTML="";
  PEAK.forEach(function(d){
    var isT=d.day===curDay;
    var div=document.createElement("div");
    div.className="wday";
    var chips=d.slots.map(function(t){
      var isPast=isT&&t<cur;
      var isNow=isT&&t===cur;
      var cls=isNow?"chip now":isPast?"chip done":isT?"chip tod":"chip";
      return '<span class="'+cls+'">'+t+'</span>';
    }).join("");
    div.innerHTML='<div class="wlbl">'+DAYSFULL[d.day]+(isT?'<span class="today-b">HOJE</span>':'')+'</div><div class="chips">'+chips+'</div><div class="kwtag">📎 '+KW[d.day]+'</div>';
    g.appendChild(div);
  });
}
// Poll server status every 10s
function pollStatus(){
  fetch("/api/status").then(function(r){return r.json();}).then(function(data){
    // Update stats
    if(data.stats){
      document.getElementById("st-today").textContent=data.stats.today||0;
      document.getElementById("st-total").textContent=data.stats.total||0;
    }
    // Update config dots
    if(data.config){
      ["anthropic","aliexpress","pinterest","telegram"].forEach(function(k){
        var dot=document.getElementById("d-"+k.replace("aliexpress","ali").replace("pinterest","pin").replace("telegram","tg").replace("anthropic","anthropic"));
        if(dot){dot.className="cfg-dot "+(data.config[k]?"dot-ok":"dot-no");}
      });
    }
    // Update logs from server
    if(data.logs&&data.logs.length){
      var box=document.getElementById("logbox");
      var last=box.lastChild;
      var lastTs=last?last.querySelector(".lts"):null;
      var lastTsText=lastTs?lastTs.textContent:"";
      data.logs.forEach(function(l){
        if(l.ts!==lastTsText){
          var d=document.createElement("div");
          d.className="ll l"+(l.level||"info");
          d.innerHTML='<span class="lts">'+l.ts+'</span>'+l.msg;
          box.appendChild(d);
        }
      });
      box.scrollTop=box.scrollHeight;
    }
  }).catch(function(){});
}
// Run now
function runNow(){
  var btn=document.getElementById("runbtn");
  btn.disabled=true;
  btn.textContent="⏳ Publicando...";
  addLog("🚀 Publicação manual iniciada...");
  fetch("/api/run",{method:"POST"}).then(function(r){return r.json();}).then(function(data){
    btn.disabled=false;
    btn.textContent="📌 Publicar agora";
    if(data.results) renderResults(data.results);
  }).catch(function(e){
    btn.disabled=false;
    btn.textContent="📌 Publicar agora";
    addLog("❌ Erro: "+e.message,"err");
  });
}
function renderResults(results){
  var list=document.getElementById("res-list");
  list.innerHTML="";
  results.forEach(function(r){
    if(r.error){
      var d=document.createElement("div");
      d.className="res err";
      d.innerHTML='<span class="rbadge" style="background:#F87171;color:#000">❌ ERRO</span><div class="rtitle">'+r.error+'</div>';
      list.appendChild(d);
      return;
    }
    // Pinterest result
    var rPin=r.pinterest||{};
    var rTg=r.telegram||{};
    var content=r.content||{};
    var div=document.createElement("div");
    var ok=rPin.ok||rTg.ok;
    var sim=rPin.simulated||rTg.simulated;
    div.className="res "+(ok?"ok":sim?"demo":"err");
    var badges='';
    if(rPin.ok) badges+='<span class="rbadge" style="background:#22C55E;color:#000;margin-right:4px">📌 Pin #'+rPin.pin_id+'</span>';
    else if(rPin.simulated) badges+='<span class="rbadge" style="background:#F59E0B;color:#000;margin-right:4px">📌 Preview</span>';
    if(rTg.ok) badges+='<span class="rbadge" style="background:#22C55E;color:#000">📨 Msg #'+rTg.msg_id+'</span>';
    else if(rTg.simulated) badges+='<span class="rbadge" style="background:#F59E0B;color:#000">📨 Preview</span>';
    var imgHtml=content.image?'<img class="rimg" src="'+content.image+'" onerror="this.style.display=\\'none\\'">':'';
    div.innerHTML=badges+
      (imgHtml)+
      '<div class="rtitle">'+( content.title||r.product||"")+'</div>'+
      '<div class="rdesc">'+(content.description||"").slice(0,120)+'...</div>'+
      (rPin.url?'<a href="'+rPin.url+'" class="rlink" target="_blank">↗ Ver Pin no Pinterest</a>':'')+
      (rTg.url?'<a href="'+rTg.url+'" class="rlink" target="_blank">↗ Ver no Telegram</a>':'')+
      (r.blogger&&r.blogger.url?'<a href="'+r.blogger.url+'" class="rlink" target="_blank">↗ Ver no Blogger</a>':'')+
      (r.buffer&&r.buffer.ok?'<span style="font-size:11px;color:#22C55E;display:block;margin-top:4px">✅ Buffer: '+( r.buffer.profiles||1)+' perfil(s)</span>':'');
    list.appendChild(div);
  });
  document.getElementById("res-section").style.display="block";
}
// Init
setInterval(tick,1000);
tick();
setInterval(pollStatus,10000);
pollStatus();
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return HTML, 200, {"Content-Type": "text/html; charset=utf-8"}

@app.route("/ping")
def ping():
    return jsonify({"status":"ok","service":"PinAgent Cloud"})

@app.route("/api/run", methods=["POST"])
def api_run():
    results = run_pipeline(manual=True)
    return jsonify({"ok":True,"results":results})

@app.route("/api/status")
def api_status():
    brt = get_brt()
    day = (brt.weekday() + 1) % 7
    hhmm = brt.strftime("%H:%M")
    slots = []
    for d in range(7):
        idx = (day + d) % 7
        for t in PEAK.get(idx, []):
            slots.append({"day":DAYS[idx],"time":t,"keyword":KEYWORDS[idx]})
    return jsonify({
        "brt_time": hhmm,
        "brt_day": DAYS[day],
        "keyword_today": KEYWORDS[day],
        "is_peak": hhmm in PEAK.get(day, []),
        "next_slots": slots[:8],
        "stats": stats,
        "logs": logs[-30:],
        "config": {
            "anthropic": bool(ANTHROPIC_KEY),
            "aliexpress": bool(ALI_KEY and ALI_SECRET),
            "pinterest": bool(PIN_TOKEN and PIN_BOARD_ID),
            "telegram": bool(TG_TOKEN),
            "blogger": bool(BLOGGER_REFRESH or BLOGGER_TOKEN),
            "buffer": bool(BUFFER_TOKEN),
        }
    })

add_log("PinAgent Cloud started", "ok")
if BLOGGER_REFRESH: refresh_blogger_token()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
