"""Produz vídeos adiantados: monta os próximos N dias, um depois do outro (cada dia ~3 h na placa de vídeo).

Uso: python estoque.py 7     de amanhã até daqui a 7 dias
Espera a fábrica que estiver rodando terminar antes de começar cada dia. Dias já prontos são pulados.
"""
import sem_janela  # noqa: F401  (programas chamados pelos robôs abrem sem janela preta)
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import diario

AQUI = Path(__file__).parent

if __name__ == "__main__":
    dias = int(sys.argv[1]) if len(sys.argv) > 1 else 7
    for k in range(1, dias + 1):
        dia = (date.today() + timedelta(days=k)).isoformat()
        while diario.ocupada():
            time.sleep(60)
        print(f"### estoque: {dia}", flush=True)
        with open(AQUI / "saida" / "diario.log", "a", encoding="utf-8") as log:
            subprocess.run([sys.executable, "diario.py", dia], cwd=AQUI, stdout=log, stderr=subprocess.STDOUT,
                           env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    print("ESTOQUE PRONTO", flush=True)
