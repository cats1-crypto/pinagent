"""
telegram_templates.py
=====================
Módulo de templates variados para o canal @Ofertassdiariasaliexpresss
Integra com o agent existente no Render.com (pinagent.onrender.com)

Uso:
    from telegram_templates import build_telegram_message
    msg = build_telegram_message(product, template_type="auto")
"""

import random
from datetime import datetime


# ───────────────────────────────────────────────
# EMOJIS POR CATEGORIA
# ───────────────────────────────────────────────
CATEGORY_EMOJIS = {
    "electronics":  ["📱", "💻", "🎧", "⌚", "📷", "🖥️"],
    "fashion":      ["👗", "👟", "👜", "💍", "🧢", "🕶️"],
    "home":         ["🏠", "🛋️", "🍳", "🧹", "💡", "🌿"],
    "beauty":       ["💄", "💅", "🧴", "✨", "🪞", "💋"],
    "sports":       ["💪", "🏋️", "🚴", "⚽", "🎯", "🏃"],
    "toys":         ["🧸", "🎮", "🎁", "🧩", "🪁", "🎠"],
    "tools":        ["🔧", "🛠️", "⚙️", "🔩", "🪛", "🔨"],
    "default":      ["🔥", "⚡", "💎", "🌟", "🎉", "✅"],
}

# ───────────────────────────────────────────────
# FRASES DE URGÊNCIA
# ───────────────────────────────────────────────
URGENCY_PHRASES = [
    "⏰ Oferta por tempo LIMITADO!",
    "🚨 Estoque acabando!",
    "⚡ Promoção relâmpago!",
    "🔥 Últimas unidades!",
    "⏳ Só hoje nesse preço!",
    "🎯 Aproveita antes que acabe!",
]

# ───────────────────────────────────────────────
# CTAs (Call to Action)
# ───────────────────────────────────────────────
CTAS = [
    "👉 Clica no link e garante o seu!",
    "🛒 Compra agora com frete grátis!",
    "💸 Pega antes que suba o preço!",
    "🔗 Link na bio + abaixo! 👇",
    "✅ Já adicionei no carrinho, e você?",
]

# ───────────────────────────────────────────────
# FOOTERS
# ───────────────────────────────────────────────
FOOTERS = [
    "📢 @Ofertassdiariasaliexpresss\n🔔 Ativa o sino para não perder!",
    "📢 Canal: @Ofertassdiariasaliexpresss\n💾 Salva esse post!",
    "🛍️ Mais achados → @Ofertassdiariasaliexpresss",
    "📢 @Ofertassdiariasaliexpresss\n👥 Compartilha com os amigos!",
    "🔔 Segue o canal → @Ofertassdiariasaliexpresss",
]


def get_emoji(category: str = "default") -> str:
    """Retorna emoji aleatório para a categoria."""
    emojis = CATEGORY_EMOJIS.get(category.lower(), CATEGORY_EMOJIS["default"])
    return random.choice(emojis)


def format_price_brl(price_usd: float, rate: float = 5.10) -> str:
    """Converte USD para BRL formatado."""
    brl = price_usd * rate
    return f"R$ {brl:.2f}".replace(".", ",")


# ───────────────────────────────────────────────
# TEMPLATES
# ───────────────────────────────────────────────

def template_shock_price(product: dict) -> str:
    """Template 1: Choque de preço — alto impacto emocional."""
    emoji = get_emoji(product.get("category", "default"))
    price_display = product.get("price_brl") or format_price_brl(float(product.get("price", 0)))
    original = product.get("original_price_brl", "")
    discount = product.get("discount", "")

    price_line = f"✅ Por apenas: {price_display}"
    if original:
        price_line = f"❌ De: {original}\n{price_line}"
    if discount:
        price_line += f" ({discount}% OFF)"

    return (
        f"😱 NÃO ACREDITO NESSE PREÇO!\n\n"
        f"{emoji} {product['title']}\n\n"
        f"{price_line}\n\n"
        f"⭐ {product.get('rating', '4.5')}/5 "
        f"({product.get('reviews', '100+')} avaliações)\n\n"
        f"{random.choice(URGENCY_PHRASES)}\n"
        f"{random.choice(CTAS)}\n"
        f"🔗 {product['affiliate_link']}\n\n"
        f"{random.choice(FOOTERS)}"
    )


