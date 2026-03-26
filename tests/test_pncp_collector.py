"""Testes unitários do pipeline de coleta PNCP v2."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from pncp_collector.constants import TipoFalha
from pncp_collector.services.payload_builder import montar_item_row, montar_resultado_row
from pncp_collector.services.pending import extrair_url_parts
from pncp_collector.services.persistence import persistir_itens_batch, persistir_resultados_batch
from pncp_collector.services.stats import StatsTracker
from pncp_collector.services.throttling import Throttler
from pncp_collector.services.validation import validar_item, validar_resultado
from pncp_collector.types import Metadata


# ── Validação de Itens ───────────────────────────────────────


class TestValidarItem:
    def test_item_valido(self):
        item = {"numeroItem": 1, "descricao": "Caneta", "quantidade": "10", "valorUnitarioEstimado": "5.50"}
        resultado = validar_item(item)
        assert resultado is not None
        assert resultado["numeroItem"] == 1
        assert resultado["quantidade"] == 10.0
        assert resultado["valorUnitarioEstimado"] == 5.50

    def test_sem_numero_item(self):
        item = {"descricao": "Caneta"}
        assert validar_item(item) is None

    def test_numero_item_zero(self):
        item = {"numeroItem": 0}
        assert validar_item(item) is None

    def test_numero_item_negativo(self):
        item = {"numeroItem": -1}
        assert validar_item(item) is None

    def test_numero_item_string_valida(self):
        item = {"numeroItem": "5"}
        resultado = validar_item(item)
        assert resultado is not None
        assert resultado["numeroItem"] == 5

    def test_numero_item_string_invalida(self):
        item = {"numeroItem": "abc"}
        assert validar_item(item) is None

    def test_strings_vazias_viram_none(self):
        item = {"numeroItem": 1, "descricao": "  ", "ncmNbsCodigo": ""}
        resultado = validar_item(item)
        assert resultado["descricao"] is None
        assert resultado["ncmNbsCodigo"] is None

    def test_quantidade_invalida(self):
        item = {"numeroItem": 1, "quantidade": "abc"}
        resultado = validar_item(item)
        assert resultado["quantidade"] is None


# ── Validação de Resultados ──────────────────────────────────


class TestValidarResultado:
    def test_resultado_valido(self):
        res = {"sequencialResultado": 1, "valorUnitarioHomologado": "100.50", "percentualDesconto": "15.5"}
        resultado = validar_resultado(res)
        assert resultado is not None
        assert resultado["sequencialResultado"] == 1
        assert resultado["valorUnitarioHomologado"] == 100.50
        assert resultado["percentualDesconto"] == 15.5

    def test_sem_sequencial(self):
        res = {"valorUnitarioHomologado": 100}
        assert validar_resultado(res) is None

    def test_valor_negativo(self):
        res = {"sequencialResultado": 1, "valorUnitarioHomologado": -10}
        assert validar_resultado(res) is None

    def test_valor_total_negativo(self):
        res = {"sequencialResultado": 1, "valorTotalHomologado": -5}
        assert validar_resultado(res) is None

    def test_strings_vazias_viram_none(self):
        res = {"sequencialResultado": 1, "niFornecedor": "  "}
        resultado = validar_resultado(res)
        assert resultado["niFornecedor"] is None


# ── Payload Builder ──────────────────────────────────────────


class TestPayloadBuilder:
    def test_montar_item_row(self):
        item = {"numeroItem": 1, "descricao": "Caneta", "ncmNbsCodigo": "123", "temResultado": True}
        metadata = Metadata(uf="MG", municipio="BH", codigo_ibge="310620",
                           modalidade_id=6, plataforma_id=121, plataforma_nome="SH3")
        row = montar_item_row("12345678000100", 2026, 1, "hash123", item, metadata)

        assert row["cnpj_orgao"] == "12345678000100"
        assert row["ano_compra"] == 2026
        assert row["numero_item"] == 1
        assert row["uf"] == "MG"
        assert row["plataforma_id"] == 121
        assert row["versao_coletor"] == "v2"
        assert row["coletado_em"] is not None

    def test_montar_resultado_row(self):
        res = {"sequencialResultado": 1, "valorUnitarioHomologado": 50, "niFornecedor": "99999"}
        row = montar_resultado_row("uuid-123", res)

        assert row["item_id"] == "uuid-123"
        assert row["sequencial_resultado"] == 1
        assert row["cnpj_fornecedor"] == "99999"
        assert row["versao_coletor"] == "v2"


# ── URL Parts ────────────────────────────────────────────────


class TestExtrairUrlParts:
    def test_url_compras(self):
        url = "https://pncp.gov.br/api/pncp/v1/orgaos/12345678000100/compras/2026/1"
        parts = extrair_url_parts(url)
        assert parts == ("12345678000100", "2026", "1")

    def test_url_editais(self):
        url = "https://pncp.gov.br/app/editais/12345678000100/2025/42"
        parts = extrair_url_parts(url)
        assert parts == ("12345678000100", "2025", "42")

    def test_url_invalida(self):
        assert extrair_url_parts("https://google.com") is None

    def test_url_vazia(self):
        assert extrair_url_parts("") is None

    def test_url_none(self):
        assert extrair_url_parts(None) is None


# ── Throttler ────────────────────────────────────────────────


class TestThrottler:
    def test_registrar_sucesso_reseta_delay(self):
        t = Throttler(delay_base=0)
        t.registrar_falha(TipoFalha.NETWORK)
        assert t.falhas_consecutivas == 1
        t.registrar_sucesso()
        assert t.falhas_consecutivas == 0

    def test_backoff_exponencial(self):
        t = Throttler(delay_base=0)
        t.registrar_falha(TipoFalha.TIMEOUT)
        d1 = t._delay_atual
        t.registrar_falha(TipoFalha.TIMEOUT)
        d2 = t._delay_atual
        assert d2 > d1

    def test_rate_limit_delay_alto(self):
        t = Throttler(delay_base=0)
        t.registrar_falha(TipoFalha.RATE_LIMIT)
        assert t._delay_atual == 30.0

    def test_deve_retry_retriable(self):
        t = Throttler()
        assert t.deve_retry(0, TipoFalha.NETWORK) is True
        assert t.deve_retry(0, TipoFalha.TIMEOUT) is True
        assert t.deve_retry(0, TipoFalha.RATE_LIMIT) is True

    def test_nao_retry_api_error(self):
        t = Throttler()
        assert t.deve_retry(0, TipoFalha.API) is False

    def test_nao_retry_apos_max(self):
        t = Throttler(max_retries=3)
        assert t.deve_retry(3, TipoFalha.NETWORK) is False


# ── StatsTracker ─────────────────────────────────────────────


class TestStatsTracker:
    def test_contadores_basicos(self):
        tracker = StatsTracker()
        tracker.registrar_licitacao()
        tracker.registrar_licitacao()
        tracker.registrar_itens_retornados(10)
        tracker.registrar_item_valido()
        tracker.registrar_item_descartado()
        tracker.registrar_itens_persistidos(5)
        tracker.registrar_resultados_persistidos(3)

        resumo = tracker.resumo()
        assert resumo.licitacoes_processadas == 2
        assert resumo.itens_retornados == 10
        assert resumo.itens_validos == 1
        assert resumo.itens_descartados == 1
        assert resumo.itens_persistidos == 5
        assert resumo.resultados_persistidos == 3

    def test_falhas_classificadas(self):
        tracker = StatsTracker()
        tracker.registrar_falha(TipoFalha.NETWORK, "timeout")
        tracker.registrar_falha(TipoFalha.NETWORK, "dns")
        tracker.registrar_falha(TipoFalha.PERSIST, "batch fail")

        resumo = tracker.resumo()
        assert resumo.falhas["network_error"] == 2
        assert resumo.falhas["persist_error"] == 1

    def test_run_id_unico(self):
        t1 = StatsTracker()
        t2 = StatsTracker()
        assert t1.resumo().run_id != t2.resumo().run_id

    def test_tempo_total(self):
        tracker = StatsTracker()
        resumo = tracker.resumo()
        assert resumo.tempo_total_ms >= 0


# ── Persistence (batch) ─────────────────────────────────────


class TestPersistenceBatch:
    def _mock_client(self, should_fail: bool = False):
        client = MagicMock()
        table = MagicMock()
        upsert = MagicMock()
        execute = MagicMock()

        if should_fail:
            execute.execute.side_effect = Exception("DB error")
            upsert.return_value = execute
        else:
            execute.execute.return_value = MagicMock(data=[])
            upsert.return_value = execute

        table.upsert.return_value = upsert
        client.table.return_value = table
        return client

    def test_batch_itens_sucesso(self):
        client = self._mock_client()
        itens = [{"cnpj_orgao": f"cnpj{i}", "numero_item": i} for i in range(5)]
        persistidos, falhas = persistir_itens_batch(client, itens, batch_size=3)
        assert persistidos == 5
        assert len(falhas) == 0
        # 2 batches: [3, 2]
        assert client.table.return_value.upsert.call_count == 2

    def test_batch_itens_falha(self):
        client = self._mock_client(should_fail=True)
        itens = [{"cnpj_orgao": "cnpj1"}]
        persistidos, falhas = persistir_itens_batch(client, itens)
        assert persistidos == 0
        assert len(falhas) == 1
        assert falhas[0][0] == TipoFalha.PERSIST

    def test_batch_resultados_sucesso(self):
        client = self._mock_client()
        resultados = [{"item_id": f"id{i}"} for i in range(10)]
        persistidos, falhas = persistir_resultados_batch(client, resultados, batch_size=5)
        assert persistidos == 10
        assert len(falhas) == 0

    def test_batch_vazio(self):
        client = self._mock_client()
        persistidos, falhas = persistir_itens_batch(client, [])
        assert persistidos == 0
        assert len(falhas) == 0
