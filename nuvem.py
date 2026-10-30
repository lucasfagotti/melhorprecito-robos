"""Turno dos robôs no GitHub Actions (repo lucasfagotti/melhorprecito-robos). Cada turno dura ~28 min e o próximo
começa sozinho (agendado a cada 30 min); tudo que muda é salvo no repositório na hora, para o turno seguinte continuar.

O que roda: fila de ofertas do Telegram (no ritmo de telegram_config.json), ofertas dos vídeos do dia, comentários
"EU QUERO" (a cada 5 min), Reels e Stories do Instagram, vigia do anúncio, cupons (blog 8h e 18h + os que o Lucas
cadastrar no widget) e a renovação do token do Instagram.

Divisão para PC e nuvem nunca escreverem no mesmo arquivo:
- PC escreve: saida/dias/*/plano.json, saida/garimpo.json, saida/cupons_manuais.json
- nuvem escreve: o resto de saida/*.json, saida/cards/destaques.json e docs/midia/ (imagens dos Stories)
"""
import os
import shutil
import subprocess
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import requests

AQUI = Path(__file__).parent
MIDIA = AQUI / "docs" / "midia"
PAGES = "https://lucasfagotti.github.io/melhorprecito-robos/midia"
DONOS_NUVEM = ["saida/telegram_postados.json", "saida/telegram_fila.json", "saida/telegram_stats.json", "saida/cupons.json",
               "saida/instagram.json", "saida/instagram_stories.json", "saida/instagram_comentarios.json",
               "saida/ads_melhorprecito.json", "saida/ads_melhorprecito_numeros.json", "saida/ig_token_renovado.json",
               "saida/cards/destaques.json", "saida/nuvem.json", "docs/midia"]


def git(*args, ok=False):
    r = subprocess.run(["git", *args], cwd=AQUI, capture_output=True, text=True)
    if r.returncode and not ok:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr[-400:]}")
    return r


def salvar(mensagem):
    """Commit do que a nuvem mudou e push (com rebase: o PC pode ter mandado plano novo no meio do turno)."""
    git("add", "-A", "--", *[d for d in DONOS_NUVEM if (AQUI / d).exists()])
    if not git("diff", "--cached", "--quiet", ok=True).returncode:
        return
    git("commit", "-q", "-m", mensagem)
    for _ in range(4):
        if git("pull", "-q", "--rebase", ok=True).returncode == 0 and git("push", "-q", ok=True).returncode == 0:
            return
        git("rebase", "--abort", ok=True)
        time.sleep(5)
    print("aviso: não consegui salvar no repositório agora; tento no próximo passo", flush=True)


def hospedar(arquivo, nome):
    """Imagem dos Stories no GitHub Pages deste repositório (a API do Instagram só aceita link público)."""
    MIDIA.mkdir(parents=True, exist_ok=True)
    shutil.copy(arquivo, MIDIA / nome)
    salvar(f"midia {nome}")
    url = f"{PAGES}/{nome}"
    for _ in range(40):
        time.sleep(15)
        r = requests.head(url, timeout=30)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith(("image", "video")):
            return url
    raise RuntimeError("GitHub Pages não publicou a imagem em 10 min")


def remover(nome):
    (MIDIA / nome).unlink(missing_ok=True)
    salvar(f"limpa {nome}")


def _passo(nome, funcao):
    try:
        funcao()
    except Exception:
        print(f"[{datetime.now():%H:%M}] ERRO em {nome}:\n{traceback.format_exc()[-1500:]}", flush=True)
    salvar(f"{nome} {datetime.now():%d/%m %H:%M}")


def turno(minutos=28):
    import ads_mp
    import comentarios_ig
    import cupons
    import instagram_bot
    import stories_ig
    import telegram_bot
    import telegram_fila
    from shopee_api import ShopeeAfiliados
    fim = time.time() + minutos * 60
    api = ShopeeAfiliados()
    ultimo = {}

    def de_tempo_em_tempo(nome, segundos, funcao):
        if time.time() - ultimo.get(nome, 0) >= segundos:
            ultimo[nome] = time.time()
            _passo(nome, funcao)

    while time.time() < fim:
        de_tempo_em_tempo("cupons-manuais", 300, cupons.importar_manuais)
        de_tempo_em_tempo("telegram-videos", 300, telegram_bot.postar)
        de_tempo_em_tempo("comentarios", 300, comentarios_ig.rodar)
        de_tempo_em_tempo("fila", 20, lambda: telegram_fila.tick(api))
        de_tempo_em_tempo("instagram", 900, lambda: (instagram_bot.precisa_renovar() and instagram_bot.renovar(),
                                                     instagram_bot.postar(), stories_ig.postar()))
        de_tempo_em_tempo("anuncio", 1800, ads_mp.monitorar)
        de_tempo_em_tempo("cupons-blog", 1800, cupons.vigiar_no_horario)
        time.sleep(15)


if __name__ == "__main__":
    print(f"turno começou {datetime.now():%d/%m %H:%M} (fuso {time.strftime('%Z')})", flush=True)
    turno(float(sys.argv[1]) if len(sys.argv) > 1 else 28)
    print(f"turno terminou {datetime.now():%H:%M}", flush=True)
