"""Robô do Instagram @melhor_precito: posta 3 Reels por dia (versão das redes, a que termina chamando pro Telegram da bio).

Uso: python instagram_bot.py postar        publica o que já passou do horário hoje (máx. 1 por vez)
     python instagram_bot.py teste         envia um vídeo e confere o processamento, SEM publicar
     python instagram_bot.py renovar       renova o token (dura 60 dias; a tarefa agendada renova sozinha)
Token: IG_ACCESS_TOKEN no .env; depois de renovado, fica em %LOCALAPPDATA%\\shopee-afiliados (fora da pasta servida pelo widget).
Envio do vídeo direto do PC (upload "resumable" da API), sem precisar hospedar o arquivo.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

import requests

import onedrive
from shopee_api import carregar_env

AQUI = Path(__file__).parent
API = "https://graph.instagram.com/v25.0"
ESTADO = AQUI / "saida" / "instagram.json"
COFRE = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "shopee-afiliados" / "ig_token.json"
MIDIAS = AQUI / "midias-ig"  # repositório público lucasfagotti/melhorprecito-midias (GitHub Pages)
PAGES = "https://lucasfagotti.github.io/melhorprecito-midias"
HORARIOS = ["09:00", "12:00", "15:00", "18:00", "21:00"]  # 5 Reels por dia (perfil de vendas)


def _marca(t):
    return hashlib.sha256(t.encode()).hexdigest()[:16]


def token():
    """Token renovado no cofre; mas se o Lucas colar um token NOVO no .env (ex.: com mais permissões), ele vale."""
    carregar_env()
    do_env = os.environ.get("IG_ACCESS_TOKEN", "")
    if COFRE.exists():
        cofre = json.loads(COFRE.read_text(encoding="utf-8"))
        if not do_env or cofre.get("origem") == _marca(do_env):
            return cofre["token"]
    if not do_env:
        raise SystemExit("Falta IG_ACCESS_TOKEN no .env")
    return do_env


def ig(metodo, caminho, **params):
    params["access_token"] = token()
    r = requests.request(metodo, f"{API}/{caminho}", params=params, timeout=120).json()
    if "error" in r:
        raise RuntimeError(f"{caminho}: {r['error'].get('message')}")
    return r


def minha_conta():
    return ig("GET", "me", fields="user_id,username")["user_id"]


def git(*args):
    subprocess.run(["git", "-c", "user.name=lucasfagotti", "-c", "user.email=lucasfagotti@users.noreply.github.com", *args],
                   cwd=MIDIAS, check=True, capture_output=True)


def hospedar(video, nome):
    """Com login do Instagram a API só aceita link público: o vídeo vai para o GitHub Pages até ser publicado."""
    shutil.copy(video, MIDIAS / nome)
    git("add", nome)
    try:
        git("commit", "-m", f"video {nome}")
    except subprocess.CalledProcessError:
        pass  # foto idêntica já estava no repositório: não há nada a commitar (re-tentativa do mesmo produto)
    git("push", "-q")
    url = f"{PAGES}/{nome}"
    for _ in range(40):  # o Pages leva ~1 min para publicar
        time.sleep(15)
        r = requests.head(url, timeout=30)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith(("video", "image")):
            return url
    raise RuntimeError("GitHub Pages não publicou o vídeo em 10 min")


def limpar_hospedagem(nomes=None):
    """Apaga do repositório de mídia os arquivos dados (ou todos). O Instagram guarda a cópia dele depois de publicar."""
    velhos = [p.name for p in list(MIDIAS.glob("*.mp4")) + list(MIDIAS.glob("*.jpg")) if nomes is None or p.name in nomes]
    if velhos:
        git("rm", "-q", *velhos)
        git("commit", "-m", "limpa vídeos publicados")
        git("push", "-q")


def enviar(video, legenda, nome="teste.mp4"):
    """Hospeda o vídeo, cria o contêiner do Reel e espera o Instagram processar. Devolve (conta, contêiner).
    Hospedar sobe só este arquivo; limpar_hospedagem apaga todos depois de publicar."""
    uid = minha_conta()
    url = hospedar(video, nome)
    c = ig("POST", f"{uid}/media", media_type="REELS", video_url=url, caption=legenda, share_to_feed="true")
    for _ in range(60):
        time.sleep(10)
        st = ig("GET", c["id"], fields="status_code,status")
        if st["status_code"] == "FINISHED":
            return uid, c["id"]
        if st["status_code"] == "ERROR":
            raise RuntimeError(f"processamento: {st.get('status')}")
    raise RuntimeError("Instagram demorou mais de 10 min para processar")


def enviar_url(url, legenda):
    """Cria o Reel a partir de um link público já pronto e espera o Instagram processar."""
    uid = minha_conta()
    c = ig("POST", f"{uid}/media", media_type="REELS", video_url=url, caption=legenda, share_to_feed="true")
    for _ in range(60):
        time.sleep(10)
        st = ig("GET", c["id"], fields="status_code,status")
        if st["status_code"] == "FINISHED":
            return uid, c["id"]
        if st["status_code"] == "ERROR":
            raise RuntimeError(f"processamento: {st.get('status')}")
    raise RuntimeError("Instagram demorou mais de 10 min para processar")


def sem_marca(texto):
    """Sem o nome "Shopee" (as regras do afiliado vetam usar a marca em anúncio pago, e qualquer Reel pode ser turbinado)."""
    texto = re.sub(r"\s*#\w*shopee\w*", "", texto, flags=re.I)
    texto = re.sub(r"\s*\b(na|da|do|no|pela|pelo|de)\s+shopee\b", "", texto, flags=re.I)
    return re.sub(r"\s*\bshopee\b", "", texto, flags=re.I)


def legenda_instagram(item):
    # no Instagram o link vai por direct a quem comentar (comentarios_ig.py); link em legenda não é clicável
    return sem_marca(f"{item['legenda']}\n\n💌 Comenta EU QUERO que eu te mando o link no direct!\n"
                     f"🔔 Achados todo dia no meu Telegram (link na bio)\n\n{item['hashtags']} #achadinhos #achadosdodia")


def link_instagram(item):
    """Link de afiliado com a marca "instagram", para o relatório mostrar o que veio daqui."""
    from shopee_api import ShopeeAfiliados
    api = ShopeeAfiliados()
    try:
        q = "query($id:Int64){productOfferV2(itemId:$id,limit:1){nodes{productLink}}}"
        produto = api.consultar(q, {"id": str(item["itemId"])})["productOfferV2"]["nodes"][0]["productLink"]
        return api.link_curto(produto, ["instagram", str(item["itemId"])])
    except Exception:
        return item.get("link_telegram") or item.get("link")


NA_NUVEM = bool(os.environ.get("GITHUB_ACTIONS"))
RENOVADO = AQUI / "saida" / "ig_token_renovado.json"  # só a data (o token em si fica nos Secrets do GitHub)
REPO_ROBOS = "lucasfagotti/melhorprecito-robos"


def nome_publico(dia, item):
    return f"{dia}-{item['itemId']}.mp4"


def publicar_aprovado(dia, n):
    """PC, no 👍 do widget: sobe o vídeo das redes para o link público, de onde o robô da nuvem posta no horário."""
    arq = AQUI / "saida" / "dias" / dia / "plano.json"
    item = next(i for i in json.loads(arq.read_text(encoding="utf-8"))["itens"] if i["n"] == n)
    url = hospedar(Path(item["video"]).parent / "video_redes.mp4", nome_publico(dia, item))
    plano = json.loads(arq.read_text(encoding="utf-8"))  # relê: a fábrica pode ter mexido enquanto subia
    for i in plano["itens"]:
        if i["n"] == n:
            i["video_publico"] = url
    arq.write_text(json.dumps(plano, ensure_ascii=False, indent=1), encoding="utf-8")
    return url


def limpar_publicados():
    """PC: tira do link público os vídeos que o robô da nuvem já postou."""
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    feitos = {nome_publico(dia, f) for dia, lista in estado.items() for f in lista}
    restos = [p.name for p in MIDIAS.glob("*.mp4") if p.name in feitos]
    if restos:
        limpar_hospedagem(restos)


def fila_de_hoje():
    """Os 3 vídeos de maior ganho do dia que já têm a versão das redes (mesma escolha da pasta 📱 do OneDrive)."""
    dia = date.today().isoformat()
    arq = AQUI / "saida" / "dias" / dia / "plano.json"
    if not arq.exists():
        return dia, []
    itens = json.loads(arq.read_text(encoding="utf-8"))["itens"]
    # só o que o Lucas aprovou (👍 no widget) depois do caso dos vídeos com mão inventada pela IA
    prontos = [i for i in itens if i.get("aprovado_ig") and not i.get("descartado") and i.get("video_publico")]
    return dia, sorted(prontos, key=lambda i: -i["ganho"])[:len(HORARIOS)]


def postar():
    estado = json.loads(ESTADO.read_text(encoding="utf-8")) if ESTADO.exists() else {}
    dia, fila = fila_de_hoje()
    feitos = estado.setdefault(dia, [])
    agora = datetime.now().strftime("%H:%M")
    for hora, item in zip(HORARIOS, fila):
        if item["itemId"] in [f["itemId"] for f in feitos] or hora > agora:
            continue
        uid, cid = enviar_url(item["video_publico"], legenda_instagram(item))  # vídeo já está no link público (subiu no 👍)
        pub = ig("POST", f"{uid}/media_publish", creation_id=cid)
        feitos.append({"itemId": item["itemId"], "curto": item["curto"], "hora": datetime.now().strftime("%H:%M"), "media": pub["id"],
                       "link": link_instagram(item)})
        ESTADO.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"instagram: publicado {item['curto']}", flush=True)
        return  # um por rodada


def renovar():
    r = requests.get(f"{API.rsplit('/', 1)[0]}/refresh_access_token",
                     params={"grant_type": "ig_refresh_token", "access_token": token()}, timeout=60).json()
    if "access_token" not in r:
        raise RuntimeError(f"renovação falhou: {r}")
    if NA_NUVEM:
        # na nuvem o token vive nos Secrets: grava o novo lá (gh + GH_PAT) e anota só a data no repositório
        subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", REPO_ROBOS, "--body", r["access_token"]],
                       check=True, capture_output=True, env={**os.environ, "GH_TOKEN": os.environ.get("GH_PAT", "")})
        os.environ["IG_ACCESS_TOKEN"] = r["access_token"]
        RENOVADO.write_text(json.dumps({"renovado": date.today().isoformat()}), encoding="utf-8")
    else:
        carregar_env()
        COFRE.parent.mkdir(parents=True, exist_ok=True)
        COFRE.write_text(json.dumps({"token": r["access_token"], "renovado": date.today().isoformat(),
                                     "origem": _marca(os.environ.get("IG_ACCESS_TOKEN", ""))}), encoding="utf-8")
    print("token renovado", flush=True)


def precisa_renovar():
    """Renova a cada 30 dias (o token vale 60)."""
    arq = RENOVADO if NA_NUVEM else COFRE
    if not arq.exists():
        return True
    return (date.today() - date.fromisoformat(json.loads(arq.read_text(encoding="utf-8"))["renovado"])).days >= 30


if __name__ == "__main__":
    acao = sys.argv[1] if len(sys.argv) > 1 else "postar"
    if acao == "teste":
        _, fila = fila_de_hoje()
        uid, cid = enviar(Path(fila[0]["video"]).parent / "video_redes.mp4", "teste (não publicado)")
        limpar_hospedagem()
        print(f"envio OK: contêiner {cid} processado e pronto; NÃO publicado")
    elif acao == "renovar":
        renovar()
    else:
        postar()
