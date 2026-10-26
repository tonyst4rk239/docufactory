import pytest

from src.publicacion import (
    ENCABEZADO_CREDITOS,
    LIMITE_DESCRIPCION_YT_BYTES,
    DescripcionDemasiadoLarga,
    armar_descripcion_youtube,
    bytes_utf8,
)

CAPS = ["00:00 - Introducción / Gancho", "01:10 - #5 La novia"]


def test_no_llama_uso_justo_a_las_licencias_abiertas():
    texto = armar_descripcion_youtube("Resumen.", CAPS, ["- Autor / Pixabay (Escena 1)"])
    assert "Uso Justo" not in texto
    assert ENCABEZADO_CREDITOS in texto
    assert "- Autor / Pixabay (Escena 1)" in texto


def test_no_duplica_creditos_si_la_descripcion_ya_los_trae():
    cuerpo = "Resumen.\n\nFuentes: X.\nCC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/):\n- «Obra», Autor"
    texto = armar_descripcion_youtube(cuerpo, CAPS, ["- Otro / Wikimedia Commons (Escena 2)"])
    assert ENCABEZADO_CREDITOS not in texto
    assert "Otro / Wikimedia" not in texto
    assert "FUENTES Y RECURSOS" not in texto
    assert texto.startswith(cuerpo)


def test_el_limite_se_mide_en_bytes_utf8():
    # 2600 caracteres de 2 bytes caben como caracteres (<5000) pero no como bytes.
    cuerpo = "á" * 2600
    assert len(cuerpo) < LIMITE_DESCRIPCION_YT_BYTES < bytes_utf8(cuerpo)
    with pytest.raises(DescripcionDemasiadoLarga, match="bytes"):
        armar_descripcion_youtube(cuerpo, CAPS, [])


def test_falla_en_voz_alta_en_vez_de_recortar_creditos():
    lineas = [f"- Autor {i} / Wikimedia Commons (CC BY-SA 4.0) (Escena {i % 20 + 1})" for i in range(200)]
    with pytest.raises(DescripcionDemasiadoLarga):
        armar_descripcion_youtube("Resumen.", CAPS, lineas)


def test_justo_en_el_limite_pasa_y_un_byte_mas_falla():
    base = armar_descripcion_youtube("", CAPS, [])
    relleno = LIMITE_DESCRIPCION_YT_BYTES - bytes_utf8(base)
    ok = armar_descripcion_youtube("x" * relleno, CAPS, [])
    assert bytes_utf8(ok) == LIMITE_DESCRIPCION_YT_BYTES
    with pytest.raises(DescripcionDemasiadoLarga):
        armar_descripcion_youtube("x" * (relleno + 1), CAPS, [])
