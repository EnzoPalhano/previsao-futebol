"""Teste da saída de terminal: nome estrangeiro não pode derrubar o script.

O console do Windows usa cp1252, que não tem ``ß`` nem ``ș``. Sem este
tratamento, imprimir ``Preußen Münster`` interrompe o programa com
``UnicodeEncodeError`` — e interrompe depois de o trabalho todo estar feito.
"""

from __future__ import annotations

import io
import sys

from futebol import terminal


def test_saida_aceita_nome_estrangeiro(capsys) -> None:
    terminal.preparar_saida()
    print("Preußen Münster, Ham-Kam, Colón Santa Fe, Beşiktaş")
    assert "Preußen" in capsys.readouterr().out


def test_nao_quebra_quando_a_saida_nao_e_reconfiguravel(monkeypatch) -> None:
    """Em teste, a saída às vezes é um objeto sem `reconfigure`."""
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    terminal.preparar_saida()  # não pode levantar nada
