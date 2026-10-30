"""Central de Afiliados: widget da área de trabalho (pywebview) para acompanhar o Shopee Vídeo e o canal do Telegram.

Abas: Hoje (10 postagens com horário), Produtos (garimpo), Vídeos, Telegram, Divulgação, Resultados.
Os vídeos e fotos são servidos por um servidor local só de leitura (127.0.0.1), para o player funcionar.
"""
import ctypes
import functools
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date, datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote

import webview

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
import sem_janela  # noqa: E402,F401  (programas chamados sem janela preta)
import onedrive  # noqa: E402
from shopee_api import ShopeeAfiliados, carregar_env  # noqa: E402

PASTA = Path(__file__).resolve().parent
DIAS = RAIZ / "saida" / "dias"
ESTADO = PASTA / "estado.json"
DIVULGACAO = PASTA / "divulgacao.json"
RESULTADOS = RAIZ / "saida" / "resultados.json"
W, H = 1060, 780


class Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        # só entrega a página do widget e as mídias de saida/; nunca .env, scripts ou arquivos ocultos
        caminho = unquote(self.path.split("?")[0])
        if not (caminho.startswith("/widget/") or caminho.startswith("/saida/")) or "/." in caminho or ".." in caminho:
            self.send_error(404)
            return
        super().do_GET()


def servidor():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Silencioso, directory=str(RAIZ)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def ler(arq, padrao):
    try:
        return json.loads(arq.read_text(encoding="utf-8"))
    except Exception:
        return padrao


def gravar(arq, dados):
    arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")


def url_local(caminho):
    try:
        return "/" + Path(caminho).resolve().relative_to(RAIZ).as_posix()
    except Exception:
        return ""


