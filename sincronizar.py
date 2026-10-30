"""PC <-> nuvem (a cada 5 min pelo Agendador, e no fim da fábrica).

Manda para o GitHub o que é do PC (plano do dia com as aprovações 👍, garimpo, cupons cadastrados no widget) e puxa o
que os robôs da nuvem fizeram (o que já foi postado, membros, comentários), para o widget mostrar.
Também tira do link público os Reels que a nuvem já publicou.
"""
import sem_janela  # noqa: F401
import subprocess
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).parent
DONOS_PC = ["saida/dias", "saida/garimpo.json", "saida/cupons_manuais.json", "saida/historico.json", "saida/segmind.json",
            "saida/resultados.json", "saida/telegram_config.json", "saida/convites.json", "widget/divulgacao.json"]


def git(*args, ok=False):
    r = subprocess.run(["git", "-c", "user.name=lucasfagotti", "-c", "user.email=lucasfagotti@users.noreply.github.com", *args],
                       cwd=AQUI, capture_output=True, text=True)
    if r.returncode and not ok:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr[-400:]}")
    return r


def sincronizar():
    from nuvem import DONOS_NUVEM
    # arquivo da nuvem mexido aqui no PC não vale: a versão da nuvem manda (evita conflito no pull)
    rastreados = git("ls-files", "--", *DONOS_NUVEM).stdout.split()
    if rastreados:
        git("checkout", "--", *rastreados, ok=True)
    git("add", "-A", "--", *[d for d in DONOS_PC if (AQUI / d).exists()])
    if git("diff", "--cached", "--quiet", ok=True).returncode:
        git("commit", "-q", "-m", f"PC {datetime.now():%d/%m %H:%M}")
    if git("pull", "-q", "--rebase", "--autostash", ok=True).returncode:
        git("rebase", "--abort", ok=True)
        raise RuntimeError("pull falhou (conflito); tento de novo na próxima rodada")
    git("push", "-q", ok=True)
    try:
        import instagram_bot
        instagram_bot.limpar_publicados()
    except Exception as erro:
        print(f"limpeza do link público: {erro}", flush=True)
    print(f"sincronizado {datetime.now():%H:%M}", flush=True)


if __name__ == "__main__":
    sincronizar()
