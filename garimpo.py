"""Garimpo: produtos que vendem, pagam boa comissão e têm cara de pouca concorrência entre afiliados.

Uso: python garimpo.py                 varre todas as categorias de PALAVRAS
     python garimpo.py "termo" ...      só esses termos
Saída: saida/garimpo.csv (abre no Excel), ordenado pela nota de oportunidade.

A API não diz quantos afiliados divulgam um produto; a concorrência é estimada por sinais:
- vendas recentes medianas (o top 1 viral de cada busca já está na mão de todo mundo);
- comissão extra paga pelo vendedor (sellerCommissionRate): oferta que ele precisa empurrar;
- oferta começou há pouco (periodStartTime): menos afiliados acharam ainda.
"""
import csv
import json
import math
import re
import sys
import time
from pathlib import Path

from shopee_api import CAMPOS_PRODUTO, MAIOR_COMISSAO, MAIS_VENDIDOS, ShopeeAfiliados

SAIDA = Path(__file__).parent / "saida"
# público feminino: o que ELAS compram (roupa, calçado, acessório, cozinha, casa, brinquedo/bebê); nada masculino.
# GRUPOS + COTAS (diario.py) decidem quantos vídeos de cada grupo por dia.
GRUPOS = {
    "roupas": ["vestido", "conjunto feminino", "blusa feminina", "cropped", "saia feminina", "calca feminina", "legging",
               "short feminino", "moda praia", "biquini", "fitness feminino", "pijama feminino"],
    "calcados": ["calcado feminino", "sandalia feminina", "tenis feminino", "rasteirinha"],
    "acessorios": ["bolsa feminina", "bijuteria", "brinco", "relogio feminino", "oculos de sol feminino", "maquiagem",
                   "acessorios cabelo"],
    "cozinha": ["utensilios cozinha", "potes cozinha", "acessorios air fryer", "organizador cozinha", "garrafa termica"],
    "casa": ["organizador", "decoracao casa", "cama mesa banho", "limpeza casa", "decoracao natal", "tapete"],
    "brinquedos": ["brinquedo", "brinquedo educativo", "bebe", "boneca"],
}
PALAVRAS = [p for lista in GRUPOS.values() for p in lista]
GRUPO_DA = {p: g for g, lista in GRUPOS.items() for p in lista}
MIN_NOTA = 4.7
MIN_VENDAS = 50          # vendas recentes
MIN_TAXA = 0.12          # 12%
MIN_GANHO = 4.0          # R$ por venda
VIRAL = 20000            # acima disso quase certo que está saturado
AGORA = time.time()


def oportunidade(p):
    ganho = float(p["commission"])
    vendas = int(p["sales"])
    extra = float(p.get("sellerCommissionRate") or 0)
    dias = max(0, (AGORA - int(p.get("periodStartTime") or 0)) / 86400)
    # ganho por venda x demanda (com teto, pra não premiar o viral) x bônus de comissão extra e de oferta nova
    nota = ganho * math.sqrt(min(vendas, 5000))
    nota *= 1 + min(extra, 0.5)
    nota *= 1.25 if dias < 30 else 1.0
    nota *= 0.5 if vendas > VIRAL else 1.0
    return round(nota, 1)


def concorrencia(p):
    vendas = int(p["sales"])
    if vendas > VIRAL:
        return "alta"
    if vendas > 3000 and float(p.get("sellerCommissionRate") or 0) < 0.05:
        return "média"
    return "baixa"


# listas prontas do painel: 0 = vitrine "Todos" (recomendados), 2 = "Melhor performance"
LISTAS = (0, 2)
# produto da lista não tem palavra de busca: o nome diz o grupo (a 1ª regra que casar vale)
CLASSIFICAR = [
    ("lista-acessorios", r"body ?splash|perfume|col[oô]nia|desodorante"),  # antes de roupa: "body splash" não é body
    ("lista-roupas", r"vestido|conjunto|blusa|cropped|saia|cal[cç]a|legging|short|biqu[ií]ni|mai[oô]|pijama|baby ?doll|camiseta|"
                     r"t-?shirt|macac[aã]o|\bbody\b|top\b|suti[aã]|calcinha|lingerie|moletom|jaqueta"),
    ("lista-calcados", r"sand[aá]lia|t[eê]nis|rasteir|sapat|chinelo|bota|tamanco|papete|scarpin|mule\b"),
    ("lista-acessorios", r"bolsa|brinco|colar|pulseira|anel|rel[oó]gio|[oó]culos|maquiagem|batom|c[ií]lios|base\b|paleta|"
                         r"secador|escova.*cabelo|chapinha|modelador|cabelo|perfume|unha"),
    ("lista-cozinha", r"garrafa|copo|caneca|pote|panela|frigideira|air ?fryer|airfryer|omeleteira|cozinha|talher|faca|"
                      r"t[aá]bua|liquidificador|cafeteira|chaleira|marmita|lancheira"),
    ("lista-casa", r"organizador|toalha|len[cç]ol|edredom|cortina|tapete|decora|lumin[aá]ria|limpeza|vassoura|mop|cabide|"
                   r"travesseiro|almofada|colch[aã]o|prateleira|cama\b"),
    ("lista-brinquedos", r"boneca|brinquedo|beb[eê]|infantil|reborn|pel[uú]cia|carrinho de brinquedo|lego|quebra-cabe[cç]a"),
]
# marca famosa por preço de banana: quase sempre falsificado (reclamação, devolução e comissão cancelada)
MARCAS = re.compile(r"\b(jbl|apple|iphone|airpods?|samsung|galaxy buds|nike|adidas|stanley|lacoste|ray-?ban|oakley|dior|chanel|"
                    r"louis vuitton|gucci|prada|dyson|xbox|playstation|ps5)\b", re.I)
