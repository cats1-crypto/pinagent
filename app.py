"""
PinAgent Cloud — Flask server for Render.com
Pipeline: AliExpress API → Image Processing → Claude AI → Pinterest + Telegram
"""
import os, json, time, hmac, hashlib, urllib.parse, urllib.request, ssl, threading, schedule
from flask import Flask, request, jsonify, send_from_directory
from datetime import datetime

app = Flask(__name__, static_folder="static")
ctx = ssl.create_default_context()

# ── Config from environment variables ────────────────────────────────────────
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_KEY", "")
ALI_KEY        = os.environ.get("ALI_KEY", "")
ALI_SECRET     = os.environ.get("ALI_SECRET", "")
ALI_TRACKING   = os.environ.get("ALI_TRACKING", "529958")
PIN_TOKEN      = os.environ.get("PIN_TOKEN", "")
PIN_BOARD_ID   = os.environ.get("PIN_BOARD_ID", "")
TG_TOKEN       = os.environ.get("TG_TOKEN", "")
TG_CHANNEL     = os.environ.get("TG_CHANNEL", "@Ofertassdiariasaliexpresss")

# ── Peak schedule BRT ─────────────────────────────────────────────────────────
PEAK_SCHEDULE = {
    0: ["09:00","12:00","20:00","21:00"],  # Dom
    1: ["12:00","15:00","20:00","21:00"],  # Seg
    2: ["09:00","13:00","20:00","21:00"],  # Ter
    3: ["10:00","14:00","19:00","21:00"],  # Qua
    4: ["10:00","12:00","19:00","20:00"],  # Qui
    5: ["20:00","21:00"],                  # Sex
    6: ["09:00","10:00","20:00","21:00"],  # Sáb
}
KEYWORDS = [
    "fone bluetooth sem fio",    # Dom
    "smartwatch barato 2024",    # Seg
    "cabo usb tipo c carga rapida", # Ter
    "case celular transparente", # Qua
    "led strip rgb quarto",      # Qui
    "organizador cozinha gaveta",# Sex
    "brinquedo educativo crianca", # Sáb
]

logs = []
stats = {"today": 0, "total": 0, "last_run": None}

# ── MD5 for AliExpress ────────────────────────────────────────────────────────
def md5(s):
    return hashlib.md5(s.encode()).hexdigest().upper()

def ali_sign(params, secret):
    s = "".join(f"{k}{params[k]}" for k in sorted(params))
    return md5(f"{secret}{s}{secret}")

# ── HTTP helpers ──────────────────────────────────────────────────────────────
def http_post(url, body, headers=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
        return json.loads(r.read())

def http_get(url, headers=None):
    req = urllib.request.Request(url)
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)
    with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
        return r.read()

def add_log(msg, level="info"):
    brt = get_brt()
    ts = brt.strftime("%H:%M:%S")
    logs.append({"ts": ts, "msg": msg, "level": level})
    if len(logs) > 100:
        logs.pop(0)
    print(f"[{ts}] {msg}")

def get_brt():
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-3)))

# ── Step 1: Fetch AliExpress products ────────────────────────────────────────
def fetch_products(keyword, count=2):
    if not ALI_KEY or not ALI_SECRET:
        add_log("Sem credenciais AliExpress — usando demo", "warn")
        return mock_products(keyword, count)
    try:
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        params = {
            "app_key": ALI_KEY,
            "timestamp": ts,
            "sign_method": "md5",
            "method": "aliexpress.affiliate.product.query",
            "keywords": keyword,
            "target_currency": "BRL",
            "target_language": "PT",
            "tracking_id": ALI_TRACKING,
            "page_no": "1",
            "page_size": str(count),
            "country": "BR",
            "sort": "SALE_PRICE_ASC",
            "min_sale_price": "1000",   # min R$10 em centavos
            "max_sale_price": "20000",  # max R$200
        }
        params["sign"] = ali_sign(params, ALI_SECRET)
        url = "https://api-sg.aliexpress.com/sync?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, context=ctx, timeout=30) as r:
            data = json.loads(r.read())
        items = (data.get("aliexpress_affiliate_product_query_response", {})
                     .get("resp_result", {})
                     .get("result", {})
                     .get("products", {})
                     .get("product", []))
        if items:
            add_log(f"✅ {len(items)} produto(s) AliExpress", "ok")
            return items[:count]
    except Exception as e:
        add_log(f"AliExpress erro: {e} — usando demo", "warn")
    return mock_products(keyword, count)

