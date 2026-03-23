"""Testes para funções de deduplicação do db.py."""

import sys
import os
from unittest.mock import MagicMock

# Mock dependências externas antes de importar db
sys.modules["supabase"] = MagicMock()
sys.modules["dotenv"] = MagicMock()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db import _hash_licitacao, _hash_licitacao_texto


class TestHashLicitacao:
    def test_mesmo_input_mesmo_hash(self):
        h1 = _hash_licitacao("12345678000100", "2026", "1", "PNCP")
        h2 = _hash_licitacao("12345678000100", "2026", "1", "PNCP")
        assert h1 == h2

    def test_inputs_diferentes_hashes_diferentes(self):
        h1 = _hash_licitacao("12345678000100", "2026", "1", "PNCP")
        h2 = _hash_licitacao("12345678000100", "2026", "2", "PNCP")
        assert h1 != h2

    def test_fonte_diferente_hash_diferente(self):
        h1 = _hash_licitacao("12345678000100", "2026", "1", "PNCP")
        h2 = _hash_licitacao("12345678000100", "2026", "1", "TCE_RJ")
        assert h1 != h2

    def test_tamanho_hash(self):
        h = _hash_licitacao("12345678000100", "2026", "1", "PNCP")
        assert len(h) == 32


class TestHashLicitacaoTexto:
    def test_mesmo_input_mesmo_hash(self):
        h1 = _hash_licitacao_texto("Belo Horizonte", "Software de gestão", "2026-03-01", "QUERIDO_DIARIO")
        h2 = _hash_licitacao_texto("Belo Horizonte", "Software de gestão", "2026-03-01", "QUERIDO_DIARIO")
        assert h1 == h2

    def test_municipio_diferente_hash_diferente(self):
        h1 = _hash_licitacao_texto("Belo Horizonte", "Software", "2026-03-01", "PNCP")
        h2 = _hash_licitacao_texto("Juiz de Fora", "Software", "2026-03-01", "PNCP")
        assert h1 != h2

    def test_trunca_objeto_em_100_chars(self):
        obj_longo = "x" * 200
        h1 = _hash_licitacao_texto("BH", obj_longo, "2026-03-01", "PNCP")
        h2 = _hash_licitacao_texto("BH", obj_longo[:100] + "diferente", "2026-03-01", "PNCP")
        assert h1 == h2
