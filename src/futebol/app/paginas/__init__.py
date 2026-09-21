"""As telas do app, uma por arquivo.

Cada módulo expõe uma função ``mostrar()`` sem argumentos, que o
:mod:`futebol.app.streamlit_app` registra na navegação. Não há estado
compartilhado entre páginas além do cache de :mod:`futebol.app.dados` — o
Streamlit reexecuta o script a cada clique, e página que guarda estado escondido
é página que se comporta diferente na segunda visita.

⚠️ **Toda página que mostra probabilidade, odd ou valor esperado é obrigada a
exibir o aviso correspondente de :mod:`futebol.app.avisos`.** Não é praxe de
estilo: é o que separa este app de uma máquina de sugerir apostas ruins. Há um
teste (``tests/test_app.py``) que confere página por página.
"""