def mock_products(kw, n):
    base = [
        {"product_id":"1005001","product_title":f"Fone Bluetooth 5.3 TWS {kw}","sale_price":"29.90","original_price":"79.90","evaluate_rate":"96%","commission_rate":"5.2%","product_main_image_url":"https://ae01.alicdn.com/kf/HTB1X.jpg","product_detail_url":f"https://www.aliexpress.com/item/1005001.html"},
        {"product_id":"1005002","product_title":f"Smartwatch {kw} Pro","sale_price":"45.50","original_price":"120.00","evaluate_rate":"94%","commission_rate":"4.8%","product_main_image_url":"https://ae01.alicdn.com/kf/HTB2X.jpg","product_detail_url":f"https://www.aliexpress.com/item/1005002.html"},
    ]
    return base[:n]

# ── Step 2: Get product image (with fallback) ─────────────────────────────────
def get_product_image_url(product):
    """
    Returns best image URL for Pinterest.
    Pinterest needs publicly accessible images.
    AliExpress CDN images work directly.
    """
    img = product.get("product_main_image_url", "")
    # Ensure HTTPS
    if img.startswith("http://"):
        img = "https://" + img[7:]
    # Fallback if empty
    if not img:
        img = "https://ae01.alicdn.com/kf/HTB1default.jpg"
    return img

