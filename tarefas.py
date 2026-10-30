"""Ponto de entrada do Agendador do Windows (roda com pythonw, sem janela; a saída vai para saida/*.log).

pythonw tarefas.py fabrica    1h da manhã: monta os 10 vídeos do dia
pythonw tarefas.py telegram   a cada 10 min: publica no canal as ofertas que chegaram no horário
"""
import sem_janela  # noqa: F401  (programas chamados pelos robôs abrem sem janela preta)
import contextlib
import sys
import traceback
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).parent
sys.path.insert(0, str(AQUI))

acao = sys.argv[1] if len(sys.argv) > 1 else ""
log = AQUI / "saida" / {"fabrica": "diario.log", "cupons": "cupons.log", "instagram": "instagram.log",
                             "comentarios": "instagram.log", "sync": "sync.log"}.get(acao, "telegram.log")
log.parent.mkdir(exist_ok=True)
with open(log, "a", encoding="utf-8") as fh, contextlib.redirect_stdout(fh), contextlib.redirect_stderr(fh):
    print(f"--- {datetime.now():%d/%m %H:%M} {acao}", flush=True)
    try:
        if acao == "fabrica":
            import diario
            sys.argv = sys.argv[:1]  # o diario lê a data dos argumentos; aqui é sempre hoje
            diario.main()
        elif acao == "instagram":
            import instagram_bot
            if instagram_bot.precisa_renovar():
                instagram_bot.renovar()  # token vale 60 dias; renova a cada 30
            instagram_bot.postar()
            import stories_ig
            stories_ig.postar()
            import ads_mp
            ads_mp.monitorar()  # vigia do anúncio de R$ 6/dia: pausa se passar do mês ou se o seguidor sair caro
        elif acao == "sync":
            import sincronizar
            sincronizar.sincronizar()
        elif acao == "comentarios":
            import comentarios_ig
            comentarios_ig.rodar()
        elif acao == "cupons":
            import cupons
            cupons.vigiar()
        elif acao == "telegram":
            import telegram_bot
            import telegram_fila
            telegram_bot.postar()      # ofertas com vídeo, no horário de cada uma
            telegram_fila.rodar(9.5)   # fila contínua até a próxima rodada da tarefa (a cada 10 min)
    except SystemExit as fim:
        print(fim, flush=True)
    except Exception:
        traceback.print_exc()
