"""Cupons: vigia o blog oficial da Shopee (feed RSS público) e guarda cupons manuais; o widget aprova e o bot posta.

Uso: python cupons.py vigiar                       lê o feed e guarda cupons novos como "pendente"
     python cupons.py add CODIGO "regra" [AAAA-MM-DD]
     python cupons.py postar <id>                   posta no canal e passa a anexar nas ofertas até a validade
Nada vai para o canal sem aprovação: os cupons achados no blog ficam pendentes até o Lucas aprovar no widget.
"""
import html
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import requests

import garimpo

AQUI = Path(__file__).parent
ARQ = AQUI / "saida" / "cupons.json"
FEED = "https://shopee.com.br/blog/feed/"
sys.path.insert(0, str(Path.home() / "produtos-digitais" / "deepseek"))

SISTEMA = """Você extrai cupons de desconto de textos do blog oficial da Shopee Brasil.
Só liste um cupom quando o CÓDIGO estiver escrito literalmente no texto. Nunca invente código, valor ou validade.
Se o texto só fala de cupons sem dar código, devolva lista vazia."""
PEDIDO = """Texto do post "{titulo}":
{texto}

Devolva JSON: {{"cupons": [{{"codigo": "...", "desconto": "ex.: R$ 20 OFF ou 15% OFF", "regra": "compra mínima, categoria, limite",
"validade": "AAAA-MM-DD ou vazio"}}]}}"""


def ler():
    return json.loads(ARQ.read_text(encoding="utf-8")) if ARQ.exists() else {"vistos": [], "cupons": []}


def gravar(d):
    ARQ.parent.mkdir(exist_ok=True)
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def _novo_id(d):
    return max([c["id"] for c in d["cupons"]], default=0) + 1


def vigiar():
    from ds import chat
    d = ler()
    xml = requests.get(FEED, headers={"User-Agent": "Mozilla/5.0"}, timeout=60).text
    achados = 0
    for item in re.findall(r"<item>(.*?)</item>", xml, re.S):
        link = re.search(r"<link>(.*?)</link>", item).group(1).strip()
        if link in d["vistos"]:
            continue
        d["vistos"].append(link)
        titulo = html.unescape(re.search(r"<title>(.*?)</title>", item, re.S).group(1))
        corpo = re.search(r"<content:encoded><!\[CDATA\[(.*?)\]\]>", item, re.S)
        texto = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", corpo.group(1) if corpo else item)))
        if not re.search(r"cupo|cupom|c[oó]digo", texto, re.I):
            continue
        for c in chat(PEDIDO.format(titulo=titulo, texto=texto[:12000]), sistema=SISTEMA, json_saida=True, temperatura=0).get("cupons", []):
            codigo = str(c.get("codigo", "")).strip()
            # trava contra invenção: o código tem que estar escrito no post
            if not codigo or codigo not in texto or any(x["codigo"] == codigo for x in d["cupons"]):
                continue
            validade = str(c.get("validade") or "")
            if validade and validade < date.today().isoformat():
                continue  # cupom de post antigo, já vencido
            d["cupons"].append({"id": _novo_id(d), "codigo": codigo, "desconto": c.get("desconto", ""), "regra": c.get("regra", ""),
                                "validade": validade, "fonte": link, "status": "pendente",
                                "achado": datetime.now().strftime("%d/%m %H:%M")})
            achados += 1
    gravar(d)
    # o Lucas preferiu sem aprovação: cupom achado vai direto para o canal
    for c in [x for x in d["cupons"] if x["status"] == "pendente"]:
        postar(c["id"])
    print(f"cupons novos: {achados}")
    return achados


MANUAIS = AQUI / "saida" / "cupons_manuais.json"  # escrito pelo widget (PC); a nuvem importa e posta


def adicionar_manual(codigo, regra, validade="", desconto=""):
    """PC (widget): só anota o cupom; o robô da nuvem posta em até 5 min (cupons.json é arquivo da nuvem)."""
    lista = json.loads(MANUAIS.read_text(encoding="utf-8")) if MANUAIS.exists() else []
    lista.append({"codigo": codigo.strip(), "regra": regra.strip(), "validade": validade, "desconto": desconto,
                  "quando": datetime.now().strftime("%d/%m %H:%M")})
    MANUAIS.write_text(json.dumps(lista, ensure_ascii=False, indent=1), encoding="utf-8")