# ── Step 3: Generate SEO content with Claude ──────────────────────────────────
def generate_content(product, keyword):
    aff_url_pin = f"https://www.aliexpress.com/item/{product['product_id']}.html?aff_fcid={ALI_TRACKING}&sk=pinterest&aff_platform=portals-tool"
    aff_url_tg  = f"https://www.aliexpress.com/item/{product['product_id']}.html?aff_fcid={ALI_TRACKING}&sk=telegram&aff_platform=portals-tool"

    orig  = float(product.get("original_price", 0) or 0)
    sale  = float(product.get("sale_price", 0) or 0)
    disc  = round((1 - sale/orig)*100) if orig > 0 else 0
    rate  = product.get("evaluate_rate", "95%")
    comm  = product.get("commission_rate", "4%")
    title = product.get("product_title", "")
    img   = get_product_image_url(product)

    prompt = f"""Você é especialista em marketing de afiliados para o mercado brasileiro.
Nicho: achadinhos AliExpress. Canal: @Ofertassdiariasaliexpresss e Pinterest achadinhos_virais_br.

PRODUTO:
- Nome: {title}
- Preço: R$ {sale} (era R$ {orig}, -{disc}%)
- Avaliação: {rate} dos compradores
- Comissão afiliado: {comm}
- Keyword do dia: {keyword}
- Link Pinterest: {aff_url_pin}
- Link Telegram: {aff_url_tg}

GERE conteúdo otimizado para máximo tráfego orgânico. Responda SOMENTE em JSON válido:
{{
  "pinterest_title": "título Pin SEO max 95 chars — inclua keyword principal + benefício + preço",
  "pinterest_description": "descrição Pin 450-500 chars — storytelling compra inteligente, benefícios específicos, urgência, CTA, 8-10 hashtags relevantes como #achadinhos #aliexpress #ofertasaliexpress #comprasonline #achados #brasil #fretegratis #desconto #promoção #diadeofertas",
  "pinterest_alt_text": "alt text descritivo para SEO de imagem max 500 chars — descreve o produto detalhadamente para acessibilidade e busca",
  "pinterest_keywords": ["keyword1","keyword2","keyword3","keyword4","keyword5"],
  "telegram_text": "mensagem Telegram HTML max 900 chars — emoji chamativo título em <b>negrito</b> preço destacado 3 características com emoji CTA urgente link",
  "seo_score_notes": "breve análise do potencial de tráfego"
}}"""

    try:
        resp = http_post(
            "https://api.anthropic.com/v1/messages",
            {
                "model": "claude-sonnet-4-6",
                "max_tokens": 1000,
                "messages": [{"role": "user", "content": prompt}]
            },
            {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"}
        )
        text = ""
        for block in resp.get("content", []):
            if block.get("type") == "text":
                text = block["text"]
        clean = text.replace("```json","").replace("```","").strip()
        content = json.loads(clean)
        content["aff_url_pin"] = aff_url_pin
        content["aff_url_tg"]  = aff_url_tg
        content["image_url"]   = img
        content["product"]     = product
        add_log(f"✅ Conteúdo gerado: {title[:40]}...", "ok")
        return content
    except Exception as e:
        add_log(f"Claude erro: {e}", "warn")
        return {
            "pinterest_title": f"{title[:80]} — R$ {sale} (-{disc}%)",
            "pinterest_description": f"🔥 Achado incrível! {title} por apenas R$ {sale}!\n\n✅ {rate} de aprovação\n💰 Economia de R$ {round(orig-sale,2)}\n\n#achadinhos #aliexpress #oferta #desconto #brasil #comprasonline",
            "pinterest_alt_text": f"Produto AliExpress: {title}. Preço: R$ {sale}. Avaliação: {rate}",
            "pinterest_keywords": ["achadinhos","aliexpress","oferta","desconto","brasil"],
            "telegram_text": f"🔥 <b>{title}</b>\n\n💰 R$ {sale} (-{disc}%)\n⭐ {rate} de aprovação\n\n<a href='{aff_url_tg}'>🛒 Comprar agora</a>",
            "aff_url_pin": aff_url_pin,
            "aff_url_tg":  aff_url_tg,
            "image_url":   img,
            "product":     product,
        }

# ── Step 4a: Publish Pinterest ─────────────────────────────────────────────────
def publish_pinterest(content):
    if not PIN_TOKEN or not PIN_BOARD_ID:
        return {"ok": False, "simulated": True, "ch": "pinterest"}
    try:
        resp = http_post(
            "https://api.pinterest.com/v5/pins",
            {
                "board_id": PIN_BOARD_ID,
                "title": content["pinterest_title"],
                "description": content["pinterest_description"],
                "alt_text": content["pinterest_alt_text"],
                "link": content["aff_url_pin"],
                "media_source": {
                    "source_type": "image_url",
                    "url": content["image_url"]
                }
            },
            {"Authorization": f"Bearer {PIN_TOKEN}"}
        )
        pin_id = resp.get("id", "")
        add_log(f"✅ Pinterest Pin #{pin_id}", "ok")
        return {"ok": True, "ch": "pinterest", "pin_id": pin_id,
                "url": f"https://pinterest.com/pin/{pin_id}"}
    except Exception as e:
        add_log(f"Pinterest erro: {e}", "err")
        return {"ok": False, "ch": "pinterest", "error": str(e)}

# ── Step 4b: Publish Telegram ──────────────────────────────────────────────────
def publish_telegram(content):
    if not TG_TOKEN:
        return {"ok": False, "simulated": True, "ch": "telegram"}
    try:
        # Send photo + caption for better engagement
        img_url = content["image_url"]
        tg_text = content["telegram_text"]

        # Try sendPhoto first, fallback to sendMessage
        try:
            resp = http_post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                {
                    "chat_id": TG_CHANNEL,
                    "photo": img_url,
                    "caption": tg_text,
                    "parse_mode": "HTML"
                }
            )
        except Exception:
            # Fallback: send text only if image fails
            resp = http_post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                {
                    "chat_id": TG_CHANNEL,
                    "text": tg_text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False
                }
            )

        if resp.get("ok"):
            msg_id = resp.get("result", {}).get("message_id", "")
            add_log(f"✅ Telegram msg #{msg_id}", "ok")
            return {"ok": True, "ch": "telegram", "msg_id": msg_id,
                    "url": f"https://t.me/{TG_CHANNEL.replace('@','')}"}
        else:
            raise Exception(resp.get("description", "Unknown error"))
    except Exception as e:
        add_log(f"Telegram erro: {e}", "err")
        return {"ok": False, "ch": "telegram", "error": str(e)}

