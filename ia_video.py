"""Foto do produto -> clipe de 6 s com IA paga (Segmind, Hailuo 2.3 Fast).

Uso: python ia_video.py <foto.jpg> "<prompt em inglês>" <saida.mp4>
A IA local (Wan 2.2 5B no ComfyUI) foi aposentada e apagada em 30/10: ficava ruim em roupa e inventava mão em objeto.
"""
import json
import sys
import time
from pathlib import Path

import requests

SEGMIND = "https://api.segmind.com/v1/hailuo-2.3-fast"
GASTOS = Path(__file__).parent / "saida" / "segmind.json"


def pago_disponivel():
    import os
    from shopee_api import carregar_env
    carregar_env()
    return bool(os.environ.get("SEGMIND_API_KEY"))


def gerar_clipe_pago(foto, prompt, saida):
    """IA paga (~US$ 0,24–0,39 o clipe). UMA tentativa só: se falhar, o vídeo sai no formato grátis."""
    import os
    from datetime import date
    from shopee_api import carregar_env
    import instagram_bot
    carregar_env()  # garante a SEGMIND_API_KEY mesmo quando chamado fora do fluxo da fábrica (ex.: refazer_sem_ia)
    nome = f"ia-{Path(saida).parent.parent.name}-{Path(saida).parent.name}.jpg"
    url = instagram_bot.hospedar(foto, nome)  # a API pede a foto por link público
    try:
        inicio = time.time()
        r = requests.post(SEGMIND, headers={"x-api-key": os.environ["SEGMIND_API_KEY"]}, timeout=900,
                          json={"first_frame_image": url, "prompt": prompt, "duration": 6, "resolution": "768p"})
        if r.status_code != 200:
            raise RuntimeError(f"Segmind HTTP {r.status_code}: {r.text[:300]}")
        if r.headers.get("content-type", "").startswith("video"):
            Path(saida).write_bytes(r.content)
        else:
            out = r.json().get("output") or r.json().get("video")
            Path(saida).write_bytes(requests.get(out[0] if isinstance(out, list) else out, timeout=120).content)
        g = json.loads(GASTOS.read_text(encoding="utf-8")) if GASTOS.exists() else {"clipes": 0, "dias": {}}
        g["clipes"] += 1
        g["dias"][date.today().isoformat()] = g["dias"].get(date.today().isoformat(), 0) + 1
        if r.headers.get("x-remaining-credits"):
            g["credito_restante"] = r.headers["x-remaining-credits"]
        GASTOS.write_text(json.dumps(g, indent=1), encoding="utf-8")
        return round(time.time() - inicio)
    finally:
        instagram_bot.limpar_hospedagem([nome])  # só a foto dele: no link público podem estar Reels esperando a hora


if __name__ == "__main__":
    print(f"pronto em {gerar_clipe_pago(sys.argv[1], sys.argv[2], sys.argv[3])}s")
