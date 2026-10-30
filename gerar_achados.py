"""Gera os vídeos do Shopee Vídeo a partir de videos.json + material/<pasta> (vídeo e foto reais do produto).

Uso: python gerar_achados.py            todos
     python gerar_achados.py <id> ...   só esses
Saída: saida/videos/<id>.mp4 e <id>.txt (legenda, hashtags e qual produto marcar)
Usa a fábrica de reels (produtos-digitais/videos): voz Lucas da ElevenLabs + composição "Achado" do Remotion.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageOps

AQUI = Path(__file__).parent
FABRICA = Path.home() / "produtos-digitais" / "videos"
PUBLIC = FABRICA / "public"
SAIDA = AQUI / "saida" / "videos"
FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")

sys.path.insert(0, str(FABRICA))
from gerar_video import VOZES, falar  # noqa: E402


def preparar_midia(pasta):
    """Normaliza o vídeo (1080x1920, 30 fps, sem áudio) e a foto (1080x1920) em public/achados/<pasta>/."""
    origem = AQUI / "material" / pasta
    destino = PUBLIC / "achados" / pasta
    destino.mkdir(parents=True, exist_ok=True)
    video = next(f for f in origem.iterdir() if f.suffix.lower() in (".mov", ".mp4"))
    foto = next(f for f in origem.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png"))
    clipe = destino / "clipe.mp4"
    if not clipe.exists():
        subprocess.run([FFMPEG, "-v", "error", "-y", "-i", str(video), "-an", "-vf",
                        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30",
                        "-c:v", "libx264", "-crf", "20", "-preset", "fast", str(clipe)], check=True)
    img = destino / "foto.jpg"
    if not img.exists():
        ImageOps.fit(ImageOps.exif_transpose(Image.open(foto)).convert("RGB"), (1080, 1920)).save(img, quality=92)
    dur = float(subprocess.run([FFPROBE, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(clipe)],
                               capture_output=True, text=True, check=True).stdout)
    return f"achados/{pasta}/clipe.mp4", f"achados/{pasta}/foto.jpg", dur


def montar_fundo(cenas, clipe, foto, dur_clipe, inicio, foto_na_cena):
    """Vídeo real corrido do começo ao fim (volta ao início quando acaba); a foto entra numa cena só."""
    fundo, pos, fim = [], inicio % dur_clipe, dur_clipe - 0.3
    for i, c in enumerate(cenas):
        if i == foto_na_cena:
            fundo.append({"src": foto, "ini": 0, "dur": c["dur"]})
            continue
        falta = c["dur"]
        while falta > 0.01:
            pedaco = min(falta, fim - pos)
            fundo.append({"src": clipe, "ini": round(pos, 2), "dur": round(pedaco, 2)})
            falta -= pedaco
            pos = pos + pedaco if pos + pedaco < fim - 0.05 else 0.0
    return fundo


def gerar(v):
    print(f"\n== {v['id']} ({v['loja']})", flush=True)
    clipe, foto, dur_clipe = preparar_midia(v["pasta"])
    pasta = PUBLIC / "achados" / v["id"]
    pasta.mkdir(parents=True, exist_ok=True)
    cenas = []
    for i, c in enumerate(v["cenas"]):
        mp3, cache = pasta / f"cena{i}.mp3", pasta / f"cena{i}.json"
        if cache.exists() and json.loads(cache.read_text(encoding="utf-8"))["fala"] == c["fala"]:
            palavras = json.loads(cache.read_text(encoding="utf-8"))["palavras"]
        else:
            print(f"  voz cena {i + 1}...", flush=True)
            palavras = falar(c["fala"], VOZES["lucas"], str(mp3))
            cache.write_text(json.dumps({"fala": c["fala"], "palavras": palavras}, ensure_ascii=False), encoding="utf-8")
        cenas.append({"tipo": c["tipo"], "titulo": c["titulo"], "audio": f"achados/{v['id']}/cena{i}.mp3",
                      "palavras": palavras, "dur": round(palavras[-1]["fim"] + 0.3, 2)})
    props = pasta / "props.json"
    props.write_text(json.dumps({"cenas": cenas, "fundo": montar_fundo(cenas, clipe, foto, dur_clipe, v["inicio"], v["foto_na_cena"])},
                                ensure_ascii=False), encoding="utf-8")
    SAIDA.mkdir(parents=True, exist_ok=True)
    saida = SAIDA / f"{v['id']}.mp4"
    print("  renderizando...", flush=True)
    subprocess.run(f'npx remotion render src/index.ts Achado "{saida}" --props="{props}"', cwd=FABRICA, shell=True, check=True,
                   stdout=subprocess.DEVNULL)
    (SAIDA / f"{v['id']}.txt").write_text(
        f"MARCAR: {v['produto']} - loja {v['loja']} ({v['preco']}, comissão {v['comissao']})\n"
        f"Link: {v['link']}\n\nLEGENDA:\n{v['legenda']}\n\n{v['hashtags']}\n", encoding="utf-8")
    print(f"  pronto: {saida}")


if __name__ == "__main__":
    todos = json.loads((AQUI / "videos.json").read_text(encoding="utf-8"))
    escolhidos = [v for v in todos if not sys.argv[1:] or v["id"] in sys.argv[1:]]
    for v in escolhidos:
        gerar(v)
