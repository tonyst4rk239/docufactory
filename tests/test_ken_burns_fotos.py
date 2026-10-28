import re

import pytest

from src.ken_burns_fotos import MIN_VISIBLE, MOVIMIENTOS, ZOOM_MAX, cambio_visible, expr_zoompan, zoom_total


@pytest.mark.parametrize("mov", MOVIMIENTOS)
@pytest.mark.parametrize("corte_s", [3.0, 4.2, 5.6, 8.0])
def test_lo_visible_del_corte_se_mueve_lo_suficiente(mov, corte_s):
    # El clip dura corte + 1.5 s de margen; antes la amplitud fija dejaba ~4-9 % visible (parecía foto quieta).
    n, nv = round((corte_s + 1.5) * 30), round(corte_s * 30)
    assert cambio_visible(mov, n, nv) >= MIN_VISIBLE - 1e-9
    assert 1.0 < zoom_total(mov, n, nv) <= ZOOM_MAX


def test_amplitud_vieja_era_insuficiente():
    # zoom 1.00->1.14 repartido en 5.5 s mostrando 4 s: 10 % visible < 12 %
    assert 0.14 * (120 / 165) < MIN_VISIBLE


def test_expresion_zin_crece_desde_1():
    e = expr_zoompan("zin", 165, 1920, 1080, 120)
    a = float(re.search(r"z='1\.0\+([0-9.]+)\*", e).group(1))
    assert a * 120 / 165 >= MIN_VISIBLE - 1e-3
    assert "s=1920x1080" in e and "d=165" in e


def test_movimiento_desconocido():
    with pytest.raises(ValueError):
        zoom_total("girar", 100)
