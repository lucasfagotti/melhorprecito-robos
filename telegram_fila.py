"""Fila contínua de ofertas no Telegram (além dos 10 produtos com vídeo): foto + preço + desconto + link, num ritmo fixo.

Ritmo em saida/telegram_config.json: intervalo normal, intervalo em dia de campanha (11.11, Black Friday, 12.12...)
e horário de silêncio de madrugada. Roda dentro da tarefa do Telegram (a cada 10 min), em laço até a próxima rodada.
"""
import html
import json
import random
import re
import time
from datetime import date, datetime
from pathlib import Path

import cupons
import garimpo
import telegram_bot
from regras import FORA_DO_DIARIO, PROIBIDOS
from shopee_api import ShopeeAfiliados

AQUI = Path(__file__).parent
CONFIG = AQUI / "saida" / "telegram_config.json"
POSTADOS = AQUI / "saida" / "telegram_fila.json"
PADRAO = {"intervalo_normal": 10, "intervalo_campanha": 3, "inicio": "07:30", "fim": "23:30", "repetir_apos_dias": 3,
          "datas_campanha": ["2026-11-11", "2026-11-27", "2026-11-28", "2026-12-12"]}
GANCHOS = ["🔥 ACHADINHO", "⚡ OFERTA", "💥 PREÇO BOM", "🛍️ ACHEI", "👀 OLHA ESSE", "✨ ACHADO DO DIA", "🏃 CORRE"]


def config():
    if not CONFIG.exists():
        CONFIG.write_text(json.dumps(PADRAO, indent=1), encoding="utf-8")
    return {**PADRAO, **json.loads(CONFIG.read_text(encoding="utf-8"))}


def estado():
    return json.loads(POSTADOS.read_text(encoding="utf-8")) if POSTADOS.exists() else {"ultimo": 0, "itens": {}, "hoje": {}}


def nome_curto(nome):
    nome = re.sub(r"[\[\(【].*?[\]\)】]", "", nome).strip()
    return nome if len(nome) <= 70 else nome[:70].rsplit(" ", 1)[0] + "…"


def _dias_desde(iso):
    try:
        return (date.today() - date.fromisoformat(iso)).days
    except Exception:
        return 10 ** 9


def proximo(est, cfg):
    """Melhor produto do garimpo, alternando categorias; só repete depois de repetir_apos_dias dias
    (tanto na fila quanto em relação aos vídeos do dia)."""
    dados = json.loads((AQUI / "saida" / "garimpo.json").read_text(encoding="utf-8"))["produtos"]
    historico = AQUI / "saida" / "historico.json"
    usados_plano = json.loads(historico.read_text(encoding="utf-8")) if historico.exists() else {}
    agora = time.time()
    janela = cfg["repetir_apos_dias"] * 86400
    livres = [p for p in dados if p["palavra"] not in FORA_DO_DIARIO and not PROIBIDOS.search(p["productName"])
              and agora - est["itens"].get(str(p["itemId"]), 0) > janela
              and _dias_desde(usados_plano.get(str(p["itemId"]), "")) >= cfg["repetir_apos_dias"]]
    if not livres:
        return None
    ultima_cat = est.get("ultima_cat")
    outras = [p for p in livres if p["palavra"] != ultima_cat] or livres
    return random.choice(outras[:8])  # um dos 8 melhores, pra não ficar previsível


def texto(p, link):
    preco = f"{float(p['price']):.2f}".replace(".", ",")
    desc = int(p.get("priceDiscountRate") or 0)
    linhas = [f"{random.choice(GANCHOS)}", "", f"<b>{html.escape(nome_curto(p['productName']))}</b>", "",
              f"💰 <b>R$ {preco}</b>" + (f"  🔥 <b>{desc}% OFF</b>" if desc >= 10 else ""),
              f"⭐ {p['ratingStar']} · {int(p['sales']):,} vendidos".replace(",", ".")]
    linhas.append("\n".join(cupons.linha_cupom(c) for c in cupons.para_produto(p["palavra"], max_n=1)) or "🎟️ Confira os cupons da Shopee no carrinho")
    return "\n".join(linhas) + telegram_bot.rodape(link)


def postar_um(api, est, cfg):
    p = proximo(est, cfg)
    if not p:
        # pool esgotada: garimpa produtos novos em vez de repetir oferta recém-postada
        try:
            garimpo.salvar(garimpo.garimpar(garimpo.PALAVRAS))
        except Exception as erro:
            print(f"fila regarimpo falhou: {erro}", flush=True)
        p = proximo(est, cfg)
    if not p:
        return False
    try:
        link = api.link_curto(p.get("productLink") or p["offerLink"], ["telegramfila", str(p["itemId"])])
    except Exception:
        link = p["offerLink"]
    _, canal = telegram_bot.config()
    telegram_bot.foto_card(p, texto(p, link), link)
    hoje = date.today().isoformat()
    est["itens"][str(p["itemId"])] = time.time()
    est["ultima_cat"] = p["palavra"]
    est["ultimo"] = time.time()
    est["hoje"] = {hoje: est.get("hoje", {}).get(hoje, 0) + 1}
    POSTADOS.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    print(f"fila: {nome_curto(p['productName'])[:50]}", flush=True)
    return True


def tick(api, cfg=None):
    """Um passo da fila: posta se estiver no horário e já passou o intervalo desde a última oferta."""
    cfg = cfg or config()
    agora = datetime.now().strftime("%H:%M")
    if not cfg["inicio"] <= agora <= cfg["fim"]:
        return
    est = estado()
    intervalo = cfg["intervalo_campanha"] if date.today().isoformat() in cfg["datas_campanha"] else cfg["intervalo_normal"]
    if time.time() - est["ultimo"] >= intervalo * 60:
        postar_um(api, est, cfg)


def rodar(minutos=9.5):
    """Laço de ~10 min: posta no ritmo configurado; a próxima tarefa agendada continua de onde parou."""
    cfg = config()
    api = ShopeeAfiliados()
    fim_laco = time.time() + minutos * 60
    while time.time() < fim_laco:
        agora = datetime.now().strftime("%H:%M")
        if cfg["inicio"] <= agora <= cfg["fim"]:
            est = estado()
            intervalo = cfg["intervalo_campanha"] if date.today().isoformat() in cfg["datas_campanha"] else cfg["intervalo_normal"]
            if time.time() - est["ultimo"] >= intervalo * 60:
                try:
                    postar_um(api, est, cfg)
                except Exception as erro:
                    print(f"fila erro: {erro}", flush=True)
        time.sleep(20)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["um"]:
        postar_um(ShopeeAfiliados(), estado(), config())
    else:
        rodar()
