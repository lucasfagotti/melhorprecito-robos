"""Card de oferta no estilo dos canais grandes (vertical 1080x1920): fundo temático com padrão, aviso de oferta,
cartão branco com foto + 4 selos de destaque, nome, "De" riscado, "Por" grande e cupom.
Usado nos Stories do Instagram, nas ofertas do Telegram e no status do WhatsApp.

Uso: python cards.py <itemId>     gera um card de teste em saida/cards/
Tema muda sozinho: Black Friday (20 a 30/11), Natal (01/12 a 25/12) e a cara do Melhor Precito no resto do ano.
"""
import io
import json
import random
import sys
import textwrap
from datetime import date
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

AQUI = Path(__file__).parent
PASTA = AQUI / "saida" / "cards"
CACHE = PASTA / "destaques.json"
LOGO = AQUI / "saida" / "canal" / "logo.jpg"
W, H = 1080, 1920

TEMAS = {
    "marca": {"fundo": (238, 77, 45), "fundo2": (255, 122, 89), "escuro": (31, 41, 55), "destaque": (238, 77, 45),
              "claro": (255, 237, 230), "figuras": ["🛍️", "🎁", "💸", "⭐"], "logo": True},
    "black": {"fundo": (17, 17, 17), "fundo2": (45, 45, 45), "escuro": (17, 17, 17), "destaque": (220, 38, 38),
              "claro": (254, 226, 226), "figuras": ["🖤", "🔥", "💸", "🛒"], "logo": True},
    "natal": {"fundo": (153, 27, 27), "fundo2": (185, 28, 28), "escuro": (20, 83, 45), "destaque": (185, 28, 28),
              "claro": (254, 226, 226), "figuras": ["🎄", "🎁", "⭐", "🎅"], "logo": True},
}


def tema(hoje=None):
    hoje = hoje or date.today()
    if hoje.month == 11 and 20 <= hoje.day <= 30:
        return TEMAS["black"]
    if hoje.month == 12 and hoje.day <= 25:
        return TEMAS["natal"]
    return TEMAS["marca"]


FONTES = AQUI / "fontes"  # Montserrat (licença OFL, em fontes/) e emojis Twemoji: iguais no PC e na nuvem (Linux)
EMOJI_URL = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@15.1.0/assets/72x72/{}.png"


def F(t, peso="black"):
    arq = {"black": "Montserrat-Black.ttf", "bold": "Montserrat-Bold.ttf", "normal": "Montserrat-SemiBold.ttf"}[peso]
    return ImageFont.truetype(str(FONTES / arq), t)


def emoji(im, xy, ch, tam):
    """Cola o emoji (imagem Twemoji, guardada em fontes/emoji/) no lugar do texto."""
    codigo = "-".join(f"{ord(c):x}" for c in ch if ord(c) != 0xFE0F)
    arq = FONTES / "emoji" / f"{codigo}.png"
    if not arq.exists():
        r = requests.get(EMOJI_URL.format(codigo), timeout=30)
        if r.status_code != 200:
            return
        arq.parent.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(r.content)
    img = Image.open(arq).convert("RGBA").resize((tam, tam), Image.LANCZOS)
    im.paste(img, (int(xy[0]), int(xy[1])), img)


def quebrar(d, texto, fonte, largura, max_linhas):
    """Quebra o texto pela largura real em pixels (Montserrat é larga: contar letras não serve)."""
    linhas, atual = [], ""
    for palavra in texto.split():
        teste = f"{atual} {palavra}".strip()
        if d.textlength(teste, font=fonte) <= largura:
            atual = teste
        else:
            linhas.append(atual)
            atual = palavra
    linhas.append(atual)
    linhas = [l for l in linhas if l]
    if len(linhas) > max_linhas:
        linhas = linhas[:max_linhas]
        while d.textlength(linhas[-1] + "…", font=fonte) > largura and " " in linhas[-1]:
            linhas[-1] = linhas[-1].rsplit(" ", 1)[0]
        linhas[-1] += "…"
    return linhas