def importar_manuais():
    """Nuvem: posta os cupons que o Lucas cadastrou no widget e ainda não estão no canal."""
    if not MANUAIS.exists():
        return
    ja = {c["codigo"] for c in ler()["cupons"]}
    for m in json.loads(MANUAIS.read_text(encoding="utf-8")):
        if m["codigo"] not in ja:
            postar(adicionar(m["codigo"], m["regra"], m.get("validade", ""), m.get("desconto", ""))["id"])


def vigiar_no_horario():
    """Blog oficial 2x por dia (8h e 18h), uma vez em cada horário."""
    agora = datetime.now()
    marca = f"{agora:%Y-%m-%d}-{'manha' if agora.hour < 18 else 'noite'}"
    d = ler()
    if agora.hour in (8, 9, 18, 19) and marca not in d.get("vigias", []):
        d.setdefault("vigias", []).append(marca)
        d["vigias"] = d["vigias"][-10:]
        gravar(d)
        vigiar()


def adicionar(codigo, regra, validade="", desconto=""):
    d = ler()
    d["cupons"].append({"id": _novo_id(d), "codigo": codigo.strip(), "desconto": desconto, "regra": regra.strip(),
                        "validade": validade, "fonte": "manual", "status": "pendente", "achado": datetime.now().strftime("%d/%m %H:%M")})
    gravar(d)
    return d["cupons"][-1]


def ativos():
    hoje = date.today().isoformat()
    return [c for c in ler()["cupons"] if c["status"] == "postado" and (not c["validade"] or c["validade"] >= hoje)]


def linha_cupom(c):
    return f"🎟️ Cupom <b>{html.escape(c['codigo'])}</b>: {html.escape(' '.join(x for x in (c['desconto'], c['regra']) if x))}"


def _grupo(c):
    texto = " ".join(str(x) for x in (c.get("desconto"), c.get("regra"), c.get("codigo")) if x)
    texto = texto.lower()
    for g, palavras in garimpo.GRUPOS.items():
        if any(p in texto for p in palavras):
            return g
    return None


def compativel(c, palavra):
    """O cupom combina se a regra dele não cita categoria, ou se a categoria citada é a do produto."""
    g = _grupo(c)
    return g is None or g == garimpo.GRUPO_DA.get(palavra)


def para_produto(palavra, max_n=2):
    """Cupons ativos que valem para a categoria do produto (os específicos primeiro; os genéricos entram depois)."""
    ativos_ = ativos()
    especificos = [c for c in ativos_ if _grupo(c) == garimpo.GRUPO_DA.get(palavra)]
    genericos = [c for c in ativos_ if _grupo(c) is None]
    return (especificos + genericos)[:max_n]


BANNER = AQUI / "saida" / "canal" / "banner_cupom.jpg"


def link_resgate(c):
    """Link de afiliado para a Shopee (página do cupom, se a fonte deu uma; senão a inicial): quem compra depois de entrar gera comissão."""
    from shopee_api import ShopeeAfiliados
    try:
        return ShopeeAfiliados().link_curto(c.get("url") or "https://shopee.com.br/", ["cupom", re.sub(r"\W", "", c["codigo"])[:20]])
    except Exception:
        return "https://shopee.com.br/"


def postar(cid):
    import telegram_bot
    d = ler()
    c = next(x for x in d["cupons"] if x["id"] == int(cid))
    validade = f"\n⏰ Válido até {datetime.fromisoformat(c['validade']):%d/%m}" if c["validade"] else ""
    _, canal = telegram_bot.config()
    oferta = " em ".join(x for x in (c["desconto"], c["regra"]) if x)
    legenda = (f"🔥 <b>Cupom Shopee</b>\n\n🎟️ <b>{html.escape(oferta)}</b>: <code>{html.escape(c['codigo'])}</code>{validade}"
               f"{telegram_bot.rodape(link_resgate(c), 'Resgate aqui')}")
    with open(BANNER, "rb") as foto:
        r = requests.post(f"https://api.telegram.org/bot{telegram_bot.config()[0]}/sendPhoto", timeout=60,
                          data={"chat_id": canal, "caption": legenda, "parse_mode": "HTML"}, files={"photo": foto}).json()
    if not r.get("ok"):
        raise RuntimeError(r.get("description"))
    c["status"] = "postado"
    c["postado"] = datetime.now().strftime("%d/%m %H:%M")
    gravar(d)


def descartar(cid):
    d = ler()
    next(x for x in d["cupons"] if x["id"] == int(cid))["status"] = "descartado"
    gravar(d)


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "vigiar"
    if acao == "vigiar":
        vigiar()
    elif acao == "add":
        print(adicionar(sys.argv[2], sys.argv[3], sys.argv[4] if len(sys.argv) > 4 else ""))
    elif acao == "postar":
        postar(sys.argv[2])
