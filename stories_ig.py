"""Stories do @melhor_precito: o card de oferta (cards.py) de um achadinho, várias vezes por dia.

Uso: python stories_ig.py      publica o próximo Story se já chegou o horário
Produtos: os mesmos do garimpo (sem repetir os dos últimos dias), alternando categorias, como a fila do Telegram.
Na nuvem a imagem vai para o GitHub Pages do repositório dos robôs; no PC, para o repositório de mídia.
"""
import json
import time
from datetime import date, datetime
from pathlib import Path

import instagram_bot
import telegram_fila
from instagram_bot import ig, minha_conta

AQUI = Path(__file__).parent
ESTADO = AQUI / "saida" / "instagram_stories.json"
HORARIOS = ["08:00", "09:30", "11:00", "13:00", "14:30", "16:00", "17:30", "19:00", "20:30", "22:00"]


def _hospedar(arquivo, nome):
    if instagram_bot.NA_NUVEM:
        import nuvem
        return nuvem.hospedar(arquivo, nome), lambda: nuvem.remover(nome)
    return instagram_bot.hospedar(arquivo, nome), lambda: instagram_bot.limpar_hospedagem([nome])


def postar():
    hoje = date.today().isoformat()
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    feitos = estado.setdefault(hoje, [])
    agora = datetime.now().strftime("%H:%M")
    devidos = [h for h in HORARIOS if h <= agora]
    if len(feitos) >= len(devidos):
        return
    est_fila = telegram_fila.estado()
    est_fila["ultima_cat"] = estado.get("ultima_cat")
    est_fila["itens"] = dict(estado.get("vistos", {}))  # não repete o que já foi Story nos últimos dias
    p = telegram_fila.proximo(est_fila, telegram_fila.config())
    if not p:
        return
    import cards
    url, apagar = _hospedar(cards.card_cache(p), f"story-{hoje}-{p['itemId']}.jpg")
    try:
        uid = minha_conta()
        c = ig("POST", f"{uid}/media", media_type="STORIES", image_url=url)
        for _ in range(30):
            time.sleep(5)
            if ig("GET", c["id"], fields="status_code")["status_code"] == "FINISHED":
                break
        ig("POST", f"{uid}/media_publish", creation_id=c["id"])
    finally:
        apagar()
    feitos.append({"itemId": str(p["itemId"]), "hora": agora})
    estado.setdefault("vistos", {})[str(p["itemId"])] = time.time()
    estado["ultima_cat"] = p["palavra"]
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"story: {telegram_fila.nome_curto(p['productName'])[:50]}", flush=True)


if __name__ == "__main__":
    postar()
