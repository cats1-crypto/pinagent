import os, json, hashlib, urllib.parse, urllib.request, ssl, threading, time
from flask import Flask, jsonify, send_from_directory, request
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
    s = "".join(f"{k}{params[k]}" for k in sorted(params))
    return hashlib.md5(f"{secret}{s}{secret}".encode()).hexdigest().upper()

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
        ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        params = {
            "app_key": ALI_KEY, "timestamp": ts, "sign_method": "md5",
            "method": "aliexpress.affiliate.product.query",
            "keywords": keyword, "target_currency": "BRL",
            "target_language": "PT", "tracking_id": ALI_TRACKING,
            "page_no": "1", "page_size": str(n), "country": "BR",
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
    aff_pin = f"https://www.aliexpress.com/item/{pid}.html?aff_fcid={ALI_TRACKING}&sk=pinterest"
    aff_tg  = f"https://www.aliexpress.com/item/{pid}.html?aff_fcid={ALI_TRACKING}&sk=telegram"

    if not ANTHROPIC_KEY:
        return {
            "pinterest_title": f"{title[:80]} — R$ {sale} (-{disc}%)",
            "pinterest_description": f"Achado incrível! {title} por R$ {sale}\n#achadinhos #aliexpress #oferta #desconto #brasil",
            "pinterest_alt_text": f"Produto AliExpress: {title}. Preço R$ {sale}",
            "telegram_text": f"🔥 <b>{title}</b>\n\n💰 R$ {sale} (-{disc}%)\n⭐ {rate}\n\n<a href='{aff_tg}'>Comprar</a>",
            "aff_url_pin": aff_pin, "aff_url_tg": aff_tg, "image_url": img, "product": product,
        }

    prompt = f"""Copywriter afiliados Brasil — AliExpress achadinhos.
Produto: {title}
Preco: R$ {sale} (era R$ {orig}, -{disc}%)
Avaliacao: {rate} | Keyword: {keyword}
Link Pinterest: {aff_pin} | Link Telegram: {aff_tg}

JSON SOMENTE:
{{"pinterest_title":"titulo Pin SEO max 95 chars keyword+beneficio+preco","pinterest_description":"descricao Pin 450 chars PT emojis beneficios urgencia CTA 8 hashtags #achadinhos #aliexpress #oferta #desconto #brasil #comprasonline #fretegratis #promocao","pinterest_alt_text":"alt text SEO descritivo max 300 chars","telegram_text":"mensagem HTML max 800 chars emoji <b>titulo</b> preco desconto 3 beneficios CTA link"}}"""

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
        add_log(f"Claude OK: {title[:35]}...", "ok")
        return content
    except Exception as e:
        add_log(f"Claude erro: {e}", "warn")
        return {
            "pinterest_title": f"{title[:80]} — R$ {sale} (-{disc}%)",
            "pinterest_description": f"Achado! {title} por R$ {sale}\n#achadinhos #aliexpress #oferta #brasil",
            "pinterest_alt_text": f"Produto AliExpress: {title}",
            "telegram_text": f"🔥 <b>{title}</b>\n\n💰 R$ {sale} (-{disc}%)\n⭐ {rate}\n\n<a href='{aff_tg}'>Comprar</a>",
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
        try:
            resp = http_post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                {"chat_id":TG_CHANNEL,"photo":content["image_url"],
                 "caption":content["telegram_text"],"parse_mode":"HTML"}
            )
        except Exception:
            resp = http_post(
                f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                {"chat_id":TG_CHANNEL,"text":content["telegram_text"],
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
        if r_pin.get("ok"): stats["today"] += 1; stats["total"] += 1
        results.append({
            "product": p.get("product_title","")[:50],
            "pinterest": r_pin, "telegram": r_tg,
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

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

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
        }
    })

add_log("PinAgent Cloud started", "ok")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
