from pathlib import Path

import src.edicion as ed


def _mp4(carpeta: Path, nombre: str) -> Path:
    f = carpeta / nombre
    f.write_bytes(b"\0" * 20_000)
    return f


def test_27706_con_codigo_legible_nunca_se_elige(tmp_path, monkeypatch):
    glitch = tmp_path / "glitch"
    glitch.mkdir()
    for n in ("glitch_pixabay_27228.mp4", "glitch_pixabay_27706.mp4", "glitch_pixabay_36784.mp4"):
        _mp4(glitch, n)
    assert [a.name for a in ed.listar_archivos_overlay(glitch)] == ["glitch_pixabay_27228.mp4", "glitch_pixabay_36784.mp4"]
    monkeypatch.setattr(ed.config, "OVERLAYS_DIR", tmp_path)
    cfg = {"textura_visual": {"video_overlay": {"enabled": True, "por_mood": {"tension": ["glitch"]}}}}
    elegidos = {ed.resolver_overlay_por_mood("tension", idx, es_inicio_top=True, cfg=cfg, silencioso=True)[0].name
                for idx in range(1, 30)}
    assert "glitch_pixabay_27706.mp4" not in elegidos
    assert elegidos == {"glitch_pixabay_27228.mp4", "glitch_pixabay_36784.mp4"}


def test_bloqueados_desde_config(tmp_path):
    _mp4(tmp_path, "a.mp4")
    _mp4(tmp_path, "b.mp4")
    assert [a.name for a in ed.listar_archivos_overlay(tmp_path, {"B.mp4"})] == ["a.mp4"]
