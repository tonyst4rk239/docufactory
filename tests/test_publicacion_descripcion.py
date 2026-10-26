from src.publicacion import ENCABEZADO_CREDITOS, LIMITE_DESCRIPCION_YT, armar_descripcion_youtube

CAPS = ["00:00 - Introducción / Gancho", "01:10 - #5 La novia"]


def test_no_llama_uso_justo_a_las_licencias_abiertas():
    texto, omitidas = armar_descripcion_youtube("Resumen.", CAPS, ["- Autor / Pixabay (Escena 1)"])
    assert "Uso Justo" not in texto
    assert ENCABEZADO_CREDITOS in texto
    assert "- Autor / Pixabay (Escena 1)" in texto
    assert omitidas == []


def test_no_duplica_creditos_si_la_descripcion_ya_los_trae():
    cuerpo = "Resumen.\n\nFuentes: X.\nCC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/):\n- «Obra», Autor"
    texto, _ = armar_descripcion_youtube(cuerpo, CAPS, ["- Otro / Wikimedia Commons (Escena 2)"])
    assert ENCABEZADO_CREDITOS not in texto
    assert "Otro / Wikimedia" not in texto
    assert "FUENTES Y RECURSOS" not in texto
    assert texto.startswith(cuerpo)


def test_recorta_creditos_para_no_pasar_de_5000():
    lineas = [f"- Autor número {i} / Wikimedia Commons (Escena {i % 20 + 1})" for i in range(300)]
    texto, omitidas = armar_descripcion_youtube("Resumen " * 50, CAPS, lineas)
    assert len(texto) <= LIMITE_DESCRIPCION_YT
    assert omitidas and len(omitidas) < len(lineas)
    assert f"{len(omitidas)} créditos más" in texto
    assert "#Documental" in texto


def test_tope_duro_aunque_el_cuerpo_sea_enorme():
    texto, _ = armar_descripcion_youtube("x" * 7000, CAPS, [])
    assert len(texto) <= LIMITE_DESCRIPCION_YT
