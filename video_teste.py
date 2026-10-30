"""Teste comparativo: foto do produto -> clipe com IA em vários modelos da Segmind.

Uso: python video_teste.py <nome> <url_da_foto> "<o que a pessoa faz com o produto>"
Salva em saida/teste/<nome>-<modelo>.mp4
"""
import os
import sys
import time
from pathlib import Path

import requests

from shopee_api import carregar_env

SAIDA = Path(__file__).parent / "saida" / "teste"
NEGATIVO = "deformed product, changed logo, extra fingers, text, watermark, blurry"

# Preço aproximado por clipe (página de pricing da Segmind, out/2026)
MODELOS = {
    "hailuo": ("hailuo-2.3-fast", 0.24, lambda img, p: {
        "first_frame_image": img, "prompt": p, "duration": 6, "resolution": "768p"}),
    "seedance": ("seedance-2.0-mini", 0.38, lambda img, p: {
        "first_frame_url": img, "prompt": p, "duration": 5, "resolution": "720p",
        "aspect_ratio": "9:16", "generate_audio": False}),
    "wan": ("wan2.6-i2v-flash", 0.31, lambda img, p: {
        "image": img, "prompt": p, "negative_prompt": NEGATIVO, "duration": 5,
        "resolution": "720P", "audio": False}),
}


def gerar(modelo, foto_url, prompt, destino):
    carregar_env()
    chave = os.environ.get("SEGMIND_API_KEY")
    if not chave:
        raise SystemExit("Falta SEGMIND_API_KEY no arquivo .env")
    slug, _, montar = MODELOS[modelo]
    inicio = time.time()
    resp = requests.post(f"https://api.segmind.com/v1/{slug}", json=montar(foto_url, prompt),
                         headers={"x-api-key": chave}, timeout=900)
    if resp.status_code != 200:
        raise RuntimeError(f"{slug}: HTTP {resp.status_code} {resp.text[:300]}")
    if resp.headers.get("content-type", "").startswith("video"):
        destino.write_bytes(resp.content)
    else:
        saida = resp.json().get("output") or resp.json().get("video")
        url = saida[0] if isinstance(saida, list) else saida
        destino.write_bytes(requests.get(url, timeout=120).content)
    restante = resp.headers.get("x-remaining-credits")
    print(f"  {modelo}: ok em {time.time() - inicio:.0f}s -> {destino.name}"
          + (f" | crédito restante: {restante}" if restante else ""))


if __name__ == "__main__":
    nome, foto_url, acao = sys.argv[1], sys.argv[2], sys.argv[3]
    modelos = sys.argv[4].split(",") if len(sys.argv) > 4 else ["hailuo", "seedance"]
    prompt = (f"Vertical smartphone video, natural light, a Brazilian person {acao}. "
              "The product stays exactly as in the image: same shape, colors and details. "
              "Smooth handheld camera, realistic, UGC style.")
    SAIDA.mkdir(parents=True, exist_ok=True)
    print(f"{nome}: custo estimado US$ {sum(MODELOS[m][1] for m in modelos):.2f}")
    for m in modelos:
        try:
            gerar(m, foto_url, prompt, SAIDA / f"{nome}-{m}.mp4")
        except Exception as erro:
            print(f"  {m}: FALHOU - {erro}")
