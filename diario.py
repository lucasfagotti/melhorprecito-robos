"""Fábrica diária: escolhe 10 produtos, escreve roteiro, gera clipes de IA, narra e monta os vídeos do dia.

Uso: python diario.py                  monta o dia de hoje
     python diario.py 2026-11-01       monta esse dia
     python diario.py --sem-ia         só foto animada (rápido, para testar)
Saída: saida/dias/<data>/plano.json (lido pelo widget) + vídeos em OneDrive/Shopee Videos/<data>/
"""
import sem_janela  # noqa: F401  (programas chamados pelos robôs abrem sem janela preta)
import asyncio
import json
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import edge_tts
import requests

import garimpo
import ia_video
import onedrive
from shopee_api import ShopeeAfiliados

AQUI = Path(__file__).parent
FABRICA = Path.home() / "produtos-digitais" / "videos"
HISTORICO = AQUI / "saida" / "historico.json"
sys.path.insert(0, str(Path.home() / "produtos-digitais" / "deepseek"))
from ds import chat  # noqa: E402

POR_DIA = 10
COTAS = {"roupas": 3, "calcados": 1, "acessorios": 1, "cozinha": 2, "casa": 2, "brinquedos": 1}
HORARIOS = onedrive.HORARIOS
VOZ = "pt-BR-ThalitaMultilingualNeural"  # voz feminina: o público é feminino (30/10, pedido do Lucas)
REPETIR_APOS_DIAS = 30
from regras import FORA_DO_DIARIO, MASCULINO, PROIBIDOS  # noqa: E402  (mesmos filtros dos robôs da nuvem)
# só roupa: a foto do anúncio quase sempre já tem modelo vestindo, e aí a IA fica boa (só dá movimento à pessoa).
# Em objeto a IA inventa mão/dedo (30/10: reborn, caminhão, saquinhos) -> esses viram foto parada com narração.
MODA_COM_MODELO = {"vestido", "conjunto feminino", "blusa feminina", "cropped", "saia feminina", "calca feminina", "legging",
                   "short feminino", "moda praia", "biquini", "fitness feminino", "pijama feminino", "lista-roupas"}

SISTEMA = """Você escreve roteiros curtos para vídeos de achadinhos no Shopee Vídeo, em português do Brasil, para um público feminino.
Quem narra é uma mulher, tom de amiga mostrando um achado: animado e natural.
Regras que você nunca quebra:
- O vídeo é sobre o PRODUTO: o que ele é, como é (modelo, cor, detalhe) e para que serve ou quando usar.
- Nunca fale de número de vendas, nota, estrelas ou "mais vendido", nem nas falas nem nos títulos.
- Só fale do que dá para saber pelo nome do produto. Não invente material, medida, tecnologia ou benefício.
- Nada de depoimento falso ("comprei", "uso todo dia", "minha mãe amou") e nada de promessa de resultado.
- Nunca diga "link na bio"; a chamada final é sempre tocar no produto marcado no vídeo.
- Nas falas, números por extenso (ex.: "setenta e quatro e noventa"); na legenda, nos títulos e no texto do Telegram, use algarismos (R$ 74,90).
- Cada fala tem no máximo 14 palavras; cada título na tela no máximo 5 palavras."""

PEDIDO = """Produto: {nome}
Preço: R$ {preco} | categoria: {categoria}

Devolva JSON com:
"curto": nome curto do produto (até 4 palavras),
"cenas": exatamente 5 itens, nesta ordem de tipo: gancho, info, info, preco, cta. Cada um com "tipo", "titulo" (texto na tela) e "fala" (o que a voz diz).
  O gancho já mostra o produto nos 2 primeiros segundos: o que ele é e o que tem de especial (ex.: "Esse vestido camponesa
  é a cara do verão"). As duas cenas info mostram detalhes reais do produto e quando usar. Na cena preco a fala diz o preço por extenso.
"legenda": legenda do post com 1 ou 2 emojis (até 150 caracteres),
"hashtags": 6 hashtags em uma linha,
"telegram": texto da oferta para canal do Telegram (até 3 linhas, com emoji, sem o link; termina chamando para clicar no botão "Ver na Shopee"),
"prompts_video": 2 prompts em INGLÊS para gerar clipes de 5 s a partir da foto do produto: {cena}. Peça sempre que o produto continue exatamente igual à foto."""


