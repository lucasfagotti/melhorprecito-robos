"""Robô do canal de ofertas no Telegram (API oficial de bots).

Uso: python telegram_bot.py teste           confere token, canal e se o bot é administrador
     python telegram_bot.py postar          publica as ofertas do plano de hoje que já passaram do horário (máx. 2 por vez)
     python telegram_bot.py agora <dia> <n> publica uma oferta específica na hora
     python telegram_bot.py membros         grava o número de membros em saida/telegram_stats.json
Chaves no .env: TELEGRAM_BOT_TOKEN e TELEGRAM_CANAL (ex.: @achadinhos_melhorpreco)
"""
import html
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import requests

from shopee_api import carregar_env

AQUI = Path(__file__).parent
DIAS = AQUI / "saida" / "dias"
STATS = AQUI / "saida" / "telegram_stats.json"
POSTADOS = AQUI / "saida" / "telegram_postados.json"  # dedup fora do plano.json (a fábrica reescreve o plano)
POR_VEZ = 2  # se o PC ficou desligado, não despeja tudo de uma vez


def config():
    carregar_env()
    token, canal = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CANAL")
    if not token or not canal:
        raise SystemExit("Faltam TELEGRAM_BOT_TOKEN e TELEGRAM_CANAL no .env")
    return token, canal


def tg(metodo, **dados):
    token, _ = config()
    r = requests.post(f"https://api.telegram.org/bot{token}/{metodo}", json=dados, timeout=60).json()
    if not r.get("ok"):
        raise RuntimeError(f"{metodo}: {r.get('description')}")
    return r["result"]


def botoes(link):
    """Botão de compra + botão que abre o "compartilhar" do Telegram com o convite do canal (crescimento orgânico)."""
    _, canal = config()
    convite = quote("Canal de achadinhos da Shopee com preço bom todo dia 👇")
    return {"inline_keyboard": [[{"text": "🛒 Ver na Shopee", "url": link}],
                                [{"text": "📢 Compartilhar o canal",
                                  "url": f"https://t.me/share/url?url=https://t.me/{canal.lstrip('@')}&text={convite}"}]]}


def rodape(link, chamada="🛒 Compre aqui"):
    """Link escrito no texto (vai junto quando copiam a oferta pro WhatsApp) + marca + aviso de publicidade."""
    _, canal = config()
    return (f"\n\n{chamada}:\n{link}\n\n🛍️ Melhor Precito\nTelegram: t.me/{canal.lstrip('@')}\n#Anúncio")


def texto(item):
    preco = f"{item['preco']:.2f}".replace(".", ",")
    desconto = f"  🔥 <b>{item['desconto']}% OFF</b>" if item.get("desconto", 0) >= 10 else ""
    import cupons
    # cupom compatível com a categoria do produto vai junto; senão, só o lembrete genérico
    extra = "\n".join(cupons.linha_cupom(c) for c in cupons.para_produto(item.get("categoria", ""))) or "🎟️ Confira também os cupons da Shopee no carrinho"
    return (f"<b>{html.escape(item['curto'] or item['produto'][:60])}</b>\n\n{html.escape(item['telegram_texto'])}\n\n"
            f"💰 <b>R$ {preco}</b>{desconto}\n{extra}{rodape(item['link_telegram'])}")


def foto_card(p, legenda, link):
    """Manda o card de oferta (cards.py); se o card falhar, vai a foto do anúncio para a oferta não deixar de sair."""
    token, canal = config()
    try:
        import cards
        caminho = cards.card_cache(p)
        with open(caminho, "rb") as fh:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", timeout=120, files={"photo": fh},
                              data={"chat_id": canal, "caption": legenda, "parse_mode": "HTML",
                                    "reply_markup": json.dumps(botoes(link))}).json()
        if r.get("ok"):
            return r["result"]
    except Exception as erro:
        print(f"card falhou, vai a foto: {erro}", flush=True)
    return tg("sendPhoto", chat_id=canal, photo=p["imageUrl"], caption=legenda, parse_mode="HTML", reply_markup=botoes(link))


def publicar(item):
    import cards
    msg = foto_card(cards.de_item(item), texto(item), item["link_telegram"])
    item["telegram_postado"] = True
    item["telegram_msg"] = msg["message_id"]
    item["telegram_hora"] = datetime.now().strftime("%H:%M")


def salvar_plano(arq, plano):
    arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")


def _postados():
    return json.loads(POSTADOS.read_text(encoding="utf-8")) if POSTADOS.exists() else {}


def postar():
    arq = DIAS / date.today().isoformat() / "plano.json"
    if not arq.exists():
        print("sem plano hoje")
        return
    plano = json.loads(arq.read_text(encoding="utf-8"))
    agora = datetime.now().strftime("%H:%M")
    postados = _postados()  # dedup fora do plano.json: a fábrica reescreve o plano e zerava o telegram_postado
    feitos = 0
    for item in plano["itens"]:
        if str(item["itemId"]) not in postados and item["horario"] <= agora and feitos < POR_VEZ:
            publicar(item)
            postados[str(item["itemId"])] = datetime.now().strftime("%d/%m %H:%M")
            POSTADOS.write_text(json.dumps(postados, ensure_ascii=False, indent=1), encoding="utf-8")
            feitos += 1  # o plano.json é do PC (fábrica/widget): a nuvem só escreve em telegram_postados
            print("postado:", item["curto"])
    membros()


def agora(dia, n):
    arq = DIAS / dia / "plano.json"
    plano = json.loads(arq.read_text(encoding="utf-8"))
    item = next(i for i in plano["itens"] if i["n"] == int(n))
    publicar(item)
    salvar_plano(arq, plano)
    postados = _postados()
    postados[str(item["itemId"])] = datetime.now().strftime("%d/%m %H:%M")
    POSTADOS.write_text(json.dumps(postados, ensure_ascii=False, indent=1), encoding="utf-8")
    print("postado:", item["curto"])


def membros():
    _, canal = config()
    total = tg("getChatMemberCount", chat_id=canal)
    stats = json.loads(STATS.read_text(encoding="utf-8")) if STATS.exists() else {}
    stats[date.today().isoformat()] = total
    STATS.write_text(json.dumps(stats, indent=1), encoding="utf-8")
    return total


def teste():
    eu = tg("getMe")
    _, canal = config()
    chat = tg("getChat", chat_id=canal)
    papel = tg("getChatMember", chat_id=canal, user_id=eu["id"])
    pode = papel.get("status") == "creator" or (papel.get("status") == "administrator" and papel.get("can_post_messages"))
    print(f"bot @{eu['username']} | canal: {chat.get('title')} | situação do bot: {papel.get('status')} | "
          f"pode postar: {'sim' if pode else 'NÃO'}")
    if pode:
        print(f"membros: {membros()}")


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "postar"
    {"teste": teste, "postar": postar, "membros": membros}.get(acao, lambda: agora(*sys.argv[2:4]))()