# ── Main pipeline ──────────────────────────────────────────────────────────────
def run_pipeline(manual=False):
    brt = get_brt()
    keyword = KEYWORDS[brt.weekday() % 7]  # weekday 0=Mon, adjust to our 0=Sun
    # Python weekday: 0=Mon...6=Sun, our array: 0=Sun...6=Sat
    day_idx = (brt.weekday() + 1) % 7
    keyword = KEYWORDS[day_idx]

    trigger = "MANUAL" if manual else "AUTO"
    add_log(f"🚀 Pipeline {trigger} — keyword: '{keyword}'", "ok")

    products = fetch_products(keyword, count=2)
    results = []

    for product in products:
        try:
            content = generate_content(product, keyword)
            r_pin = publish_pinterest(content)
            r_tg  = publish_telegram(content)
            results.append({"product": product.get("product_title","")[:50],
                            "pinterest": r_pin, "telegram": r_tg,
                            "content": {
                                "title": content["pinterest_title"],
                                "description": content["pinterest_description"][:200],
                                "image": content["image_url"],
                            }})
            if r_pin.get("ok"): stats["today"] += 1; stats["total"] += 1
        except Exception as e:
            add_log(f"Erro produto: {e}", "err")
            results.append({"error": str(e)})

    stats["last_run"] = brt.strftime("%H:%M:%S BRT")
    ok_count = sum(1 for r in results if r.get("pinterest",{}).get("ok") or r.get("telegram",{}).get("ok"))
    add_log(f"🎉 Concluído — {ok_count}/{len(results)*2} publicações OK", "ok")
    return results

# ── Scheduler (runs in background thread) ────────────────────────────────────
def scheduler_loop():
    """Checks every minute if it's a peak slot and runs pipeline."""
    while True:
        try:
            brt = get_brt()
            hhmm = brt.strftime("%H:%M")
            day  = (brt.weekday() + 1) % 7  # convert to Sun=0
            if hhmm in PEAK_SCHEDULE.get(day, []):
                add_log(f"⏰ Horário de pico: {hhmm} BRT", "ok")
                run_pipeline(manual=False)
                time.sleep(61)  # avoid double-trigger in same minute
        except Exception as e:
            add_log(f"Scheduler erro: {e}", "err")
        time.sleep(30)

# Start scheduler in background
scheduler_thread = threading.Thread(target=scheduler_loop, daemon=True)
scheduler_thread.start()

# ── Flask routes ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/run", methods=["POST"])
def api_run():
    results = run_pipeline(manual=True)
    return jsonify({"ok": True, "results": results})

@app.route("/api/status")
def api_status():
    brt = get_brt()
    day = (brt.weekday() + 1) % 7
    hhmm = brt.strftime("%H:%M")
    peak_slots = PEAK_SCHEDULE.get(day, [])
    next_slots = []
    for d in range(7):
        idx = (day + d) % 7
        for slot in PEAK_SCHEDULE.get(idx, []):
            next_slots.append({
                "day": ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"][idx],
                "time": slot,
                "keyword": KEYWORDS[idx]
            })
    return jsonify({
        "brt_time": hhmm,
        "brt_day": ["Dom","Seg","Ter","Qua","Qui","Sex","Sáb"][day],
        "keyword_today": KEYWORDS[day],
        "is_peak": hhmm in peak_slots,
        "next_slots": next_slots[:8],
        "stats": stats,
        "logs": logs[-30:],
        "config": {
            "anthropic": bool(ANTHROPIC_KEY),
            "aliexpress": bool(ALI_KEY and ALI_SECRET),
            "pinterest": bool(PIN_TOKEN and PIN_BOARD_ID),
            "telegram": bool(TG_TOKEN),
        }
    })

@app.route("/api/logs")
def api_logs():
    return jsonify(logs[-50:])

@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "service": "PinAgent Cloud"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    add_log(f"PinAgent Cloud started on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
