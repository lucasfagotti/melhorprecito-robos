"""Filtros de produto usados pela fábrica (PC) e pelos robôs da nuvem: módulo leve, sem dependências."""
import re

# nada de promessa de saúde/resultado em conteúdo de afiliado
PROIBIDOS = re.compile(r"clare|olheira|emagrec|melasma|lifting|anti.?idade|rugas|celulite|remedio|remédio|suplement|"
                       r"capilar.*cresc|cura|colágeno|colageno|tratamento|retin|acne|mancha|spot|pore|wrinkle|whiten|"
                       r"brighten|aging|serum|sérum|ampoule|booster|peeling", re.I)
# skincare e tratamento: promessa de resultado e concorrência altíssima entre afiliados (não estão mais no garimpo)
FORA_DO_DIARIO = {"skincare", "cabelo tratamento"}
MASCULINO = re.compile(r"\bmasculin|\bhomem\b|\bhomens\b", re.I)
