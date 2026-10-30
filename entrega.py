"""Manda no Telegram PRIVADO do Lucas os vídeos do dia para postar no Shopee Vídeo, cada um com a ficha pronta.

Uso: python entrega.py              vídeos de hoje (só manda uma vez por dia)
     python entrega.py 2026-11-01   outro dia (e manda mesmo se já mandou)
Roda no PC (os vídeos estão aqui): tarefa às 6h30 e logo que o PC liga, se ainda não mandou.
Quem recebe: o primeiro que mandou /start no privado do @melhorprecito_bot (registrado pela nuvem em telegram_entradas.json).
"""
import sem_janela  # noqa: F401
import json
import sys
from datetime import date
from pathlib import Path

import requests

import onedrive
import telegram_bot

AQUI = Path(__file__).parent
FEITO = AQUI / "saida" / "entregas.json"


DONO = AQUI / "saida" / "telegram_dono.json"  # chat privado do Lucas (anotado no 1º /start)


def chat_do_lucas():
    if DONO.exists():
        return json.loads(DONO.read_text(encoding="utf-8"))["chat"]
    import subprocess
    subprocess.run(["git", "pull", "-q", "--rebase", "--autostash"], cwd=AQUI, capture_output=True)  # pega o /start registrado
    ent = AQUI / "saida" / "telegram_entradas.json"
    privados = json.loads(ent.read_text(encoding="utf-8")).get("privados", {}) if ent.exists() else {}
    if not privados:
        raise SystemExit("ninguém mandou /start no privado do bot ainda")
    return next(iter(privados))


def ficha(i):
    preco = f"{i['preco']:.2f}".replace(".", ",")
    bloco = onedrive.bloco(i["horario"])
    return (f"<b>{i['n']:02d} · {bloco} ({i['horario']})</b>\n\n🏷️ <b>Marcar:</b> {i['produto']}\n🏪 <b>Loja:</b> {i['loja']}\n"
            f"💰 Preço no vídeo: R$ {preco}\n\n📋 <b>Legenda</b> (toque e segure pra copiar):\n<code>{i['legenda']}\n\n{i['hashtags']}</code>")[:1024]


def entregar(dia=None, forcar=False):
    dia = dia or date.today().isoformat()
    feito = json.loads(FEITO.read_text(encoding="utf-8")) if FEITO.exists() else {}
    if feito.get(dia) and not forcar:
        print("já entregue hoje")
        return
    arq = AQUI / "saida" / "dias" / dia / "plano.json"
    if not arq.exists():
        print("sem vídeos para", dia)
        return
    itens = [i for i in json.loads(arq.read_text(encoding="utf-8"))["itens"] if not i.get("descartado")]
    token, _ = telegram_bot.config()
    chat = chat_do_lucas()
    d = date.fromisoformat(dia)
    telegram_bot.tg("sendMessage", chat_id=chat, parse_mode="HTML",
                    text=f"📦 <b>Vídeos do Shopee Vídeo — {onedrive.SEMANA[d.weekday()]} {d:%d/%m}</b>\n\n"
                         f"☀️ Manhã (07:00): os 4 primeiros\n🌙 Noite (20:00): os outros\n\n"
                         f"Poste 1 a 2 min um do outro, marcando o produto da loja certa. Depois marque \"Postei\" no widget.")
    for i in itens:
        with open(i["video"], "rb") as fh:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo", timeout=300, files={"video": fh},
                              data={"chat_id": chat, "caption": ficha(i), "parse_mode": "HTML", "supports_streaming": "true"}).json()
        if not r.get("ok"):
            print(f"vídeo {i['n']} falhou: {r.get('description')}", flush=True)
    feito[dia] = True
    FEITO.write_text(json.dumps(feito, indent=1), encoding="utf-8")
    print(f"entregue: {len(itens)} vídeos de {dia}", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:]
    entregar(args[0] if args else None, forcar=bool(args))
