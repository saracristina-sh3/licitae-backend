"""
Scraper genérico para sites de prefeituras municipais.

Tenta múltiplas estratégias para encontrar a página de licitações:
1. Caminhos comuns (/licitacoes, /transparencia/licitacoes, etc.)
2. Busca por links com texto "licitação/licitações" na página inicial

Após encontrar a listagem, busca publicações em formato tabela ou cards.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from scrapers.portais.base import PortalScraper

log = logging.getLogger(__name__)

# Regex para detectar CMS "cadastro genérico" (obterPagina / paginarCadastroGenerico)
REGEX_CADGEN_ID = re.compile(r"paginarCadastroGenerico\(\s*(\d+)")
REGEX_PAGINA_ID = re.compile(r"/pagina/(\d+)")

# Caminhos comuns para páginas de licitação em sites de prefeituras
CAMINHOS_LICITACAO = [
    "/licitacoes",
    "/licitacao",
    "/transparencia/licitacoes",
    "/transparencia/licitacao",
    "/portal-transparencia/licitacoes",
    "/cidadao/licitacoes",
    "/servicos/licitacoes",
    "/editais",
    "/editais-e-licitacoes",
]

# Padrões regex para identificar links de licitação
REGEX_LINK_LICITACAO = re.compile(
    r"licita[çc][ãa]o|licita[çc][õo]es|editais|preg[ãa]o|tomada.+pre[çc]o|concorr[êe]ncia",
    re.IGNORECASE,
)

# Padrões para extrair modalidade do texto
MODALIDADES = {
    "pregão eletrônico": "Pregão Eletrônico",
    "pregão presencial": "Pregão Presencial",
    "pregao eletronico": "Pregão Eletrônico",
    "pregao presencial": "Pregão Presencial",
    "tomada de preço": "Tomada de Preços",
    "tomada de preco": "Tomada de Preços",
    "concorrência": "Concorrência",
    "concorrencia": "Concorrência",
    "convite": "Convite",
    "dispensa": "Dispensa de Licitação",
    "inexigibilidade": "Inexigibilidade",
    "leilão": "Leilão",
    "leilao": "Leilão",
    "chamamento público": "Chamamento Público",
    "chamamento publico": "Chamamento Público",
    "credenciamento": "Credenciamento",
}

# Regex para extrair número de processo
REGEX_PROCESSO = re.compile(
    r"(?:processo|proc|nº|n°|numero|número|pregão|pe|pp|tp|cc|dl)\s*[.:nº°-]*\s*(\d{1,4}[/.-]\d{2,4})",
    re.IGNORECASE,
)

# Regex para extrair datas no formato DD/MM/YYYY ou DD/MM/YY
REGEX_DATA = re.compile(r"\b(\d{2})/(\d{2})/(\d{2,4})\b")

# Regex para extrair valores monetários
REGEX_VALOR = re.compile(r"R\$\s*([\d.,]+)")


class PrefeituraGenericaScraper(PortalScraper):
    """Scraper genérico para sites de prefeituras municipais."""

    def buscar(self, data_inicial: str, data_final: str) -> list[dict]:
        data_ini = self._formatar_data(data_inicial)
        data_fim = self._formatar_data(data_final)

        # Se há URLs explícitas, usar diretamente (sem descoberta)
        if self.urls_licitacoes:
            publicacoes: list[dict] = []
            for url in self.urls_licitacoes:
                log.info("  %s: coletando URL direta → %s", self.municipio["nome"], url)
                publicacoes.extend(self._coletar_listagem(url, data_ini, data_fim))
            log.info("  %s: %d publicações encontradas", self.municipio["nome"], len(publicacoes))
            return publicacoes

        # Descoberta automática
        url_licitacoes = self._encontrar_pagina_licitacoes()
        if not url_licitacoes:
            log.info("  %s: página de licitações não encontrada", self.municipio["nome"])
            return []

        log.info("  %s: página encontrada → %s", self.municipio["nome"], url_licitacoes)

        publicacoes = self._coletar_listagem(url_licitacoes, data_ini, data_fim)
        log.info("  %s: %d publicações encontradas", self.municipio["nome"], len(publicacoes))

        return publicacoes

    def _encontrar_pagina_licitacoes(self) -> str | None:
        """Tenta encontrar a URL da página de licitações do portal."""
        # Estratégia 1: tentar caminhos conhecidos
        for caminho in CAMINHOS_LICITACAO:
            url = f"{self.url_base}{caminho}"
            try:
                resp = self.session.head(url, timeout=10, allow_redirects=True)
                if resp.status_code == 200:
                    return url
            except Exception:
                continue

        self._politeness_delay()

        # Estratégia 2: buscar links na página inicial
        soup = self._get_soup(self.url_base)
        if not soup:
            return None

        for link in soup.find_all("a", href=True):
            texto = link.get_text(strip=True).lower()
            href = link["href"]
            if REGEX_LINK_LICITACAO.search(texto) or REGEX_LINK_LICITACAO.search(href):
                return urljoin(self.url_base, href)

        return None

    def _coletar_listagem(
        self, url_listagem: str, data_ini: str, data_fim: str,
    ) -> list[dict]:
        """Coleta publicações de uma página de listagem de licitações."""
        # Tentar CMS cadgen via AJAX primeiro
        cadgen = self._coletar_cadgen(url_listagem, data_ini, data_fim)
        if cadgen is not None:
            return cadgen

        # Fallback: extração HTML estática
        resultados: list[dict] = []
        pagina = 1
        max_paginas = 5

        while pagina <= max_paginas:
            url = self._url_paginada(url_listagem, pagina)
            soup = self._get_soup(url)
            if not soup:
                break

            itens = self._extrair_itens(soup, url)
            if not itens:
                break

            novos = 0
            for item in itens:
                data_pub = item.get("data_publicacao", "")[:10]
                if data_pub and data_ini <= data_pub <= data_fim:
                    resultados.append(item)
                    novos += 1

            if novos == 0:
                break

            pagina += 1
            self._politeness_delay()

        return resultados

    def _coletar_cadgen(
        self, url_listagem: str, data_ini: str, data_fim: str,
    ) -> list[dict] | None:
        """
        Coleta via CMS 'cadastro genérico' (usado por muitos municípios de MG).
        Fluxo:
          1. GET /ws_consulta/Pagina.php?INT_PAG={id} → descobre INT_CAD_GEN
          2. POST /ws_consulta/Conteudo_Generico.php com INT_CAD_GEN → HTML
        Retorna None se a página não usa esse CMS.
        """
        match_pagina = REGEX_PAGINA_ID.search(url_listagem)
        if not match_pagina:
            return None

        pagina_id = match_pagina.group(1)
        base = url_listagem.split("/pagina/")[0]

        # Configurar Referer e cookie ANTES das requests
        self.session.headers.update({
            "Referer": url_listagem,
            "Origin": base,
        })
        self.session.cookies.set("INT_RPID", pagina_id)

        # Passo 1: Descobrir INT_CAD_GEN via Pagina.php
        cadgen_id = self._descobrir_cadgen_id(base, pagina_id)
        if not cadgen_id:
            return None

        log.info("  %s: CMS cadgen detectado (pagina=%s, cadgen=%s)",
                 self.municipio["nome"], pagina_id, cadgen_id)

        # Passo 2: Buscar conteúdo via POST
        import time as _time
        timestamp = str(int(_time.time() * 1000))
        ws_url = f"{base}/ws_consulta/Conteudo_Generico.php"

        resultados: list[dict] = []

        for pag in range(0, 5):
            if pag > 0:
                self._politeness_delay()

            resp_html = self._post_cadgen(ws_url, timestamp, cadgen_id, pag)
            if not resp_html:
                break

            soup_ajax = BeautifulSoup(resp_html, "html.parser")
            itens = self._extrair_de_cadgen(soup_ajax, url_listagem)
            if not itens:
                break

            novos = 0
            for item in itens:
                data_pub = item.get("data_publicacao", "")[:10]
                if data_pub and data_ini <= data_pub <= data_fim:
                    resultados.append(item)
                    novos += 1

            if novos == 0:
                break

        return resultados

    def _descobrir_cadgen_id(self, base_url: str, pagina_id: str) -> str | None:
        """
        Descobre o INT_CAD_GEN fazendo GET /ws_consulta/Pagina.php?INT_PAG={id}.
        A resposta contém: obterCadastroGenerico({cadgen_id}, false)
        """
        try:
            url = f"{base_url}/ws_consulta/Pagina.php?INT_PAG={pagina_id}"
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            match = re.search(r"(?:obterCadastroGenerico|buscarConteudoGenerico)\(\s*(\d+)", resp.text)
            if match:
                return match.group(1)
            log.info("  %s: Pagina.php respondeu mas sem cadgen_id (len=%d)",
                     self.municipio["nome"], len(resp.text))
            return None
        except Exception as e:
            log.warning("  %s: Falha ao acessar Pagina.php: %s", self.municipio["nome"], e)
            return None

    def _post_cadgen(
        self,
        ws_url: str,
        timestamp: str,
        cadgen_id: str,
        pag: int = 0,
    ) -> str | None:
        """Faz POST ao endpoint do CMS cadastro genérico."""
        try:
            data = {
                "INT_CAD_GEN": cadgen_id,
                "STR_BSC_CAD_GEN": "",
                "LG_ADM": "",
                "INT_PAG": str(pag) if pag > 0 else "undefined",
            }
            resp = self.session.post(
                f"{ws_url}?DataHora={timestamp}",
                data=data,
                timeout=30,
            )
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            log.warning("Erro ao buscar cadgen %s: %s", ws_url, e)
            return None

    def _url_paginada(self, url_base: str, pagina: int) -> str:
        """Adiciona parâmetro de paginação à URL."""
        if pagina == 1:
            return url_base
        sep = "&" if "?" in url_base else "?"
        return f"{url_base}{sep}pagina={pagina}"

    def _extrair_itens(self, soup: BeautifulSoup, url_pagina: str) -> list[dict]:
        """
        Extrai itens de licitação do HTML parseado.
        Tenta múltiplas estratégias: cadastro genérico, tabelas, cards/divs.
        """
        itens = self._extrair_de_cadgen(soup, url_pagina)
        if itens:
            return itens

        itens = self._extrair_de_tabela(soup, url_pagina)
        if itens:
            return itens

        itens = self._extrair_de_cards(soup, url_pagina)
        if itens:
            return itens

        return []

    def _extrair_de_cadgen(self, soup: BeautifulSoup, url_pagina: str) -> list[dict]:
        """
        Extrai licitações do layout 'cadastro genérico' (cadgen) usado por
        muitos municípios de MG. Estrutura: DIV#contenedor_registro_generico
        com spans .titulo_generico / .valor_generico.
        """
        containers = soup.find_all("div", id="contenedor_registro_generico")
        if not containers:
            return []

        resultados = []
        for container in containers:
            campos: dict[str, str] = {}
            for info in container.find_all("div", class_="informacao_generica"):
                titulo_el = info.find("span", class_="titulo_generico")
                valor_el = info.find("span", class_="valor_generico")
                if titulo_el and valor_el:
                    chave = titulo_el.get_text(strip=True).lower()
                    valor = valor_el.get_text(" ", strip=True)
                    campos[chave] = valor

            objeto = campos.get("objeto", "").strip()
            if not objeto:
                continue

            processo = campos.get("nº processo", "") or campos.get("nº proc", "")
            processo = processo.strip()

            modalidade_raw = campos.get("modalidade", "").strip()
            modalidade = self._detectar_modalidade(modalidade_raw) or modalidade_raw

            data_julg = campos.get("data de julgamento", "").strip()
            data_pub = self._parse_data(data_julg) if data_julg else ""

            situacao = campos.get("situação", "").strip() or "Publicada"

            # Extrair data dos anexos como fallback para data_publicacao
            data_anexo = ""
            for arq in container.find_all("span", id="datahora_arquivo_registro_generico"):
                txt = arq.get_text(strip=True)
                parsed = self._parse_data(txt)
                if parsed and (not data_anexo or parsed > data_anexo):
                    data_anexo = parsed

            # Usar data de julgamento se disponível, senão data do último anexo
            data_final = data_pub or data_anexo

            resultados.append({
                "objeto": objeto[:500],
                "modalidade": modalidade,
                "data_publicacao": f"{data_final}T00:00:00" if data_final else "",
                "data_abertura": f"{data_pub}T00:00:00" if data_pub else "",
                "data_encerramento": "",
                "valor_estimado": 0,
                "numero_processo": processo,
                "orgao": self.municipio["nome"],
                "cnpj": "",
                "situacao": situacao,
                "url_fonte": url_pagina,
                "exclusivo_me_epp": False,
            })

        return resultados

    def _extrair_de_tabela(self, soup: BeautifulSoup, url_pagina: str) -> list[dict]:
        """Extrai licitações de tabelas HTML."""
        resultados = []

        for table in soup.find_all("table"):
            rows = table.find_all("tr")
            if len(rows) < 2:
                continue

            # Detectar cabeçalhos
            header = rows[0]
            cols = [th.get_text(strip=True).lower() for th in header.find_all(["th", "td"])]

            if not any(
                termo in " ".join(cols)
                for termo in ["objeto", "licitação", "licitacao", "descrição", "descricao", "processo", "edital"]
            ):
                continue

            # Mapear colunas
            col_map = self._mapear_colunas(cols)

            for row in rows[1:]:
                cells = row.find_all(["td", "th"])
                if not cells:
                    continue

                item = self._row_to_item(cells, col_map, url_pagina)
                if item and item.get("objeto"):
                    resultados.append(item)

        return resultados

    def _extrair_de_cards(self, soup: BeautifulSoup, url_pagina: str) -> list[dict]:
        """Extrai licitações de elementos card/div."""
        resultados = []

        # Buscar containers que parecem cards de licitação
        containers = soup.find_all(
            ["div", "article", "li"],
            class_=re.compile(r"licit|edital|processo|card|item|post", re.IGNORECASE),
        )

        if not containers:
            # Tentar h2/h3 com texto de licitação como âncora
            for heading in soup.find_all(["h2", "h3", "h4", "a"]):
                texto = heading.get_text(strip=True)
                if REGEX_LINK_LICITACAO.search(texto) and len(texto) > 20:
                    item = self._texto_to_item(texto, url_pagina, heading)
                    if item:
                        resultados.append(item)

            return resultados

        for container in containers:
            texto_completo = container.get_text(" ", strip=True)
            if len(texto_completo) < 20:
                continue

            # Extrair link interno se houver
            link = container.find("a", href=True)
            url_item = urljoin(url_pagina, link["href"]) if link else url_pagina

            item = self._texto_to_item(texto_completo, url_item, container)
            if item and item.get("objeto"):
                resultados.append(item)

        return resultados

    def _mapear_colunas(self, cols: list[str]) -> dict[str, int]:
        """Mapeia nomes de colunas para índices."""
        mapa: dict[str, int] = {}

        for i, col in enumerate(cols):
            col_lower = col.lower()
            if any(t in col_lower for t in ["objeto", "descrição", "descricao"]):
                mapa["objeto"] = i
            elif any(t in col_lower for t in ["modalidade", "tipo"]):
                mapa["modalidade"] = i
            elif any(t in col_lower for t in ["processo", "número", "numero", "nº", "edital"]):
                mapa["processo"] = i
            elif any(t in col_lower for t in ["data", "publicação", "publicacao", "abertura"]):
                if "abertura" in col_lower:
                    mapa["data_abertura"] = i
                else:
                    mapa.setdefault("data", i)
            elif any(t in col_lower for t in ["valor", "estimado"]):
                mapa["valor"] = i
            elif any(t in col_lower for t in ["situação", "situacao", "status"]):
                mapa["situacao"] = i

        return mapa

    def _row_to_item(
        self, cells: list[Tag], col_map: dict[str, int], url_pagina: str,
    ) -> dict | None:
        """Converte uma linha de tabela em dict de licitação."""
        def cell_text(key: str) -> str:
            idx = col_map.get(key)
            if idx is not None and idx < len(cells):
                return cells[idx].get_text(strip=True)
            return ""

        objeto = cell_text("objeto")
        if not objeto:
            return None

        # Link dentro da célula do objeto
        link = cells[col_map["objeto"]].find("a", href=True) if "objeto" in col_map else None
        url_item = urljoin(url_pagina, link["href"]) if link else url_pagina

        data_raw = cell_text("data")
        data_pub = self._parse_data(data_raw) if data_raw else ""

        data_abertura_raw = cell_text("data_abertura")
        data_abertura = self._parse_data(data_abertura_raw) if data_abertura_raw else ""

        valor_raw = cell_text("valor")
        valor = self._parse_valor(valor_raw) if valor_raw else 0

        processo = cell_text("processo")
        if not processo:
            match = REGEX_PROCESSO.search(objeto)
            if match:
                processo = match.group(1)

        modalidade = cell_text("modalidade")
        if not modalidade:
            modalidade = self._detectar_modalidade(objeto)

        return {
            "objeto": objeto[:500],
            "modalidade": modalidade,
            "data_publicacao": f"{data_pub}T00:00:00" if data_pub else "",
            "data_abertura": f"{data_abertura}T00:00:00" if data_abertura else "",
            "data_encerramento": "",
            "valor_estimado": valor,
            "numero_processo": processo,
            "orgao": self.municipio["nome"],
            "cnpj": "",
            "situacao": cell_text("situacao") or "Publicada",
            "url_fonte": url_item,
            "exclusivo_me_epp": False,
        }

    def _texto_to_item(
        self, texto: str, url_item: str, element: Tag | None = None,
    ) -> dict | None:
        """Extrai informações de licitação de um bloco de texto livre."""
        if len(texto) < 20:
            return None

        # Extrair número do processo
        processo = ""
        match = REGEX_PROCESSO.search(texto)
        if match:
            processo = match.group(1)

        # Extrair data
        data_pub = ""
        match_data = REGEX_DATA.search(texto)
        if match_data:
            data_pub = self._parse_data(f"{match_data.group(1)}/{match_data.group(2)}/{match_data.group(3)}")

        # Extrair valor
        valor = 0
        match_valor = REGEX_VALOR.search(texto)
        if match_valor:
            valor = self._parse_valor(match_valor.group(0))

        # Detectar modalidade
        modalidade = self._detectar_modalidade(texto)

        # Link se disponível no elemento
        if element:
            link = element.find("a", href=True) if hasattr(element, "find") else None
            if link:
                url_item = urljoin(self.url_base, link["href"])

        return {
            "objeto": texto[:500],
            "modalidade": modalidade,
            "data_publicacao": f"{data_pub}T00:00:00" if data_pub else "",
            "data_abertura": "",
            "data_encerramento": "",
            "valor_estimado": valor,
            "numero_processo": processo,
            "orgao": self.municipio["nome"],
            "cnpj": "",
            "situacao": "Publicada",
            "url_fonte": url_item,
            "exclusivo_me_epp": False,
        }

    def _detectar_modalidade(self, texto: str) -> str:
        """Detecta modalidade de licitação no texto."""
        texto_lower = texto.lower()
        for chave, modalidade in MODALIDADES.items():
            if chave in texto_lower:
                return modalidade
        return ""

    def _parse_data(self, data_str: str) -> str:
        """Converte data DD/MM/YYYY ou DD/MM/YY para YYYY-MM-DD."""
        match = REGEX_DATA.search(data_str)
        if not match:
            return ""

        dia, mes, ano = match.group(1), match.group(2), match.group(3)
        if len(ano) == 2:
            ano = f"20{ano}" if int(ano) < 50 else f"19{ano}"

        try:
            datetime(int(ano), int(mes), int(dia))
            return f"{ano}-{mes}-{dia}"
        except ValueError:
            return ""

    def _parse_valor(self, valor_str: str) -> float:
        """Converte string de valor monetário para float."""
        try:
            limpo = valor_str.replace("R$", "").strip()
            limpo = limpo.replace(".", "").replace(",", ".")
            return float(limpo)
        except (ValueError, AttributeError):
            return 0