# vídeo pago (~R$ 1,35 o clipe): só onde UMA venda já paga o vídeo com folga e o produto já prova que vende
PAGO_MIN_GANHO = 15.0   # R$ por venda
PAGO_MIN_VENDAS = 300
PAGO_MIN_NOTA = 4.8
PAGO_POR_DIA = 3


def vale_pagar(ganho, vendas, nota, pasta_dia, categoria):
    # só ROUPA (a foto do anúncio tem modelo vestindo): em foto de catálogo de objeto a IA paga quase não mexe
    # (30/10: o Reborn saiu parado e o dinheiro foi jogado fora)
    ja_pagos = len(list(Path(pasta_dia).glob("*/clipe_pago.tentado")))  # conta o que já foi tentado hoje (sobrevive a reinício)
    return (categoria in MODA_COM_MODELO and float(ganho) >= PAGO_MIN_GANHO and int(vendas) >= PAGO_MIN_VENDAS
            and float(nota or 0) >= PAGO_MIN_NOTA and ja_pagos < PAGO_POR_DIA)


def foto_tela_cheia(pasta, imagem_url):
    """A IA mexe pouco quando recebe a foto com moldura desfocada (entende como "quadro"): manda a original em 9:16 cheio."""
    from PIL import Image, ImageOps
    destino = pasta / "foto_ia.jpg"
    if not destino.exists():
        original = Image.open(__import__("io").BytesIO(requests.get(imagem_url, timeout=60).content))
        # corta mais de baixo do que de cima: em foto de roupa a cabeça da modelo fica no topo
        ImageOps.fit(ImageOps.exif_transpose(original).convert("RGB"), (768, 1366), centering=(0.5, 0.3)).save(destino, quality=93)
    return destino


def clipe_pago(pasta, imagem_url, prompt, ganho, vendas, nota, categoria):
    """Uma chance por vídeo: marca como tentado ANTES de pagar, e nunca tenta de novo o mesmo produto."""
    arq, tentado = pasta / "clipe_pago.mp4", pasta / "clipe_pago.tentado"
    if not arq.exists() and not tentado.exists() and prompt and vale_pagar(ganho, vendas, nota, pasta.parent, categoria):
        tentado.touch()
        try:
            print("    clipe IA pago...", flush=True)
            ia_video.gerar_clipe_pago(str(foto_tela_cheia(pasta, imagem_url)), prompt, arq)
        except Exception as erro:
            print(f"    clipe pago falhou (vai no formato grátis): {erro}", flush=True)
    return arq if arq.exists() else None


def historico():
    return json.loads(HISTORICO.read_text(encoding="utf-8")) if HISTORICO.exists() else {}


def escolher(produtos, dia):
    usados = historico()
    hoje = datetime.fromisoformat(dia)
    livres = [p for p in produtos if not PROIBIDOS.search(p["productName"]) and p["palavra"] not in FORA_DO_DIARIO
              and not MASCULINO.search(p["productName"])
              and (str(p["itemId"]) not in usados
                   or (hoje - datetime.fromisoformat(usados[str(p["itemId"])])).days > REPETIR_APOS_DIAS)]
    escolhidos, por_categoria, por_grupo = [], {}, {}
    # cota por grupo (3 roupas, 1 calçado, 1 acessório, 2 cozinha, 2 casa, 1 brinquedo); dentro do grupo, os de melhor
    # oportunidade (já vêm ordenados), no máximo 1 por categoria para variar
    for p in livres:
        g = garimpo.GRUPO_DA.get(p["palavra"])
        if g and por_grupo.get(g, 0) < COTAS[g] and por_categoria.get(p["palavra"], 0) < 1:
            escolhidos.append(p)
            por_grupo[g] = por_grupo.get(g, 0) + 1
            por_categoria[p["palavra"]] = 1
    # se algum grupo não teve produto bom suficiente, completa com os melhores que sobraram
    for p in livres:
        if len(escolhidos) >= POR_DIA:
            break
        if p not in escolhidos:
            escolhidos.append(p)
    # intercala os grupos (roupa, calçado, acessório, cozinha, casa, brinquedo, roupa...) para o feed não repetir tipo
    filas = {g: [p for p in escolhidos if garimpo.GRUPO_DA.get(p["palavra"]) == g] for g in COTAS}
    ordem = []
    while any(filas.values()):
        for g in COTAS:
            if filas[g]:
                ordem.append(filas[g].pop(0))
    ordem += [p for p in escolhidos if p not in ordem]
    return ordem[:POR_DIA]