def destaques(p):
    """4 selos (emoji, título curto, texto curto) tirados SÓ do nome do produto; guardados para não pedir de novo."""
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    chave = str(p["itemId"])
    if chave not in cache:
        try:
            sys.path.insert(0, str(Path.home() / "produtos-digitais" / "deepseek"))
            from ds import chat
            r = chat(f'Produto: {p["productName"]}\nDevolva JSON {{"selos": [4 itens {{"emoji": "1 emoji", "titulo": "até 3 palavras", '
                     f'"texto": "até 6 palavras"}}]}} com características REAIS que dá para tirar do nome (tamanho, material, '
                     f'quantidade, uso, cor). Nunca invente. Sem nome de marca de terceiros.',
                     sistema="Você resume produtos de e-commerce em selos curtos, em português do Brasil.", json_saida=True, temperatura=0.3)
            cache[chave] = r["selos"][:4]
        except Exception:
            cache[chave] = []
        PASTA.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
    selos = cache[chave]
    padrao = [{"emoji": "⭐", "titulo": "Bem avaliado", "texto": f"Nota {p.get('ratingStar', '')} das compradoras"},
              {"emoji": "💸", "titulo": "Preço bom", "texto": "Conferido hoje"},
              {"emoji": "🛒", "titulo": "Compra fácil", "texto": "Toque no link e pronto"},
              {"emoji": "🚚", "titulo": "Entrega", "texto": "Para todo o Brasil"}]
    return (selos + padrao)[:4]


def _texto_central(d, y, texto, fonte, cor):
    w = d.textlength(texto, font=fonte)
    d.text(((W - w) / 2, y), texto, font=fonte, fill=cor)


def _fundo(t):
    im = Image.new("RGB", (W, H), t["fundo"])
    d = ImageDraw.Draw(im)
    for y in range(H):  # degradê vertical
        k = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * k) for a, b in zip(t["fundo"], t["fundo2"])))
    # padrão de figuras nas bordas (fora do cartão), como os canais grandes fazem com mascote
    rnd = random.Random(7)
    logo = Image.open(LOGO).resize((110, 110)) if t["logo"] and LOGO.exists() else None
    mascara = Image.new("L", (110, 110), 0)
    ImageDraw.Draw(mascara).ellipse([0, 0, 110, 110], fill=255)
    # só nas laterais e no topo: embaixo fica a marca
    pontos = [(x, y) for y in range(40, H - 300, 190) for x in (20, W - 120)] + [(x, 60) for x in range(160, W - 160, 230)]
    for k, (x, y) in enumerate(pontos):
        x += rnd.randint(-10, 10)
        if logo and k % 3 == 0:
            im.paste(logo, (x, y), mascara)
        else:
            emoji(im, (x, y), rnd.choice(t["figuras"]), 84)
    return im