def template_flash_sale(product: dict) -> str:
    """Template 2: Oferta relâmpago — senso de urgência máximo."""
    emoji = get_emoji(product.get("category", "default"))
    price_display = product.get("price_brl") or format_price_brl(float(product.get("price", 0)))

    return (
        f"⚡ OFERTA RELÂMPAGO!\n\n"
        f"{emoji} {product['title']}\n\n"
        f"💰 Preço: {price_display}\n"
        f"🚚 Frete GRÁTIS para o Brasil\n"
        f"⭐ Avaliação: {product.get('rating', '4.5')}/5\n\n"
        f"🔥 Essa oferta some em breve!\n\n"
        f"🛒 {product['affiliate_link']}\n\n"
        f"{random.choice(FOOTERS)}"
    )


def template_discovery(product: dict) -> str:
    """Template 3: Achado do dia — tom de descoberta."""
    emoji = get_emoji(product.get("category", "default"))
    price_display = product.get("price_brl") or format_price_brl(float(product.get("price", 0)))
    hour = datetime.now().hour
    period = "manhã ☀️" if hour < 12 else ("tarde 🌤️" if hour < 18 else "noite 🌙")

    return (
        f"🔍 ACHADO DA {period.upper()}\n\n"
        f"{emoji} {product['title']}\n\n"
        f"💸 Por: {price_display}\n"
        f"📦 Entrega para o Brasil\n"
        f"⭐ {product.get('rating', '4.5')}/5\n\n"
        f"💬 Me conta nos comentários se você compraria!\n\n"
        f"👉 {product['affiliate_link']}\n\n"
        f"{random.choice(FOOTERS)}"
    )


def template_comparison(product: dict) -> str:
    """Template 4: Comparação de valor — racional."""
    emoji = get_emoji(product.get("category", "default"))
    price_display = product.get("price_brl") or format_price_brl(float(product.get("price", 0)))

    return (
        f"💡 VALE A PENA COMPRAR?\n\n"
        f"{emoji} {product['title']}\n\n"
        f"✅ AliExpress: {price_display}\n"
        f"✅ Frete grátis incluso\n"
        f"✅ {product.get('reviews', '500+')} avaliações positivas\n"
        f"✅ Proteção de comprador AliExpress\n\n"
        f"🏆 Veredicto: VALE MUITO!\n\n"
        f"🔗 {product['affiliate_link']}\n\n"
        f"{random.choice(FOOTERS)}"
    )


def template_top5_weekly(products: list) -> str:
    """Template 5: Top 5 da semana — lista curada."""
    lines = ["🏆 TOP 5 ACHADOS DA SEMANA\n"]
    medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]

    for i, p in enumerate(products[:5]):
        price = p.get("price_brl") or format_price_brl(float(p.get("price", 0)))
        lines.append(f"{medals[i]} {p['title'][:40]}...\n   💰 {price} → {p['affiliate_link']}")

    lines.append(
        f"\n💾 Salva para não perder!\n"
        f"🔔 Ativa as notificações!\n\n"
        f"{random.choice(FOOTERS)}"
    )
    return "\n".join(lines)


def template_poll_style(product: dict) -> str:
    """Template 6: Estilo enquete — gera engajamento."""
    emoji = get_emoji(product.get("category", "default"))
    price_display = product.get("price_brl") or format_price_brl(float(product.get("price", 0)))

    return (
        f"📊 VOCÊ COMPRARIA ISSO?\n\n"
        f"{emoji} {product['title']}\n"
        f"💰 Por {price_display} no AliExpress\n\n"
        f"👍 SIM, tô comprando!\n"
        f"❤️ Não, mas é bom!\n"
        f"🤔 Preciso pensar...\n\n"
        f"Comenta aqui embaixo! 👇\n\n"
        f"🔗 {product['affiliate_link']}\n\n"
        f"{random.choice(FOOTERS)}"
    )


