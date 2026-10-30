"""Conta quem entra no canal e por onde veio (cada origem tem um link de convite próprio, em saida/convites.json).

Roda nos turnos da nuvem. Lê as atualizações de membros do Telegram (getUpdates, só "chat_member") e grava em
saida/telegram_entradas.json: {dia: {origem: entradas}}. Quem entra pelo @ ou pela busca conta como "busca/@".
Serve para saber quanto custou cada membro de cada lugar (anúncio, parceiro...) antes de pôr mais dinheiro.
"""
import json
from datetime import date
from pathlib import Path

import telegram_bot

AQUI = Path(__file__).parent
ARQ = AQUI / "saida" / "telegram_entradas.json"
MEMBRO = {"member", "administrator", "creator"}
FORA = {"left", "kicked"}


def contar():
    d = json.loads(ARQ.read_text(encoding="utf-8")) if ARQ.exists() else {"offset": 0, "dias": {}, "saidas": {}}
    atualizacoes = telegram_bot.tg("getUpdates", offset=d["offset"], timeout=0, allowed_updates=["chat_member", "message"])
    for u in atualizacoes:
        d["offset"] = u["update_id"] + 1
        msg = u.get("message") or {}
        if msg.get("chat", {}).get("type") == "private":
            # quem mandou /start no privado do bot: o primeiro é o Lucas (recebe os vídeos do dia, ver entrega.py)
            de = msg.get("from", {})
            d.setdefault("privados", {}).setdefault(str(msg["chat"]["id"]), {"nome": de.get("first_name", ""),
                                                                            "usuario": de.get("username", "")})
            continue
        m = u.get("chat_member")
        if not m:
            continue
        antes, depois = m["old_chat_member"]["status"], m["new_chat_member"]["status"]
        dia = date.fromtimestamp(m["date"]).isoformat()
        if antes in FORA and depois in MEMBRO:
            origem = (m.get("invite_link") or {}).get("name") or "busca/@"
            d["dias"].setdefault(dia, {})
            d["dias"][dia][origem] = d["dias"][dia].get(origem, 0) + 1
        elif antes in MEMBRO and depois in FORA:
            d["saidas"][dia] = d["saidas"].get(dia, 0) + 1
    ARQ.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    return d


if __name__ == "__main__":
    print(json.dumps(contar(), ensure_ascii=False, indent=1))