GRUPOS_LISTA = {"lista-roupas": "roupas", "lista-calcados": "calcados", "lista-acessorios": "acessorios",
                "lista-cozinha": "cozinha", "lista-casa": "casa", "lista-brinquedos": "brinquedos"}
GRUPO_DA.update(GRUPOS_LISTA)


def classificar(nome):
    return next((palavra for palavra, regra in CLASSIFICAR if re.search(regra, nome, re.I)), None)


# fora do público/do que dá pra divulgar sem promessa: masculino e suplemento
FORA = re.compile(r"\bmasculin|\bhomem\b|\bhomens\b|creatina|whey|suplemento|pr[eé]-?treino|termog[eê]nico", re.I)


def suspeito(p):
    return bool(MARCAS.search(p["productName"])) and float(p["price"]) < 150 or bool(FORA.search(p["productName"]))


def bom(p):
    return (float(p.get("ratingStar") or 0) >= MIN_NOTA and int(p.get("sales") or 0) >= MIN_VENDAS
            and float(p.get("commissionRate") or 0) >= MIN_TAXA and float(p.get("commission") or 0) >= MIN_GANHO
            and not suspeito(p))


def garimpar_listas(api, vistos):
    """Vitrine e "Melhor performance" do painel: produtos que a Shopee já viu vendendo bem pelos afiliados."""
    q = f"query($t:Int,$p:Int){{productOfferV2(listType:$t,page:$p,limit:50){{nodes{{ {CAMPOS_PRODUTO} }}}}}}"
    for tipo in LISTAS:
        for pagina in (1, 2, 3):
            try:
                nodes = api.consultar(q, {"t": tipo, "p": pagina})["productOfferV2"]["nodes"]
            except Exception as erro:
                print(f"  lista {tipo}: erro {erro}")
                break
            for p in nodes:
                palavra = classificar(p["productName"])
                if palavra and bom(p) and p["itemId"] not in vistos:  # fora dos grupos (creatina, ferramenta...) não entra
                    p["palavra"] = palavra
                    vistos[p["itemId"]] = p
            time.sleep(0.3)
    print(f"listas do painel: {len(vistos)} aprovados até agora", flush=True)


def garimpar(palavras):
    api = ShopeeAfiliados()
    vistos = {}
    garimpar_listas(api, vistos)
    for palavra in palavras:
        for ordem in (MAIOR_COMISSAO, MAIS_VENDIDOS):
            try:
                nodes = api.buscar_produtos(palavra, ordem=ordem, limite=50)["nodes"]
            except Exception as erro:
                print(f"  {palavra}: erro {erro}")
                continue
            for p in nodes:
                if bom(p) and p["itemId"] not in vistos:
                    p["palavra"] = palavra
                    vistos[p["itemId"]] = p
            time.sleep(0.3)
        print(f"{palavra}: {len(vistos)} aprovados até agora", flush=True)
    return sorted(vistos.values(), key=oportunidade, reverse=True)


def salvar(produtos):
    SAIDA.mkdir(exist_ok=True)
    resumo = [{**{k: p.get(k) for k in ("itemId", "productName", "shopName", "price", "sales", "ratingStar", "commissionRate",
                                        "sellerCommissionRate", "commission", "imageUrl", "offerLink", "productLink",
                                        "priceDiscountRate", "palavra")},
               "oportunidade": oportunidade(p), "concorrencia": concorrencia(p)} for p in produtos]
    (SAIDA / "garimpo.json").write_text(json.dumps({"quando": time.strftime("%d/%m %H:%M"), "produtos": resumo}, ensure_ascii=False),
                                        encoding="utf-8")
    with open(SAIDA / "garimpo.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Oportunidade", "Concorrência", "Produto", "Loja", "Preço", "Vendas recentes", "Nota",
                    "Comissão %", "Extra do vendedor %", "Ganho/venda", "Oferta desde", "Busca", "Link afiliado"])
        for p in produtos:
            w.writerow([str(oportunidade(p)).replace(".", ","), concorrencia(p), p["productName"], p["shopName"],
                        p["price"].replace(".", ","), p["sales"], p["ratingStar"],
                        f"{float(p['commissionRate']) * 100:.0f}", f"{float(p.get('sellerCommissionRate') or 0) * 100:.0f}",
                        f"{float(p['commission']):.2f}".replace(".", ","),
                        time.strftime("%d/%m/%Y", time.localtime(int(p.get("periodStartTime") or 0))),
                        p["palavra"], p.get("offerLink") or p["productLink"]])


if __name__ == "__main__":
    produtos = garimpar(sys.argv[1:] or PALAVRAS)
    salvar(produtos)
    print(f"\n{len(produtos)} produtos em saida/garimpo.csv. Top 25:")
    for p in produtos[:25]:
        print(f"{oportunidade(p):>7} | {concorrencia(p):5} | R$ {float(p['commission']):5.2f}/venda "
              f"({float(p['commissionRate']) * 100:.0f}%) | {int(p['sales']):>6} vend | {p['ratingStar']}★ | "
              f"R$ {p['price']:>7} | {p['productName'][:55]}")
