"""Importar este módulo faz todo programa aberto pelos robôs (npx, ffmpeg, ffprobe, git, tasklist...) rodar sem janela.

Os robôs rodam com pythonw (sem console); qualquer programa de linha de comando que eles chamam ganhava uma janela
preta própria, que piscava na tela do Lucas a cada poucos minutos.
"""
import subprocess
import sys

if sys.platform == "win32" and not getattr(subprocess.Popen, "_sem_janela", False):
    _original = subprocess.Popen.__init__

    def _init(self, *args, creationflags=0, **kwargs):
        _original(self, *args, creationflags=creationflags | subprocess.CREATE_NO_WINDOW, **kwargs)

    subprocess.Popen.__init__ = _init
    subprocess.Popen._sem_janela = True