def roteiro(p):
    # roupa: movimento de verdade (a modelo anda e vira mostrando a peça); só roupa recebe vídeo pago, e com movimento sutil
    # demais o clipe parecia foto parada. Nada de mãos ou pessoas novas (a IA inventava mão em foto de objeto)
    cena = ("the model in the photo walks a few steps toward the camera and turns to show the outfit, fabric moving naturally, "
            "handheld phone camera following her, natural light; exactly the same clothes, no new people, no hands entering the frame"
            if p["palavra"] in MODA_COM_MODELO else
            "product only, exactly as in the photo, no hands, no people, no new objects; smooth slow camera orbit around the "
            "product, soft studio light")
    preco = f"{float(p['price']):.2f}".replace(".", ",")
    r = chat(PEDIDO.format(nome=p["productName"], preco=preco, categoria=p["palavra"], cena=cena), sistema=SISTEMA, json_saida=True)
    r["cenas"] = r["cenas"][:5]
    for c in r["cenas"]:
        if c["tipo"] == "preco":
            c["titulo"] = f"R$ {preco}"
    return r


async def _falar(texto, destino):
    palavras = []
    com = edge_tts.Communicate(texto, VOZ, rate="+8%", boundary="WordBoundary")
    with open(destino, "wb") as fh:
        async for parte in com.stream():
            if parte["type"] == "audio":
                fh.write(parte["data"])
            elif parte["type"] == "WordBoundary":
                palavras.append({"t": parte["text"], "ini": parte["offset"] / 1e7, "fim": (parte["offset"] + parte["duration"]) / 1e7})
    return palavras


def falar(texto, destino):
    """O serviço de voz às vezes não devolve áudio: tenta de novo e, em último caso, usa a outra voz feminina."""
    global VOZ
    for tentativa in range(4):
        try:
            return asyncio.run(_falar(texto, destino))
        except edge_tts.exceptions.NoAudioReceived:
            time.sleep(3 * (tentativa + 1))
            if tentativa == 2:
                VOZ = "pt-BR-FranciscaNeural"
    raise RuntimeError(f"voz não respondeu: {texto[:40]}")


