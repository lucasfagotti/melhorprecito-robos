"""Vigia do anúncio do @melhor_precito (R$ 6/dia, objetivo: visitas ao perfil -> seguidores).

Roda junto com o robô do Instagram (a cada 30 min). Grava saida/ads_melhorprecito_numeros.json para o widget e:
- pausa a campanha se o gasto do mês dela chegar a R$ 186 (R$ 6 x 31): nunca aumenta orçamento;
- pausa se o custo por seguidor ganho passar de R$ 2 depois de R$ 20 gastos (anúncio ruim: trocar o Reel).
Token: o do robo-ads da Loja que Lucra (mesma conta de anúncios), lido do .env de lá sem aparecer em lugar nenhum.
"""
import json
import os
from datetime import date
from pathlib import Path

import requests
from dotenv import dotenv_values

AQUI = Path(__file__).parent
ESTADO = AQUI / "saida" / "ads_melhorprecito.json"
NUMEROS = AQUI / "saida" / "ads_melhorprecito_numeros.json"
G = "https://graph.facebook.com/v25.0"
LIMITE_MES = 186.0
MAX_CUSTO_SEGUIDOR = 2.0
MIN_GASTO_PARA_JULGAR = 20.0


def token():
    # o robo-ads guarda o token nas variáveis do Windows (setx) ou no .env do social-bot
    return os.environ.get("META_ADS_TOKEN") or dotenv_values(Path.home() / "produtos-digitais" / "social-bot" / ".env").get("META_ADS_TOKEN")


def api(metodo, caminho, **dados):
    r = requests.request(metodo, f"{G}/{caminho}", params={"access_token": token(), **({} if metodo == "POST" else dados)},
                         json=dados if metodo == "POST" else None, timeout=60).json()
    if "error" in r:
        raise RuntimeError(r["error"].get("error_user_msg") or r["error"]["message"])
    return r


def seguidores():
    import instagram_bot
    return instagram_bot.ig("GET", "me", fields="followers_count").get("followers_count", 0)


def monitorar():
    if not ESTADO.exists():
        return
    est = json.loads(ESTADO.read_text(encoding="utf-8"))
    status = api("GET", est["campanha"], fields="effective_status")["effective_status"]
    total = (api("GET", f"{est['campanha']}/insights", fields="spend,actions", date_preset="maximum").get("data") or [{}])[0]
    mes = (api("GET", f"{est['campanha']}/insights", fields="spend", date_preset="this_month").get("data") or [{}])[0]
    gasto, gasto_mes = float(total.get("spend", 0)), float(mes.get("spend", 0))
    visitas = sum(int(float(a["value"])) for a in total.get("actions", []) if "profile" in a["action_type"] or a["action_type"] == "link_click")
    seg = seguidores()
    est.setdefault("seguidores_inicio", seg)
    ganhos = max(0, seg - est["seguidores_inicio"])
    custo_seg = gasto / ganhos if ganhos else None
    motivo = None
    if status == "ACTIVE" and gasto_mes >= LIMITE_MES:
        motivo = f"limite do mês (R$ {LIMITE_MES:.0f}) atingido"
    elif status == "ACTIVE" and gasto >= MIN_GASTO_PARA_JULGAR and (custo_seg is None or custo_seg > MAX_CUSTO_SEGUIDOR):
        motivo = f"seguidor saindo caro (R$ {custo_seg:.2f})" if custo_seg else "R$ 20 gastos sem seguidor novo"
    if motivo:
        api("POST", est["campanha"], status="PAUSED")
        status = "PAUSED"
        est["pausado_por"] = motivo
        print(f"anúncio pausado: {motivo}", flush=True)
    ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding="utf-8")
    NUMEROS.write_text(json.dumps({"quando": date.today().isoformat(), "status": status, "gasto": gasto, "gasto_mes": gasto_mes,
                                   "visitas_perfil": visitas, "seguidores": seg, "seguidores_ganhos": ganhos,
                                   "custo_por_seguidor": custo_seg, "pausado_por": est.get("pausado_por")},
                                  ensure_ascii=False, indent=1), encoding="utf-8")


TG_ESTADO = AQUI / "saida" / "ads_telegram.json"
TG_NUMEROS = AQUI / "saida" / "ads_telegram_numeros.json"
MAX_CUSTO_MEMBRO = 3.0  # R$ por membro novo no canal (contado pelo link de convite "anuncio")


def monitorar_telegram():
    """Anúncio do canal: custo por membro = gasto ÷ entradas pelo link "anuncio" (entradas.py)."""
    if not TG_ESTADO.exists():
        return
    est = json.loads(TG_ESTADO.read_text(encoding="utf-8"))
    status = api("GET", est["campanha"], fields="effective_status")["effective_status"]
    total = (api("GET", f"{est['campanha']}/insights", fields="spend,inline_link_clicks", date_preset="maximum").get("data") or [{}])[0]
    mes = (api("GET", f"{est['campanha']}/insights", fields="spend", date_preset="this_month").get("data") or [{}])[0]
    gasto, gasto_mes, cliques = float(total.get("spend", 0)), float(mes.get("spend", 0)), int(total.get("inline_link_clicks", 0))
    ent = AQUI / "saida" / "telegram_entradas.json"
    dias = json.loads(ent.read_text(encoding="utf-8")).get("dias", {}) if ent.exists() else {}
    membros = sum(d.get("anuncio", 0) for d in dias.values())
    custo = gasto / membros if membros else None
    motivo = None
    if status == "ACTIVE" and gasto_mes >= LIMITE_MES:
        motivo = f"limite do mês (R$ {LIMITE_MES:.0f}) atingido"
    elif status == "ACTIVE" and gasto >= MIN_GASTO_PARA_JULGAR and (custo is None or custo > MAX_CUSTO_MEMBRO):
        motivo = f"membro saindo caro (R$ {custo:.2f})" if custo else "R$ 20 gastos sem membro novo"
    if motivo:
        api("POST", est["campanha"], status="PAUSED")
        status, est["pausado_por"] = "PAUSED", motivo
        TG_ESTADO.write_text(json.dumps(est, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"anúncio do Telegram pausado: {motivo}", flush=True)
    TG_NUMEROS.write_text(json.dumps({"quando": date.today().isoformat(), "status": status, "gasto": gasto, "gasto_mes": gasto_mes,
                                      "cliques": cliques, "membros": membros, "custo_por_membro": custo,
                                      "pausado_por": est.get("pausado_por")}, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    monitorar()
    print(NUMEROS.read_text(encoding="utf-8"))