def card(p, destino, cupom=None):
    """p: produto do garimpo (productName, price, priceDiscountRate, imageUrl, itemId, ratingStar). Devolve o caminho."""
    t = tema()
    im = _fundo(t)
    d = ImageDraw.Draw(im)
    # aviso do topo
    aviso = "*Essa oferta pode encerrar em qualquer momento."
    w = d.textlength(aviso, font=F(26, "bold"))
    d.rounded_rectangle([(W - w) / 2 - 24, 200, (W + w) / 2 + 24, 258], radius=20, fill=(255, 241, 236))
    d.text(((W - w) / 2, 213), aviso, font=F(26, "bold"), fill=t["escuro"])
    # cartão branco do tamanho do conteúdo (calculado antes de desenhar)
    import telegram_fila
    nome = telegram_fila.nome_curto(p["productName"])
    linhas_nome = quebrar(d, nome, F(48, "black"), W - 220, 3)
    desc = int(p.get("priceDiscountRate") or 0)
    fim = 910 + 60 * len(linhas_nome) + 18 + (80 if desc >= 5 else 0) + 195 + (130 if cupom or desc >= 10 else 0) + 20
    fim = max(fim, 1300)
    d.rounded_rectangle([70, 290, W - 70, fim], radius=44, fill="white")
    foto = ImageOps.exif_transpose(Image.open(io.BytesIO(requests.get(p["imageUrl"], timeout=60).content))).convert("RGB")
    foto = ImageOps.contain(foto, (520, 560))
    im.paste(foto, (100 + (520 - foto.width) // 2, 320 + (560 - foto.height) // 2))
    # 4 selos à direita
    for k, s in enumerate(destaques(p)):
        y = 320 + k * 142
        d.rounded_rectangle([640, y, W - 100, y + 128], radius=22, fill=t["escuro"])
        emoji(im, (654, y + 34), s.get("emoji", "⭐")[:2], 60)
        titulo, tam = str(s.get("titulo", "")), 28
        while d.textlength(titulo, font=F(tam, "black")) > W - 100 - 746 and tam > 20:  # diminui até caber no selo
            tam -= 2
        d.text((736, y + 16), titulo, font=F(tam, "black"), fill="white")
        for j, linha in enumerate(quebrar(d, str(s.get("texto", "")), F(21, "normal"), W - 100 - 746, 2)):
            d.text((736, y + 56 + j * 28), linha, font=F(21, "normal"), fill=(226, 232, 240))
    # nome do produto
    y = 910
    for linha in linhas_nome:
        d.text((110, y), linha, font=F(48, "black"), fill=t["escuro"])
        y += 60
    # De / Por
    preco = float(p["price"])
    brl = lambda v: "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    y += 18
    if desc >= 5:
        de = f"De: {brl(preco / (1 - desc / 100))}"
        emoji(im, (110, y + 4), "❌", 48)
        d.text((175, y), de, font=F(42, "bold"), fill=(120, 120, 120))
        largura = d.textlength(de, font=F(42, "bold"))
        d.line([(175, y + 28), (175 + largura, y + 28)], fill=(120, 120, 120), width=5)
        y += 80
    d.rounded_rectangle([100, y, W - 100, y + 170], radius=30, fill=t["claro"])
    emoji(im, (124, y + 35), "💰", 100)
    por, tam = f"Por: {brl(preco)}", 84
    while d.textlength(por, font=F(tam, "black")) > W - 130 - 250 and tam > 40:  # preço alto: diminui até caber
        tam -= 4
    d.text((250, y + 85 - tam * 0.62), por, font=F(tam, "black"), fill=t["destaque"])
    y += 195
    # cupom ou desconto
    if cupom:
        d.rounded_rectangle([100, y, W - 100, y + 110], radius=26, fill=(253, 224, 71))
        emoji(im, (124, y + 22), "🎟️", 66)
        d.text((210, y + 30), f"Use o cupom: {cupom}", font=F(42, "black"), fill=t["escuro"])
    elif desc >= 10:
        d.rounded_rectangle([100, y, W - 100, y + 110], radius=26, fill=(253, 224, 71))
        emoji(im, (124, y + 22), "🔥", 66)
        d.text((210, y + 28), f"{desc}% OFF hoje", font=F(48, "black"), fill=t["escuro"])
    # marca logo abaixo do cartão
    _texto_central(d, fim + 40, "Melhor Precito", F(50, "black"), "white")
    _texto_central(d, fim + 108, "t.me/melhorprecito  •  @melhor_precito", F(30, "bold"), (255, 237, 230))
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    im.save(destino, quality=92)
    return destino


def de_item(item):
    """Item do plano do dia -> formato do garimpo (para fazer o card dos 10 produtos com vídeo)."""
    return {"itemId": item["itemId"], "productName": item["produto"], "price": item["preco"],
            "priceDiscountRate": item.get("desconto", 0), "imageUrl": item["imagem_url"], "ratingStar": item.get("nota", "")}


def cupom_ativo():
    import cupons
    ativos = cupons.ativos()
    return ativos[0]["codigo"] if ativos else None


def card_cache(p, nome=None):
    """Mesmo produto no mesmo dia = mesmo card (não refaz a imagem)."""
    destino = PASTA / date.today().isoformat() / f"{nome or p['itemId']}.jpg"
    return destino if destino.exists() else card(p, destino, cupom_ativo())


if __name__ == "__main__":
    dados = json.loads((AQUI / "saida" / "garimpo.json").read_text(encoding="utf-8"))["produtos"]
    p = next((x for x in dados if str(x["itemId"]) == (sys.argv[1] if len(sys.argv) > 1 else "")), dados[0])
    print(card(p, PASTA / f"teste-{p['itemId']}.jpg"))
