"""Instagram @melhor_precito: quem comenta EU QUERO (ou LINK, QUERO...) num Reel recebe resposta pública + o link do produto no direct.

Uso: python comentarios_ig.py            verifica uma vez
     python comentarios_ig.py --teste    mostra o que responderia, sem responder
Cada Reel postado pelo instagram_bot.py fica ligado ao seu produto (saida/instagram.json guarda media -> link de afiliado).
Base: robô de comentários da Loja que Lucra (mesmas regras da Meta: direct só até 7 dias do comentário, 200 chamadas/hora).
Permissões do token: instagram_business_manage_comments e instagram_business_manage_messages.
"""
import datetime as dt
import json
import random
import re
import sys
import time
import unicodedata
from pathlib import Path

from instagram_bot import ig, minha_conta

AQUI = Path(__file__).parent
POSTS = AQUI / "saida" / "instagram.json"
ESTADO = AQUI / "saida" / "instagram_comentarios.json"
JANELA = dt.timedelta(days=7)
GATILHOS = r"\b(EU ?QUERO|QUERO|LINK|ONDE COMPR\w*|QUANTO|PRECO|MANDA)\b"
PUBLICAS = ["Te mandei no direct! 💌", "Enviado no seu direct 😉", "Corre no direct que mandei o link! 🛒", "Link no seu direct 💛"]
CANAL = "t.me/melhorprecito"


def normalizar(t):
    t = unicodedata.normalize("NFD", t.upper())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def mapa_posts():
    """media id -> produto (curto, link) de todos os Reels publicados pelo robô."""
    dias = json.loads(POSTS.read_text(encoding="utf-8")) if POSTS.exists() else {}
    return {p["media"]: p for lista in dias.values() for p in lista if p.get("link")}


def rodar(teste=False):
    posts = mapa_posts()
    if not posts:
        return
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    for k in ("comentarios", "enviados", "contagem"):
        estado.setdefault(k, {})
    uid = estado.get("uid") or minha_conta()
    estado["uid"] = uid
    agora = dt.datetime.now(dt.timezone.utc)
    # uma chamada traz a contagem de comentários de todos os posts; só abre os que mudaram
    medias = ig("GET", f"{uid}/media", fields="id,comments_count", limit=30).get("data", [])
    for m in medias:
        if m["id"] not in posts or m.get("comments_count", 0) == estado["contagem"].get(m["id"], 0):
            continue
        produto = posts[m["id"]]
        for c in ig("GET", f"{m['id']}/comments", fields="id,text,from,timestamp", limit=50).get("data", []):
            autor = c.get("from") or {}
            if c["id"] in estado["comentarios"] or autor.get("id") == uid:
                continue
            quando = dt.datetime.fromisoformat(c["timestamp"].replace("+0000", "+00:00"))
            if not re.search(GATILHOS, normalizar(c.get("text", ""))) or agora - quando > JANELA:
                continue
            if teste:
                print(f"[teste] responderia @{autor.get('username', '?')}: {c.get('text', '')[:60]}")
                continue
            chave = f"{autor.get('id', c['id'])}:{m['id']}"
            try:
                ig("POST", f"{c['id']}/replies", message=random.choice(PUBLICAS))
                if chave not in estado["enviados"]:  # uma vez por pessoa por Reel
                    texto = (f"Oi! Aqui está o link do {produto['curto']} 👇\n{produto['link']}\n\n"
                             f"Todo dia tem achado novo no meu canal do Telegram: {CANAL} 💛")
                    import requests
                    from instagram_bot import API, token
                    r = requests.post(f"{API}/{uid}/messages", params={"access_token": token()}, timeout=60,
                                      json={"recipient": {"comment_id": c["id"]}, "message": {"text": texto}})
                    if not r.ok:
                        raise RuntimeError(r.text[:300])
                    estado["enviados"][chave] = agora.isoformat()
                estado["comentarios"][c["id"]] = True
                print(f"respondido @{autor.get('username', '?')} ({produto['curto']})", flush=True)
            except Exception as erro:
                print(f"ERRO @{autor.get('username', '?')}: {erro}", flush=True)
            ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
            time.sleep(2)
        if not teste:
            estado["contagem"][m["id"]] = m.get("comments_count", 0)
    ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    rodar("--teste" in sys.argv)
