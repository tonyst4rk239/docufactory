import re
from types import SimpleNamespace

import src.subtitulos as sub


def _esc(i, txt, puesto=None, titulo=None):
    return SimpleNamespace(id=i, texto_pantalla=txt, puesto=puesto, puesto_titulo=titulo,
                           pose="neutral", host_lado="derecha", host_visible=True)


def _tarjetas(tmp_path, monkeypatch, escenas):
    guion = SimpleNamespace(escenas=escenas)
    monkeypatch.setattr(sub, "cargar_guion", lambda p: guion)
    monkeypatch.setattr(sub, "top_n_explicito", lambda g, t: 3)
    monkeypatch.setattr(sub, "asegurar_tarjetas_top", lambda g, top_n=None: None)
    p = SimpleNamespace(carpeta=tmp_path, datos={}, tema="x")
    ruta = sub.generar_tarjetas_ass(p, {e.id: 10.0 for e in escenas})
    lineas = [l for l in ruta.read_text("utf-8").splitlines() if l.startswith("Dialogue")]
    textos = [re.sub(r"\{[^}]*\}", "", l.rsplit(",,", 1)[1]).replace("\\N", " ") for l in lineas]
    return [" ".join(t.split()) for t in textos]


def test_fechas_dentro_de_un_puesto_no_son_tarjetas_top(tmp_path, monkeypatch):
    escenas = [
        _esc(1, "#3: EL VIAJE", 3, "EL VIAJE A LA CAPITAL"),
        _esc(2, "«HOTEL DE LEYENDAS» · 1 NOV – 10 DIC 2017", 3),
        _esc(3, "REGRESO: 17 DE JULIO DE 2018", 3),
        _esc(4, "#2: LA MISMA", 2, "LA MISMA"),
        _esc(5, "#1: LA ORIGINAL", 1, "LA ORIGINAL"),
    ]
    t = _tarjetas(tmp_path, monkeypatch, escenas)
    assert "TOP #3" in t[0]
    assert "TOP #" not in t[1] and "1 NOV – 10 DIC 2017" in t[1]
    assert "TOP #" not in t[2] and "17 DE JULIO" in t[2]
    assert "TOP #2" in t[3]
    assert "TOP #1" in t[4] and "LA ORIGINAL" in t[4]


def test_texto_que_arranca_con_numero_de_puesto_sigue_siendo_tarjeta(tmp_path, monkeypatch):
    t = _tarjetas(tmp_path, monkeypatch, [_esc(1, "TOP #4 - EL ESPEJO"), _esc(2, "#3: LA CASA")])
    assert "TOP #4" in t[0] and "EL ESPEJO" in t[0]
    assert "TOP #3" in t[1] and "LA CASA" in t[1]
