"""Conector da Shopee Afiliados Open API (Brasil, GraphQL)."""
import hashlib
import json
import os
import time
from pathlib import Path

import requests

ENDPOINT = "https://open-api.affiliate.shopee.com.br/graphql"

# sortType do productOfferV2
RELEVANCIA, MAIS_VENDIDOS, MAIOR_PRECO, MENOR_PRECO, MAIOR_COMISSAO = 1, 2, 3, 4, 5

CAMPOS_PRODUTO = """
  itemId productName shopName price priceMin priceMax priceDiscountRate
  sales ratingStar commissionRate sellerCommissionRate commission imageUrl productLink offerLink
  periodStartTime productCatIds
"""


def carregar_env(caminho=Path(__file__).parent / ".env"):
    if not caminho.exists():
        return
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip())


class ShopeeAfiliados:
    def __init__(self, app_id=None, secret=None):
        carregar_env()
        self.app_id = app_id or os.environ.get("SHOPEE_APP_ID", "")
        self.secret = secret or os.environ.get("SHOPEE_SECRET", "")
        if not self.app_id or not self.secret:
            raise SystemExit("Faltam SHOPEE_APP_ID e SHOPEE_SECRET no arquivo .env")

    def consultar(self, query, variables=None):
        corpo = json.dumps({"query": query, "variables": variables or {}}, separators=(",", ":"))
        ts = int(time.time())
        # Assinatura = SHA256(AppId + Timestamp + Payload + Secret); o payload tem que ser idêntico ao corpo enviado
        assinatura = hashlib.sha256(f"{self.app_id}{ts}{corpo}{self.secret}".encode()).hexdigest()
        cabecalho = {
            "Authorization": f"SHA256 Credential={self.app_id}, Timestamp={ts}, Signature={assinatura}",
            "Content-Type": "application/json",
        }
        resp = requests.post(ENDPOINT, data=corpo.encode(), headers=cabecalho, timeout=30)
        resp.raise_for_status()
        dados = resp.json()
        if dados.get("errors"):
            raise RuntimeError(json.dumps(dados["errors"], ensure_ascii=False))
        return dados["data"]

    def buscar_produtos(self, palavra=None, ordem=MAIS_VENDIDOS, pagina=1, limite=50, categoria=None):
        query = f"""query($keyword:String,$sortType:Int,$page:Int,$limit:Int,$productCatId:Int){{
          productOfferV2(keyword:$keyword,sortType:$sortType,page:$page,limit:$limit,productCatId:$productCatId){{
            nodes {{ {CAMPOS_PRODUTO} }}
            pageInfo {{ page limit hasNextPage }}
          }}
        }}"""
        variaveis = {"keyword": palavra, "sortType": ordem, "page": pagina, "limit": limite, "productCatId": categoria}
        return self.consultar(query, {k: v for k, v in variaveis.items() if v is not None})["productOfferV2"]

    def link_curto(self, url, sub_ids=None):
        query = """mutation($url:String!,$subIds:[String!]){
          generateShortLink(input:{originUrl:$url,subIds:$subIds}){ shortLink }
        }"""
        return self.consultar(query, {"url": url, "subIds": sub_ids or []})["generateShortLink"]["shortLink"]