def baixar_foto(url, destino):
    from PIL import Image, ImageOps
    destino.write_bytes(requests.get(url, timeout=60).content)
    img = ImageOps.exif_transpose(Image.open(destino)).convert("RGB")
    # foto quadrada do anúncio vira vertical com fundo desfocado (a IA trabalha melhor com 704x1280)
    from PIL import ImageFilter
    fundo = ImageOps.fit(img, (704, 1280)).filter(ImageFilter.GaussianBlur(30))
    frente = ImageOps.contain(img, (704, 1100))
    fundo.paste(frente, ((704 - frente.width) // 2, (1280 - frente.height) // 2))
    fundo.save(destino, quality=93)


def montar_fundo(cenas, foto, clipes):
    """O clipe pago abre o vídeo e corre direto, sem repetir trecho; quando acaba, entra a foto real.
    A cena de preço é sempre a foto real. Sem clipe: foto parada o vídeo todo."""
    fundo, fila = [], [list(c) + [0.0] for c in clipes]  # [src, duração, posição]
    for c in cenas:
        falta = c["dur"]
        while falta > 0.01:
            atual = next((x for x in fila if x[1] - 0.1 - x[2] > 0.3), None) if c["tipo"] != "preco" else None
            if not atual:
                fundo.append({"src": foto, "ini": 0, "dur": round(falta, 2)})
                break
            pedaco = min(falta, atual[1] - 0.1 - atual[2])
            fundo.append({"src": atual[0], "ini": round(atual[2], 2), "dur": round(pedaco, 2)})
            atual[2] += pedaco
            falta -= pedaco
    return fundo


CTA_REDES = {"titulo": "Link no Telegram da bio", "fala": "O link desse achado tá no meu canal do Telegram, na bio do perfil."}


def versao_redes(pasta, pub, pub_rel):
    """Mesmo vídeo para TikTok/Instagram: só troca o final (lá não tem produto marcado; o link fica no canal da bio)."""
    pasta = Path(pasta).resolve()
    destino = pasta / "video_redes.mp4"
    if destino.exists():
        return destino
    props = json.loads((pasta / "props.json").read_text(encoding="utf-8"))
    mp3 = pub / "cta_redes.mp3"
    palavras = falar(CTA_REDES["fala"], mp3)
    dur_antiga = props["cenas"][-1]["dur"]
    props["cenas"][-1] = {"tipo": "cta", "titulo": CTA_REDES["titulo"], "semSeta": True, "audio": f"{pub_rel}/cta_redes.mp3",
                          "palavras": palavras, "dur": round(palavras[-1]["fim"] + 0.3, 2)}
    sobra = round(props["cenas"][-1]["dur"] - dur_antiga, 2)
    if sobra > 0:  # final novo é mais longo: completa com a foto real (o clipe pode já ter acabado)
        props["fundo"].append({"src": f"{pub_rel}/foto.jpg", "ini": 0, "dur": sobra})
    else:
        props["fundo"][-1]["dur"] = max(0.1, round(props["fundo"][-1]["dur"] + sobra, 2))
    arq = pasta / "props_redes.json"
    arq.write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    subprocess.run(f'npx remotion render src/index.ts Achado "{destino}" --props="{arq}"', cwd=FABRICA, shell=True, check=True,
                   stdout=subprocess.DEVNULL)
    return destino


def narrar(rot, pub, pub_rel, desconto):
    """Voz de cada cena (com o tempo de cada palavra para a legenda)."""
    cenas = []
    for i, c in enumerate(rot["cenas"]):
        palavras = falar(c["fala"], pub / f"cena{i}.mp3")
        cenas.append({"tipo": c["tipo"], "titulo": c["titulo"], "audio": f"{pub_rel}/cena{i}.mp3", "palavras": palavras,
                      "dur": round(palavras[-1]["fim"] + 0.3, 2),
                      **({"desconto": desconto} if c["tipo"] == "preco" and desconto >= 10 else {})})
    return cenas


def refazer_narracao(dia, n):
    """Roteiro novo (sobre o produto, sem falar de vendas) e voz feminina num vídeo já pronto; reaproveita foto e clipe pago."""
    arq_plano = AQUI / "saida" / "dias" / dia / "plano.json"
    plano = json.loads(arq_plano.read_text(encoding="utf-8"))
    item = next(i for i in plano["itens"] if i["n"] == n)
    pasta = Path(item["video"]).parent
    pub_rel = f"afiliados/{dia}/{pasta.name}"
    pub = FABRICA / "public" / pub_rel
    rot = roteiro({"productName": item["produto"], "price": item["preco"], "palavra": item["categoria"]})
    (pasta / "roteiro.json").write_text(json.dumps(rot, ensure_ascii=False, indent=1), encoding="utf-8")
    cenas = narrar(rot, pub, pub_rel, item.get("desconto", 0))
    clipes = [(f"{pub_rel}/clipe_pago.mp4", duracao(pasta / "clipe_pago.mp4"))] if (pasta / "clipe_pago.mp4").exists() else []
    (pasta / "props.json").write_text(json.dumps({"cenas": cenas, "fundo": montar_fundo(cenas, f"{pub_rel}/foto.jpg", clipes)},
                                                 ensure_ascii=False), encoding="utf-8")
    for velho in ("video.mp4", "video_redes.mp4", "props_redes.json"):
        (pasta / velho).unlink(missing_ok=True)
    subprocess.run(f'npx remotion render src/index.ts Achado "{pasta / "video.mp4"}" --props="{pasta / "props.json"}"',
                   cwd=FABRICA, shell=True, check=True, stdout=subprocess.DEVNULL)
    versao_redes(pasta, pub, pub_rel)
    item.update(curto=rot.get("curto", item["curto"]), legenda=rot["legenda"], hashtags=rot["hashtags"],
                telegram_texto=rot["telegram"], clipes_ia=len(clipes))
    item.pop("aprovado_ig", None)  # vídeo mudou: precisa de um novo 👍
    arq_plano.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")


def refazer_sem_ia(dia, n):
    """Refaz um vídeo só com a foto parada + narração (para quando o clipe de IA saiu ruim). Reaproveita voz e roteiro."""
    arq = AQUI / "saida" / "dias" / dia / "plano.json"
    plano = json.loads(arq.read_text(encoding="utf-8"))
    item = next(i for i in plano["itens"] if i["n"] == n)
    pasta = Path(item["video"]).parent
    pub_rel = f"afiliados/{dia}/{pasta.name}"
    props = json.loads((pasta / "props.json").read_text(encoding="utf-8"))
    # se o produto vale a IA paga (e ainda não teve a chance dele), tenta uma vez; senão foto parada
    rot = json.loads((pasta / "roteiro.json").read_text(encoding="utf-8"))
    clipes = []
    pago = clipe_pago(pasta, item["imagem_url"], (rot.get("prompts_video") or [""])[0], item["ganho"], item["vendas"], item["nota"],
                      item["categoria"])
    if pago:
        shutil.copy(pago, FABRICA / "public" / pub_rel / pago.name)
        clipes.append((f"{pub_rel}/{pago.name}", duracao(pago)))
    props["fundo"] = montar_fundo(props["cenas"], f"{pub_rel}/foto.jpg", clipes)
    (pasta / "props.json").write_text(json.dumps(props, ensure_ascii=False), encoding="utf-8")
    for velho in ("video.mp4", "video_redes.mp4", "props_redes.json"):
        (pasta / velho).unlink(missing_ok=True)
    subprocess.run(f'npx remotion render src/index.ts Achado "{pasta / "video.mp4"}" --props="{pasta / "props.json"}"',
                   cwd=FABRICA, shell=True, check=True, stdout=subprocess.DEVNULL)
    versao_redes(pasta, FABRICA / "public" / pub_rel, pub_rel)
    item.pop("descartado", None)
    item["clipes_ia"] = len(clipes)
    salvar_plano(arq, plano)


def completar_redes(dia):
    """Gera a versão das redes dos vídeos que ainda não têm (dias montados antes dessa versão existir)."""
    plano = json.loads((AQUI / "saida" / "dias" / dia / "plano.json").read_text(encoding="utf-8"))
    for i in plano["itens"]:
        pasta = Path(i["video"]).parent
        if not (pasta / "video_redes.mp4").exists():
            pub_rel = f"afiliados/{dia}/{pasta.name}"
            versao_redes(pasta, FABRICA / "public" / pub_rel, pub_rel)


def duracao(arq):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(arq)],
                                capture_output=True, text=True, check=True).stdout)


