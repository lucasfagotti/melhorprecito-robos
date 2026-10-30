"""Anúncio que leva direto para o canal do Telegram (link de convite "anuncio", contado em telegram_entradas.json).

Uso: python ads_telegram.py criar      cria campanha (R$ 6/dia), 3 anúncios com cards de oferta, e já ativa
O vigia (ads_mp.py) acompanha: pausa se o mês passar de R$ 186 ou se cada membro sair caro.
Mesma conta de anúncios da Loja que Lucra (robo-ads). Só Instagram (Stories e Reels), mulheres 20–45.
Sem o nome "Shopee" no texto do anúncio (regra do afiliado para anúncio pago).
"""
import json
import sys
from pathlib import Path

import ads_mp
import cards

AQUI = Path(__file__).parent
ESTADO = AQUI / "saida" / "ads_telegram.json"
CONTA = "act_1809559753571949"
PAGINA = "1496038213583415"           # a Meta exige uma página dona; no Instagram aparece o @melhor_precito
INSTAGRAM = "17841462511466551"       # @melhor_precito
TEXTO = "Achadinhos com preço bom todo dia 🛍️ Moda, casa e cozinha. Entra no canal, é grátis e você sai quando quiser."
TITULO = "Canal Melhor Precito no Telegram"


def escolher_produtos():
    """Um produto forte de roupa, cozinha e casa (os grupos que mais vendem para o público feminino)."""
    dados = json.loads((AQUI / "saida" / "garimpo.json").read_text(encoding="utf-8"))["produtos"]
    import garimpo
    escolhidos = []
    for grupo in ("roupas", "cozinha", "casa"):
        p = next((x for x in dados if garimpo.GRUPO_DA.get(x["palavra"]) == grupo and int(x.get("priceDiscountRate") or 0) >= 15
                  and "shopee" not in x["productName"].lower()), None)
        if p:
            escolhidos.append(p)
    return escolhidos


def criar():
    conv = json.loads((AQUI / "saida" / "convites.json").read_text(encoding="utf-8"))["anuncio"]
    est = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {"anuncios": {}}
    if "campanha" not in est:
        est["campanha"] = ads_mp.api("POST", f"{CONTA}/campaigns", name="Melhor Precito - Telegram", objective="OUTCOME_TRAFFIC",
                                     status="PAUSED", special_ad_categories=[], buying_type="AUCTION",
                                     is_adset_budget_sharing_enabled=False)["id"]
        ESTADO.write_text(json.dumps(est, indent=1), encoding="utf-8")
    if "conjunto" not in est:
        alvo = {"geo_locations": {"countries": ["BR"]}, "age_min": 20, "age_max": 45, "genders": [2],
                "publisher_platforms": ["instagram"], "instagram_positions": ["story", "reels"],
                "targeting_automation": {"advantage_audience": 0}}
        est["conjunto"] = ads_mp.api("POST", f"{CONTA}/adsets", name="Telegram - Mulheres 20-45", campaign_id=est["campanha"],
                                     status="PAUSED", daily_budget=600, billing_event="IMPRESSIONS",
                                     bid_strategy="LOWEST_COST_WITHOUT_CAP", optimization_goal="LINK_CLICKS",
                                     destination_type="WEBSITE", targeting=alvo)["id"]
        ESTADO.write_text(json.dumps(est, indent=1), encoding="utf-8")
    import requests
    for p in escolhidos_ou_vazio():
        nome = f"TG - {p['productName'][:40]}"
        if nome in est["anuncios"]:
            continue
        img = cards.card(p, AQUI / "saida" / "cards" / f"anuncio-{p['itemId']}.jpg")
        with open(img, "rb") as fh:
            r = requests.post(f"{ads_mp.G}/{CONTA}/adimages", params={"access_token": ads_mp.token()},
                              files={"filename": (img.name, fh, "image/jpeg")}, timeout=120).json()
        hash_img = next(iter(r["images"].values()))["hash"]
        cri = ads_mp.api("POST", f"{CONTA}/adcreatives", name=nome, object_story_spec={
            "page_id": PAGINA, "instagram_user_id": INSTAGRAM,
            "link_data": {"image_hash": hash_img, "link": conv, "message": TEXTO, "name": TITULO,
                          "call_to_action": {"type": "LEARN_MORE", "value": {"link": conv}}}})["id"]
        est["anuncios"][nome] = ads_mp.api("POST", f"{CONTA}/ads", name=nome, adset_id=est["conjunto"],
                                           creative={"creative_id": cri}, status="ACTIVE")["id"]
        ESTADO.write_text(json.dumps(est, indent=1), encoding="utf-8")
        print("anúncio:", nome, flush=True)
    ads_mp.api("POST", est["conjunto"], status="ACTIVE")
    ads_mp.api("POST", est["campanha"], status="ACTIVE")
    print("campanha ATIVA:", est["campanha"], flush=True)


def escolhidos_ou_vazio():
    ps = escolher_produtos()
    if not ps:
        raise SystemExit("garimpo sem produto bom para o anúncio")
    return ps


if __name__ == "__main__":
    if sys.argv[1:] == ["criar"]:
        criar()
