"""Cliente mínimo da API da DeepSeek. A chave vem da variável de ambiente DEEPSEEK_API_KEY (nunca do código)."""
import os, json, time
import requests

URL = "https://api.deepseek.com/chat/completions"
MODELO = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

CONTEXTO = """Você escreve em português do Brasil, direto e sem enrolação, para a marca @loja_quelucra,
que vende produtos digitais para lojistas de marketplace (Shopee, Mercado Livre, TikTok Shop) e lojas físicas.
Regras de negócio que você sempre respeita:
- Markup PADRÃO 3x sobre o custo; MÍNIMO 2,5x só em promoção ou produto parado; abaixo disso não vende.
  Escreva sempre "markup padrão de 3x" e "mínimo de 2,5x" (nunca "mínimo de 3x").
- Produto pago parado em estoque é prejuízo.
- Taxa Shopee (desde 01/10/2026): 20% + R$ 4,50 por item até R$ 79,99 (abaixo de R$ 9, taxa fixa = 50% do preço);
  14% + R$ 16 (R$ 80-99,99), 14% + R$ 20 (R$ 100-199,99), 14% + R$ 26 (R$ 200+). Zona ruim: R$ 80,00-87,69.
- Nunca prometa faturamento garantido, nunca invente números de clientes ou depoimentos.
Produtos (palavra-chave do ManyChat entre parênteses):
1. Kit Vendedor Shopee 2026: calculadora de markup e lucro + guia de 27 páginas (KIT) R$ 37
2. Auto-Consultoria Shopee: guia + planilha, nota de 0 a 10 em 9 áreas (AUDITORIA) R$ 47
3. Kit Gestão Financeira: planilha de 11 abas com DRE e ponto de equilíbrio (CAIXA) R$ 37
4. Pack 36 Posts Canva para lojas de moda e calçados + 36 legendas (POSTS) R$ 27
5. Auditoria Personalizada por PDF, sem reunião (RELATORIO) R$ 197
6. Combo Lojista Completo, produtos 1 a 4 (COMBO) R$ 127"""


def chat(pedido, sistema=CONTEXTO, json_saida=False, temperatura=0.7, tentativas=3):
    chave = os.getenv("DEEPSEEK_API_KEY")
    if not chave:
        raise SystemExit("Defina a chave: no PowerShell, rode  setx DEEPSEEK_API_KEY \"sua-chave\"  e abra um terminal novo.")
    corpo = {"model": MODELO, "temperature": temperatura,
             "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": pedido}]}
    if json_saida:
        corpo["response_format"] = {"type": "json_object"}
    for t in range(tentativas):
        try:
            r = requests.post(URL, headers={"Authorization": f"Bearer {chave}"}, json=corpo, timeout=180)
            r.raise_for_status()
            txt = r.json()["choices"][0]["message"]["content"]
            return json.loads(txt) if json_saida else txt
        except (requests.RequestException, json.JSONDecodeError, KeyError) as e:
            if t == tentativas - 1:
                raise
            time.sleep(3 * (t + 1))