def salvar_plano(plano_arq, plano):
    """Grava o plano sem apagar o que o robô do Telegram marcou (telegram_postado) enquanto a fábrica roda."""
    if plano_arq.exists():
        atual = json.loads(plano_arq.read_text(encoding="utf-8"))
        por_id = {str(i["itemId"]): i for i in atual.get("itens", [])}
        for i in plano["itens"]:
            antigo = por_id.get(str(i["itemId"]))
            if antigo and antigo.get("telegram_postado"):
                i["telegram_postado"] = True
                i["telegram_msg"] = antigo.get("telegram_msg")
                i["telegram_hora"] = antigo.get("telegram_hora")
    plano_arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")


def produzir(p, n, dia, pasta_dia, usar_ia, api):
    slug = f"{n:02d}"
    pasta = pasta_dia / slug
    pasta.mkdir(parents=True, exist_ok=True)
    pub_rel = f"afiliados/{dia}/{slug}"
    pub = FABRICA / "public" / pub_rel
    pub.mkdir(parents=True, exist_ok=True)

    rot_arq = pasta / "roteiro.json"
    rot = json.loads(rot_arq.read_text(encoding="utf-8")) if rot_arq.exists() else roteiro(p)
    rot_arq.write_text(json.dumps(rot, ensure_ascii=False, indent=1), encoding="utf-8")

    foto = pasta / "foto.jpg"
    if not foto.exists():
        baixar_foto(p["imageUrl"], foto)
    shutil.copy(foto, pub / "foto.jpg")

    clipes = []
    arq = clipe_pago(pasta, p["imageUrl"], (rot.get("prompts_video") or [""])[0], p["commission"], p["sales"], p["ratingStar"],
                     p["palavra"]) if usar_ia else None
    if arq:
        shutil.copy(arq, pub / arq.name)
        clipes.append((f"{pub_rel}/{arq.name}", duracao(arq)))

    desconto = int(p.get("priceDiscountRate") or 0)
    cenas = narrar(rot, pub, pub_rel, desconto)
    props = pasta / "props.json"
    props.write_text(json.dumps({"cenas": cenas, "fundo": montar_fundo(cenas, f"{pub_rel}/foto.jpg", clipes)}, ensure_ascii=False),
                     encoding="utf-8")
    video = pasta / "video.mp4"
    subprocess.run(f'npx remotion render src/index.ts Achado "{video}" --props="{props}"', cwd=FABRICA, shell=True, check=True,
                   stdout=subprocess.DEVNULL)
    versao_redes(pasta, pub, pub_rel)

    try:
        link_tg = api.link_curto(p["productLink"], ["telegram", str(p["itemId"])])
    except Exception:
        link_tg = p.get("offerLink") or p["productLink"]
    return {
        "n": n, "horario": HORARIOS[n - 1], "itemId": str(p["itemId"]), "produto": p["productName"], "curto": rot.get("curto", ""),
        "loja": p["shopName"], "preco": float(p["price"]), "desconto": desconto, "comissao_pct": round(float(p["commissionRate"]) * 100),
        "ganho": round(float(p["commission"]), 2), "vendas": int(p["sales"]), "nota": p["ratingStar"], "categoria": p["palavra"],
        "concorrencia": garimpo.concorrencia(p), "foto": str(foto), "video": str(video), "clipes_ia": len(clipes),
        "legenda": rot["legenda"], "hashtags": rot["hashtags"], "telegram_texto": rot["telegram"], "link": p.get("offerLink"),
        "link_telegram": link_tg, "imagem_url": p["imageUrl"], "shopee_postado": False, "telegram_postado": False,
    }