class Api:
    def __init__(self, porta):
        self._janela = None
        self._porta = porta
        self._api = None

    def _shopee(self):
        if not self._api:
            self._api = ShopeeAfiliados()
        return self._api

    # ---------- dados ----------
    def dados(self, dia=None):
        dia = dia or date.today().isoformat()
        try:
            onedrive.sincronizar(dia)  # mantém a pasta do celular em dia enquanto a fábrica trabalha
        except Exception:
            pass
        self._completar_redes(dia)
        plano = ler(DIAS / dia / "plano.json", {"dia": dia, "itens": []})
        plano["itens"] = [i for i in plano["itens"] if not i.get("descartado")]
        for i in plano["itens"]:
            i["video_url"] = url_local(i["video"])
            i["foto_url"] = url_local(i["foto"])
        dias = sorted([d.name for d in DIAS.iterdir() if (d / "plano.json").exists()], reverse=True) if DIAS.exists() else []
        carregar_env()
        stats = ler(RAIZ / "saida" / "telegram_stats.json", {})
        return {
            "base": f"http://127.0.0.1:{self._porta}", "hoje": date.today().isoformat(), "agora": datetime.now().strftime("%H:%M"),
            "plano": plano, "dias": dias,
            "garimpo": ler(RAIZ / "saida" / "garimpo.json", {"quando": "", "produtos": []}),
            "telegram": {"canal": os.environ.get("TELEGRAM_CANAL", ""), "configurado": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
                         "membros": stats},
            "divulgacao": ler(DIVULGACAO, {"tarefas": []}),
            "resultados": ler(RESULTADOS, {}),
            "cupons": ler(RAIZ / "saida" / "cupons.json", {"cupons": []})["cupons"],
            "fabrica": self._fabrica(),
            "estado": ler(ESTADO, {}),
        }

    def _completar_redes(self, dia):
        """Dias montados antes da versão das redes: gera as que faltam em segundo plano (só renderiza, sem IA)."""
        if getattr(self, "_redes_rodando", False):
            return
        import diario
        if diario.ocupada():  # a fábrica gera a versão das redes dela; mexer junto corrompe o áudio
            return
        plano = ler(DIAS / dia / "plano.json", {"itens": []})
        if all((Path(i["video"]).parent / "video_redes.mp4").exists() for i in plano["itens"]):
            return

        def trabalho():
            self._redes_rodando = True
            try:
                import diario
                diario.completar_redes(dia)
                onedrive.sincronizar(dia)
            except Exception:
                pass
            finally:
                self._redes_rodando = False
        threading.Thread(target=trabalho, daemon=True).start()

    def _fabrica(self):
        log = RAIZ / "saida" / "diario.log"
        if not log.exists():
            return {"status": "nunca rodou"}
        linhas = log.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
        return {"status": linhas[-1] if linhas else "", "quando": datetime.fromtimestamp(log.stat().st_mtime).strftime("%d/%m %H:%M")}

    # ---------- ações ----------
    def marcar(self, dia, n, campo, valor):
        arq = DIAS / dia / "plano.json"
        plano = ler(arq, None)
        for i in plano["itens"]:
            if i["n"] == n:
                i[campo] = valor
                if campo == "shopee_postado" and valor:
                    i["shopee_hora"] = datetime.now().strftime("%H:%M")
        gravar(arq, plano)
        onedrive.sincronizar(dia)  # move o vídeo para "✅ Postados" (ou de volta)
        return True

    def avaliar(self, dia, n, bom):
        """👍 libera o vídeo para o robô do Instagram; 👎 tira o vídeo da pasta do celular e de tudo."""
        arq = DIAS / dia / "plano.json"
        plano = ler(arq, None)
        for i in plano["itens"]:
            if i["n"] == n:
                if bom:
                    i["aprovado_ig"] = True
                else:
                    i["descartado"] = "reprovado no widget"
        gravar(arq, plano)
        onedrive.sincronizar(dia)
        return True

    def tarefa(self, idx, feito):
        d = ler(DIVULGACAO, {"tarefas": []})
        d["tarefas"][idx]["feito"] = feito
        gravar(DIVULGACAO, d)
        return True

    def abrir(self, alvo):
        os.startfile(alvo if alvo.startswith("http") else str(Path(alvo)))
        return True

    def pasta_celular(self, dia):
        p = onedrive.sincronizar(dia) or onedrive.RAIZ
        os.startfile(str(p))
        return True

    def conferir_preco(self, dia, n):
        """Compara o preço de agora com o do vídeo; se mudou, o vídeo precisa ser refeito."""
        arq = DIAS / dia / "plano.json"
        plano = ler(arq, None)
        item = next(i for i in plano["itens"] if i["n"] == n)
        q = "query($id:Int64){productOfferV2(itemId:$id,limit:1){nodes{price commission commissionRate}}}"
        nodes = self._shopee().consultar(q, {"id": str(item["itemId"])})["productOfferV2"]["nodes"]
        if not nodes:
            item["preco_check"] = {"quando": datetime.now().strftime("%H:%M"), "ok": False, "msg": "produto saiu da oferta"}
        else:
            agora = float(nodes[0]["price"])
            ok = abs(agora - item["preco"]) < 0.01
            item["preco_check"] = {"quando": datetime.now().strftime("%H:%M"), "ok": ok, "agora": agora,
                                   "msg": "preço igual ao vídeo" if ok else f"mudou para R$ {agora:.2f}".replace(".", ",")}
        gravar(arq, plano)
        return item["preco_check"]

    def telegram_agora(self, dia, n):
        r = subprocess.run([sys.executable, str(RAIZ / "telegram_bot.py"), "agora", dia, str(n)], cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8")
        return {"ok": r.returncode == 0, "msg": (r.stdout or r.stderr).strip()[-300:]}

    def telegram_teste(self):
        r = subprocess.run([sys.executable, str(RAIZ / "telegram_bot.py"), "teste"], cwd=RAIZ,
                           capture_output=True, text=True, encoding="utf-8")
        return {"ok": r.returncode == 0, "msg": (r.stdout or r.stderr).strip()[-400:]}

    # ---------- cupons ----------
    def cupom_add(self, codigo, desconto, regra, validade):
        import cupons
        c = cupons.adicionar(codigo, regra, validade, desconto)
        return self.cupom_postar(c["id"])

    def cupom_postar(self, cid):
        import cupons
        try:
            cupons.postar(cid)
            return {"ok": True}
        except Exception as erro:
            return {"ok": False, "msg": str(erro)[:300]}

    def cupom_descartar(self, cid):
        import cupons
        cupons.descartar(cid)
        return True

    def cupom_vigiar(self):
        import cupons
        try:
            return {"ok": True, "novos": cupons.vigiar()}
        except Exception as erro:
            return {"ok": False, "msg": str(erro)[:300]}

    def rodar_fabrica(self):
        subprocess.Popen(f'"{sys.executable}" diario.py >> saida\\diario.log 2>&1', cwd=RAIZ, shell=True,
                         creationflags=subprocess.CREATE_NO_WINDOW)
        return True

    def atualizar_resultados(self):
        """Comissões dos últimos 30 dias pelo relatório de conversões da API."""
        fim = int(time.time())
        ini = int((datetime.now() - timedelta(days=30)).timestamp())
        q = ("query($a:Int64,$b:Int64,$s:String){conversionReport(purchaseTimeStart:$a,purchaseTimeEnd:$b,limit:500,scrollId:$s)"
             "{nodes{purchaseTime totalCommission orders{orderStatus items{itemId itemName itemPrice qty itemTotalCommission}}}"
             " pageInfo{hasNextPage scrollId}}}")
        nodes, scroll = [], ""
        while True:
            # Int64 da API vai como texto
            r = self._shopee().consultar(q, {"a": str(ini), "b": str(fim), "s": scroll})["conversionReport"]
            nodes += r["nodes"]
            if not r["pageInfo"]["hasNextPage"]:
                break
            scroll = r["pageInfo"]["scrollId"]
        hoje = date.today()
        tot = {"hoje": 0.0, "7d": 0.0, "30d": 0.0}
        pedidos = {"hoje": 0, "7d": 0, "30d": 0}
        por_produto, por_dia = {}, {}
        for nd in nodes:
            d = datetime.fromtimestamp(int(nd["purchaseTime"])).date()
            c = float(nd.get("totalCommission") or 0)
            for chave, dias in (("hoje", 0), ("7d", 6), ("30d", 29)):
                if (hoje - d).days <= dias:
                    tot[chave] += c
                    pedidos[chave] += 1
            por_dia[d.isoformat()] = por_dia.get(d.isoformat(), 0) + c
            for o in nd.get("orders") or []:
                for it in o.get("items") or []:
                    k = it["itemName"][:60]
                    por_produto.setdefault(k, {"nome": k, "qtd": 0, "comissao": 0.0})
                    por_produto[k]["qtd"] += int(it.get("qty") or 1)
                    por_produto[k]["comissao"] += float(it.get("itemTotalCommission") or 0)
        res = {"quando": datetime.now().strftime("%d/%m %H:%M"), "total": tot, "pedidos": pedidos, "por_dia": por_dia,
               "top": sorted(por_produto.values(), key=lambda x: -x["comissao"])[:10]}
        gravar(RESULTADOS, res)
        return res

    def fixar(self):
        e = ler(ESTADO, {})
        e["topo"] = not e.get("topo", False)
        gravar(ESTADO, e)
        self._janela.on_top = e["topo"]
        return e["topo"]

    def minimizar(self):
        self._janela.minimize()

    def fechar(self):
        self._janela.destroy()


def cantos_arredondados(janela):
    try:  # Windows 11: cantos arredondados
        hwnd = janela.native.Handle.ToInt32()
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(2)), 4)
    except Exception:
        pass


def salvar_posicao(x, y):
    if x <= -10000 or y <= -10000:  # janela minimizada: o Windows informa -32000 (salvar isso faz abrir fora da tela)
        return
    e = ler(ESTADO, {})
    e["pos"] = [x, y]
    gravar(ESTADO, e)


if __name__ == "__main__":
    porta = servidor()
    e = ler(ESTADO, {})
    api = Api(porta)
    x, y = e.get("pos", [80, 40])
    larg, alt = ctypes.windll.user32.GetSystemMetrics(78), ctypes.windll.user32.GetSystemMetrics(79)  # área de todos os monitores
    if not (-200 < x < larg - 200 and -50 < y < alt - 100):
        x, y = 80, 40
    janela = webview.create_window("Central de Afiliados", f"http://127.0.0.1:{porta}/widget/index.html", js_api=api,
                                   width=W, height=H, x=x, y=y, frameless=True, easy_drag=False, resizable=True,
                                   on_top=e.get("topo", False), background_color="#0F1623", shadow=True, min_size=(860, 600))
    api._janela = janela
    janela.events.shown += lambda: cantos_arredondados(janela)
    janela.events.moved += salvar_posicao
    webview.start(private_mode=True)
