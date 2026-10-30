"""Pasta do celular no OneDrive, montada a partir do plano do dia (pode rodar quantas vezes quiser).

OneDrive/Shopee Videos/
  2026-10-31 (sábado 31-10)/
    01 - 07h30 - Vestido Camponesa.mp4
    01 - 07h30 - Vestido Camponesa - LEGENDA.txt      produto e loja para marcar + legenda
    00 - TODAS AS LEGENDAS.txt
    ✅ Postados/                                       o widget move pra cá quando você clica em "Postei"
"""
import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).parent
RAIZ = Path.home() / "OneDrive" / "Shopee Videos"
SEMANA = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
POSTADOS = "✅ Postados"
# o Lucas trabalha o dia todo: posta em 2 blocos (antes do trabalho e no pico da noite), 1–2 min entre um vídeo e outro
HORARIOS = ["07:00"] * 4 + ["20:00"] * 6


def pasta_dia(dia):
    d = date.fromisoformat(dia)
    return RAIZ / f"{dia} ({SEMANA[d.weekday()]} {d:%d-%m})"


def bloco(horario):
    return "MANHÃ" if horario < "12:00" else "NOITE"


def nome_base(i):
    return re.sub(r'[\\/:*?"<>|]', "", f"{i['n']:02d} - {bloco(i['horario'])} - {i['curto'] or i['produto'][:40]}").strip()


def ficha(i):
    preco = f"{i['preco']:.2f}".replace(".", ",")
    return (f"{i['n']:02d} - BLOCO DA {bloco(i['horario'])} (a partir das {i['horario']}, 1–2 min entre um vídeo e outro)\n\nPRODUTO PARA MARCAR:\n{i['produto']}\n\nLOJA: {i['loja']}\n"
            f"PREÇO NO VÍDEO: R$ {preco}\n\nLEGENDA (copie tudo abaixo):\n{i['legenda']}\n\n{i['hashtags']}\n")


REDES = "📱 TikTok e Instagram"
POR_DIA_REDES = 5  # os de maior ganho por venda (mesmos 5 Reels que o robô posta no Instagram)


def legenda_redes(i):
    return f"{i['legenda']}\n\n🔗 O link está no meu canal do Telegram (link na bio)\n\n{i['hashtags']} #achadinhos #shopee"


def redes(plano, pasta):
    """Versão sem "produto marcado" (termina chamando pro Telegram da bio), para TikTok e Instagram."""
    destino = pasta / REDES
    prontos = [i for i in plano["itens"] if (Path(i["video"]).parent / "video_redes.mp4").exists()]
    escolhidos = sorted(prontos, key=lambda i: -i["ganho"])[:POR_DIA_REDES]
    if not escolhidos:
        return
    destino.mkdir(exist_ok=True)
    bases = [re.sub(r'[\\/:*?"<>|]', "", f"R{k} - {i['curto'] or i['produto'][:40]}").strip() for k, i in enumerate(escolhidos, 1)]
    validos = {f"{b}{ext}" for b in bases for ext in (".mp4", " - LEGENDA.txt")}
    for arq in destino.glob("*"):
        if arq.is_file() and arq.name not in validos:
            arq.unlink()  # ranking mudou com vídeo novo: tira o que saiu do top 3
    for base, i in zip(bases, escolhidos):
        if not (destino / f"{base}.mp4").exists():
            shutil.copy(Path(i["video"]).parent / "video_redes.mp4", destino / f"{base}.mp4")
        (destino / f"{base} - LEGENDA.txt").write_text(legenda_redes(i), encoding="utf-8")


CARDS = "🖼️ Cards (status do WhatsApp)"


def cards_do_dia(plano, pasta):
    """Card de oferta de cada produto do dia, pronto para o status do WhatsApp (com o link na legenda do status)."""
    import cards
    destino = pasta / CARDS
    destino.mkdir(exist_ok=True)
    linhas = []
    for i in plano["itens"]:
        base = re.sub(r'[\\/:*?"<>|]', "", f"{i['n']:02d} - {i['curto'] or i['produto'][:40]}").strip()
        alvo = destino / f"{base}.jpg"
        if not alvo.exists():
            try:
                shutil.copy(cards.card(cards.de_item(i), destino / f"_{base}.jpg", cards.cupom_ativo()), alvo)
                (destino / f"_{base}.jpg").unlink(missing_ok=True)
            except Exception:
                continue
        linhas.append(f"{base}\n{i['curto'] or i['produto'][:40]} 👉 {i['link_telegram']}\n")
    (destino / "00 - LINKS PARA O STATUS.txt").write_text("\n".join(linhas), encoding="utf-8")


def sincronizar(dia, com_cards=False):
    plano_arq = AQUI / "saida" / "dias" / dia / "plano.json"
    if not plano_arq.exists():
        return None
    plano = json.loads(plano_arq.read_text(encoding="utf-8"))
    # planos montados antes da troca para blocos ganham os horários novos
    if any(i["horario"] != HORARIOS[(i["n"] - 1) % len(HORARIOS)] for i in plano["itens"]):
        for i in plano["itens"]:
            i["horario"] = HORARIOS[(i["n"] - 1) % len(HORARIOS)]
        plano_arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    # vídeo reprovado (IA deformou o produto, mão aparecendo...) não vai para a pasta do celular
    plano["itens"] = [i for i in plano["itens"] if not i.get("descartado")]
    pasta = pasta_dia(dia)
    feitos = pasta / POSTADOS
    feitos.mkdir(parents=True, exist_ok=True)
    # tira arquivos com nome velho (ex.: horário mudou), para não ter vídeo repetido na pasta
    validos = {f"{nome_base(i)}{ext}" for i in plano["itens"] for ext in (".mp4", " - LEGENDA.txt")}
    for arq in list(pasta.glob("*")) + list(feitos.glob("*")):
        if arq.is_file() and arq.name not in validos and arq.name != "00 - TODAS AS LEGENDAS.txt":
            arq.unlink()
    for i in plano["itens"]:
        base = nome_base(i)
        destino, outro = (feitos, pasta) if i.get("shopee_postado") else (pasta, feitos)
        for ext, gerar in ((".mp4", None), (" - LEGENDA.txt", ficha)):
            alvo, velho = destino / f"{base}{ext}", outro / f"{base}{ext}"
            if velho.exists() and not alvo.exists():
                shutil.move(str(velho), str(alvo))
            elif not alvo.exists():
                if gerar:
                    alvo.write_text(gerar(i), encoding="utf-8")
                elif Path(i["video"]).exists():
                    shutil.copy(i["video"], alvo)
    redes(plano, pasta)
    if com_cards:  # gerar card é lento (baixa foto + IA dos selos): só a fábrica faz, o widget não espera por isso
        cards_do_dia(plano, pasta)
    (pasta / "00 - TODAS AS LEGENDAS.txt").write_text(
        f"{'-' * 40}\n".join(ficha(i) for i in plano["itens"]), encoding="utf-8")
    antiga = RAIZ / dia  # formato antigo (só a data)
    if antiga.exists():
        shutil.rmtree(antiga, ignore_errors=True)
    return pasta


if __name__ == "__main__":
    print(sincronizar(sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat(), com_cards=True))