TRAVA = AQUI / "saida" / "fabrica.lock"


def ocupada():
    """Outra fábrica rodando? (a placa de vídeo só aguenta uma por vez)"""
    if not TRAVA.exists():
        return False
    pid = TRAVA.read_text().strip()
    vivo = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
    return pid in vivo


def main():
    if ocupada():
        print("outra fábrica já está rodando; saindo", flush=True)
        return
    TRAVA.write_text(str(__import__("os").getpid()))
    try:
        _main()
    finally:
        TRAVA.unlink(missing_ok=True)


def _main():
    global POR_DIA
    POR_DIA = next((int(a[4:]) for a in sys.argv if a.startswith("--n=")), POR_DIA)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dia = args[0] if args else date.today().isoformat()
    usar_ia = "--sem-ia" not in sys.argv and ia_video.pago_disponivel()
    pasta_dia = AQUI / "saida" / "dias" / dia
    pasta_dia.mkdir(parents=True, exist_ok=True)
    print(f"== {dia} | IA de vídeo: {'sim' if usar_ia else 'não'}", flush=True)

    produtos = garimpo.garimpar(garimpo.PALAVRAS)
    garimpo.salvar(produtos)
    escolhidos = escolher(produtos, dia)
    api = ShopeeAfiliados()
    plano_arq = pasta_dia / "plano.json"
    plano = json.loads(plano_arq.read_text(encoding="utf-8")) if plano_arq.exists() else {"dia": dia, "itens": []}
    feitos = {i["n"] for i in plano["itens"]}
    usados = historico()

    for n, p in enumerate(escolhidos, 1):
        if n in feitos:
            continue
        print(f"[{n}/{len(escolhidos)}] {p['productName'][:60]}", flush=True)
        inicio = time.time()
        try:
            item = produzir(p, n, dia, pasta_dia, usar_ia, api)
        except Exception as erro:
            print(f"    ERRO: {erro}", flush=True)
            continue
        plano["itens"].append(item)
        plano["itens"].sort(key=lambda i: i["n"])
        salvar_plano(plano_arq, plano)
        usados[item["itemId"]] = dia
        HISTORICO.write_text(json.dumps(usados, indent=1), encoding="utf-8")
        onedrive.sincronizar(dia)  # pasta do celular: OneDrive/Shopee Videos/<dia (semana dd-mm)>/
        print(f"    ok em {time.time() - inicio:.0f}s", flush=True)

    onedrive.sincronizar(dia, com_cards=True)
    try:
        import sincronizar
        sincronizar.sincronizar()  # manda o plano novo para os robôs da nuvem
    except Exception as erro:
        print(f"sincronização com a nuvem falhou (a tarefa de 5 em 5 min tenta de novo): {erro}", flush=True)
    print(f"DIA PRONTO: {len(plano['itens'])} vídeos", flush=True)


if __name__ == "__main__":
    main()