def template_night_deal(product: dict) -> str:
    """Template 7: Oferta da madrugada — exclusividade noturna."""
    emoji = get_emoji(product.get("category", "default"))
    price_display = product.get("price_brl") or format_price_brl(float(product.get("price", 0)))

    return (
        f"🌙 OFERTA DA MADRUGADA\n\n"
        f"Enquanto o Brasil dorme...\n"
        f"Eu acho os melhores preços! 😏\n\n"
        f"{emoji} {product['title']}\n\n"
        f"💸 Apenas: {price_display}\n"
        f"📦 Frete grátis\n\n"
        f"⚡ Pega antes de acabar!\n"
        f"🛒 {product['affiliate_link']}\n\n"
        f"{random.choice(FOOTERS)}"
    )


# ───────────────────────────────────────────────
# SELETOR AUTOMÁTICO
# ───────────────────────────────────────────────

SINGLE_TEMPLATES = [
    template_shock_price,
    template_flash_sale,
    template_discovery,
    template_comparison,
    template_poll_style,
    template_night_deal,
]

# Pesos: shock_price e flash_sale têm maior chance (mais virais)
TEMPLATE_WEIGHTS = [30, 25, 15, 10, 15, 5]


def build_telegram_message(
    product: dict,
    template_type: str = "auto"
) -> str:
    """
    Constrói mensagem Telegram para um produto.

    Args:
        product: dict com campos:
            - title (str): nome do produto
            - price (float): preço em USD
            - price_brl (str, opcional): preço já em BRL formatado
            - original_price_brl (str, opcional): preço original
            - discount (str/int, opcional): % de desconto
            - rating (str, opcional): avaliação ex: "4.8"
            - reviews (str, opcional): ex: "1.2k"
            - affiliate_link (str): link com tracking Admitad
            - category (str, opcional): "electronics", "fashion", etc.
        template_type: "auto" | "shock" | "flash" | "discovery" |
                       "comparison" | "poll" | "night"

    Returns:
        str: mensagem pronta para enviar no Telegram
    """
    mapping = {
        "shock":      template_shock_price,
        "flash":      template_flash_sale,
        "discovery":  template_discovery,
        "comparison": template_comparison,
        "poll":       template_poll_style,
        "night":      template_night_deal,
    }

    if template_type == "auto":
        # Escolha inteligente por hora do dia
        hour = datetime.now().hour
        if hour >= 22 or hour < 6:
            fn = template_night_deal
        elif hour in [12, 13]:
            fn = template_flash_sale   # pico do almoço → urgência
        else:
            fn = random.choices(SINGLE_TEMPLATES, weights=TEMPLATE_WEIGHTS, k=1)[0]
    else:
        fn = mapping.get(template_type, template_shock_price)

    return fn(product)


def build_top5_message(products: list) -> str:
    """Constrói mensagem Top 5 para lista de produtos."""
    return template_top5_weekly(products)


# ───────────────────────────────────────────────
# TESTE RÁPIDO
# ───────────────────────────────────────────────
if __name__ == "__main__":
    sample_product = {
        "title": "Fone de Ouvido Bluetooth 5.3 com Cancelamento de Ruído",
        "price": 12.99,
        "original_price_brl": "R$ 89,99",
        "discount": "65",
        "rating": "4.8",
        "reviews": "3.2k",
        "affiliate_link": "https://s.click.aliexpress.com/e/XXXXX?aff_id=529958",
        "category": "electronics",
    }

    print("=" * 55)
    print("TESTE DE TEMPLATES — @Ofertassdiariasaliexpresss")
    print("=" * 55)

    types = ["shock", "flash", "discovery", "comparison", "poll", "night"]
    for t in types:
        print(f"\n📌 TEMPLATE: {t.upper()}\n{'-'*40}")
        print(build_telegram_message(sample_product, template_type=t))
        print()

    # Teste Top 5
    products_5 = [sample_product] * 5
    print("\n📌 TEMPLATE: TOP 5\n" + "-" * 40)
    print(build_top5_message(products_5))
