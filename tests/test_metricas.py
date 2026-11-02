"""Pruebas unitarias para el modulo de metricas YouTube.

Cubre exhaustivamente:
1. Novelas Express MX: clasifica novela_cap ANTES de Short (<=180s) y extrae serie/capitulo (Ep N / Cap N).
2. Sin datos inventados: Si falla Analytics, no se guarda fila en metricas_diarias y se reporta error.
3. puntos_de_fuga.sql y vinculacion:
   - Filtra total_vistas >= 200.
   - Ignora segundo 0 y puntos > 100%.
   - Empata video y proyecto por video_id al subir (publicacion*.json), NUNCA por título parecido.
   - NUNCA empata un Short con un proyecto largo.
4. Escritura atomica de tokens sin tocar token_youtube.bak.json.
5. Funcion fecha_local en SQLite (sin sobreescribir strftime).
6. Temas: 'muerte_mx' (mictlan, muertos, ofrenda, catrina, xolo, animas) y 'religión' con \\bpapas?\\b.
"""
from datetime import date, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.metricas.recolectar import (
    inicializar_db,
    inferir_formato_y_metadatos,
    clasificar_tema,
    convertir_a_merida,
    cargar_etiquetas_csv,
    aplicar_etiquetas_manuales,
    guardar_token_atomicamente,
    vincular_escenas_locales,
    buscar_video_id_en_proyecto,
    upsert_video,
    upsert_metrica_diaria,
    upsert_retencion,
    upsert_trafico,
    upsert_escenas,
    iso_duracion_a_s,
    obtener_servicios_youtube,
    NOVELAS_CHANNEL_ID,
)
from src.metricas.reporte import generar_reporte_md, ejecutar_consulta

RAIZ = Path(__file__).resolve().parent.parent
SCHEMA_PATH = RAIZ / "sql" / "schema.sql"
CONSULTAS_DIR = RAIZ / "sql" / "consultas"


class TestMetricas(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_metricas.db"
        self.con = inicializar_db(db_path=self.db_path, schema_path=SCHEMA_PATH)

    def tearDown(self):
        self.con.close()
        self.temp_dir.cleanup()

    # -----------------------------------------------------------------------
    # Requisito 1: Novelas Express MX clasifica novela_cap ANTES de Short (<=180s)
    # -----------------------------------------------------------------------
    def test_novelas_express_clasifica_novela_cap_antes_de_short(self):
        # 1. En Novelas Express MX, incluso con duracion corta (<=180s) es novela_cap
        n1 = inferir_formato_y_metadatos("El Amor Prohibido | Ep 3", 120.0, canal="Novelas Express MX")
        self.assertEqual(n1["formato"], "novela_cap")
        self.assertEqual(n1["serie"], "El Amor Prohibido")
        self.assertEqual(n1["capitulo"], 3)

        n2 = inferir_formato_y_metadatos("Secretos del Destino Cap. 12", 45.0, canal="Novelas Express MX")
        self.assertEqual(n2["formato"], "novela_cap")
        self.assertEqual(n2["serie"], "Secretos del Destino")
        self.assertEqual(n2["capitulo"], 12)

        # 2. En otro canal (ej. Código OcultoTV), duración <= 180s sí es short
        c1 = inferir_formato_y_metadatos("Misterio en el Mar | Ep 3", 120.0, canal="Código OcultoTV")
        self.assertEqual(c1["formato"], "short")

        # Requisito 4: canal Novelas, duración 90 s, "Cap 3" -> formato novela_cap, capitulo 3
        n3 = inferir_formato_y_metadatos("Cap 3", 90.0, canal="Novelas Express MX")
        self.assertEqual(n3["formato"], "novela_cap")
        self.assertEqual(n3["capitulo"], 3)

    # -----------------------------------------------------------------------
    # Requisito 2: Temas con muerte_mx y \bpapas?\b en religión
    # -----------------------------------------------------------------------
    def test_clasificacion_temas_muerte_mx_y_papas(self):
        # Categoría muerte_mx
        self.assertEqual(clasificar_tema("El viaje al Mictlán y el día de muertos"), "muerte_mx")
        self.assertEqual(clasificar_tema("Ofrenda tradicional con catrina y flor de cempasúchil"), "muerte_mx")
        self.assertEqual(clasificar_tema("El xoloitzcuintle que guía a las ánimas en el cementerio"), "muerte_mx")

        # Categoría religión con \bpapas?\b
        self.assertEqual(clasificar_tema("Los secretos de los papas en el Vaticano"), "religión")
        self.assertEqual(clasificar_tema("La profecía del último papa"), "religión")

        # Otras categorías
        self.assertEqual(clasificar_tema("La leyenda del nahual de Coyoacán"), "leyenda")
        self.assertEqual(clasificar_tema("El misterio del ovni en Roswell"), "paranormal")
        self.assertEqual(clasificar_tema("El crimen sin resolver del asesino serial"), "crimen")
        self.assertEqual(clasificar_tema("Pelea y escándalo en Acapulco Shore"), "reality")
        self.assertEqual(clasificar_tema("Cómo se inventó el primer transistor en la historia"), "historia")

    # -----------------------------------------------------------------------
    # Requisito 3: puntos_de_fuga.sql (filtro vistas >= 200, segundo > 0, pct <= 100)
    # y vinculación estricta por video_id guardado al subir
    # -----------------------------------------------------------------------
    def test_puntos_de_fuga_filtros_y_vinculacion_estricta(self):
        # 1. Video con suficientes vistas (>= 200)
        upsert_video(self.con, {
            "video_id": "V_FUGA_VALID",
            "canal": "Código OcultoTV",
            "titulo": "Enigma Profundo",
            "formato": "largo_original",
            "duracion_s": 300.0,
            "fecha_publicacion": "2026-10-30",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_FUGA_VALID",
            "fecha": "2026-10-31",
            "vistas": 250,  # >= 200
        })

        # Video con vistas insuficientes (< 200) que debe ser ignorado por puntos_de_fuga.sql
        upsert_video(self.con, {
            "video_id": "V_FUGA_BAJA",
            "canal": "Código OcultoTV",
            "titulo": "Enigma Poco Visto",
            "formato": "largo_original",
            "duracion_s": 300.0,
            "fecha_publicacion": "2026-10-30",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_FUGA_BAJA",
            "fecha": "2026-10-31",
            "vistas": 120,  # < 200
        })

        # Registrar retención: incluir segundo 0 y un punto anómalo > 100% que deben ser descartados
        upsert_retencion(self.con, [
            {"video_id": "V_FUGA_VALID", "fecha_corte": "2026-10-31", "segundo_relativo": 0.0, "pct_audiencia": 100.0},     # Debe ignorarse (segundo 0)
            {"video_id": "V_FUGA_VALID", "fecha_corte": "2026-10-31", "segundo_relativo": 5.0, "pct_audiencia": 105.0},     # Debe ignorarse (> 100%)
            {"video_id": "V_FUGA_VALID", "fecha_corte": "2026-10-31", "segundo_relativo": 10.0, "pct_audiencia": 90.0},
            {"video_id": "V_FUGA_VALID", "fecha_corte": "2026-10-31", "segundo_relativo": 25.0, "pct_audiencia": 65.0},    # Caída válida de -25%
        ])

        upsert_escenas(self.con, "V_FUGA_VALID", [
            {"n_escena": 1, "inicio_s": 0.0, "fin_s": 15.0, "texto": "Intro misteriosa", "broll_fuente": "niebla"},
            {"n_escena": 2, "inicio_s": 15.0, "fin_s": 40.0, "texto": "Revelación del secreto", "broll_fuente": "radar"},
        ])

        # Curva para video de bajas vistas
        upsert_retencion(self.con, [
            {"video_id": "V_FUGA_BAJA", "fecha_corte": "2026-10-31", "segundo_relativo": 15.0, "pct_audiencia": 40.0},
        ])
        self.con.commit()

        # Ejecutar consulta puntos_de_fuga.sql
        cols, filas = ejecutar_consulta(self.con, CONSULTAS_DIR / "puntos_de_fuga.sql")

        # Verificar que el video con < 200 vistas NO aparece
        vids_en_reporte = [f["video_id"] for f in filas]
        self.assertIn("V_FUGA_VALID", vids_en_reporte)
        self.assertNotIn("V_FUGA_BAJA", vids_en_reporte)

        # Verificar que el segundo 0 NO aparece en segundo_fuga
        segundos = [f["segundo_fuga"] for f in filas]
        self.assertNotIn(0.0, segundos)

        # Verificar que no hay puntos con pct_audiencia > 100%
        for f in filas:
            self.assertLessEqual(f["retencion_momento"], 100.0)

        # Verificar que empató con Escena 2 en el segundo 25
        fila_25 = [f for f in filas if f["segundo_fuga"] == 25.0][0]
        self.assertEqual(fila_25["n_escena"], 2)
        self.assertEqual(fila_25["broll_en_pantalla"], "radar")
        self.assertEqual(fila_25["caida_pct"], -25.0)

    def test_vinculacion_estricta_por_publicacion_json(self):
        # Crear estructura de proyecto en disco con publicacion_youtube.json
        dir_proj = Path(self.temp_dir.name) / "proyectos"
        dir_proj.mkdir(parents=True, exist_ok=True)

        carpeta_ok = dir_proj / "video_proyecto_largo"
        carpeta_ok.mkdir(parents=True, exist_ok=True)
        (carpeta_ok / "guion").mkdir(parents=True, exist_ok=True)
        (carpeta_ok / "guion" / "guion.json").write_text(
            json.dumps({"escenas": [{"id": 1, "voz": "Texto escena 1"}]}), encoding="utf-8"
        )
        # Guardar publicacion con video_id
        (carpeta_ok / "publicacion_youtube.json").write_text(
            json.dumps({"video_id": "VID_MATCH11", "es_short": False}), encoding="utf-8"
        )

        # Proyecto con titulo similar pero SIN video_id (nunca debe empatar por título)
        carpeta_similar = dir_proj / "video_titulo_parecido"
        carpeta_similar.mkdir(parents=True, exist_ok=True)
        (carpeta_similar / "guion").mkdir(parents=True, exist_ok=True)
        (carpeta_similar / "guion" / "guion.json").write_text(
            json.dumps({"escenas": [{"id": 1, "voz": "Texto similar"}]}), encoding="utf-8"
        )

        # Proyecto Short que coincide en ID con video Largo (NUNCA empatar Short con proyecto largo)
        carpeta_short_mismatch = dir_proj / "video_short_mismatch"
        carpeta_short_mismatch.mkdir(parents=True, exist_ok=True)
        (carpeta_short_mismatch / "guion").mkdir(parents=True, exist_ok=True)
        (carpeta_short_mismatch / "guion" / "guion.json").write_text(
            json.dumps({"escenas": [{"id": 1, "voz": "Texto short"}]}), encoding="utf-8"
        )
        (carpeta_short_mismatch / "publicacion_youtube.json").write_text(
            json.dumps({"video_id": "VID_LARGO99", "es_short": True}), encoding="utf-8"
        )

        # Registrar videos en BD
        upsert_video(self.con, {
            "video_id": "VID_MATCH11",
            "canal": "Código OcultoTV",
            "titulo": "Otro Titulo Distinto",
            "formato": "largo_original",
        })
        upsert_video(self.con, {
            "video_id": "VID_SIMIL01",
            "canal": "Código OcultoTV",
            "titulo": "Titulo Parecido",
            "formato": "largo_original",
        })
        upsert_video(self.con, {
            "video_id": "VID_LARGO99",
            "canal": "Código OcultoTV",
            "titulo": "Video Largo",
            "formato": "largo_original",
        })
        self.con.commit()

        # Ejecutar vinculación
        vinculadas = vincular_escenas_locales(self.con, dir_proyectos=dir_proj)
        self.assertEqual(vinculadas, 1)

        # Solo VID_MATCH11 debe tener escenas
        cur1 = self.con.execute("SELECT COUNT(*) FROM escenas WHERE video_id = 'VID_MATCH11'")
        self.assertEqual(cur1.fetchone()[0], 1)

        # VID_SIMIL01 NO debe tener escenas porque no tenía publicacion.json con ID
        cur2 = self.con.execute("SELECT COUNT(*) FROM escenas WHERE video_id = 'VID_SIMIL01'")
        self.assertEqual(cur2.fetchone()[0], 0)

        # VID_LARGO99 NO debe tener escenas porque el proyecto era short y el video largo
        cur3 = self.con.execute("SELECT COUNT(*) FROM escenas WHERE video_id = 'VID_LARGO99'")
        self.assertEqual(cur3.fetchone()[0], 0)

    # -----------------------------------------------------------------------
    # Requisito 4: Escritura atómica de tokens sin tocar token_youtube.bak.json
    # -----------------------------------------------------------------------
    def test_guardar_token_atomicamente(self):
        target_token = Path(self.temp_dir.name) / "token_youtube.json"
        bak_file = Path(self.temp_dir.name) / "token_youtube.bak.json"
        bak_file.write_text("contenido_original_bak", encoding="utf-8")

        guardar_token_atomicamente(target_token, '{"access_token": "nuevo"}')

        self.assertTrue(target_token.exists())
        self.assertEqual(target_token.read_text(encoding="utf-8"), '{"access_token": "nuevo"}')

        # Verificar que token_youtube.bak.json sigue intacto
        self.assertTrue(bak_file.exists())
        self.assertEqual(bak_file.read_text(encoding="utf-8"), "contenido_original_bak")

    # -----------------------------------------------------------------------
    # Requisito 5: Función fecha_local en SQLite (sin sobreescribir strftime)
    # -----------------------------------------------------------------------
    def test_fecha_local_y_ab_largos_iso(self):
        # Verificar que SQLite conserva su strftime nativo
        res_nativo = self.con.execute("SELECT strftime('%Y', '2026-11-02')").fetchone()[0]
        self.assertEqual(res_nativo, "2026")

        # Verificar que fecha_local maneja semanas ISO %G-%V
        res_iso = self.con.execute("SELECT fecha_local('%G-%V', '2026-11-02')").fetchone()[0]
        self.assertEqual(res_iso, "2026-45")

        upsert_video(self.con, {
            "video_id": "V_AB_ISO",
            "canal": "Código OcultoTV",
            "titulo": "Grandes Misterios [Recopilación]",
            "formato": "recopilacion",
            "tema": "paranormal",
            "duracion_s": 300.0,
            "fecha_publicacion": "2026-11-02",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_AB_ISO",
            "fecha": "2026-11-02",
            "vistas": 600,
            "minutos_vistos": 2000.0,
            "duracion_media_s": 200.0,
            "pct_visto_medio": 66.6,
        })
        self.con.commit()

        cols_ab, filas_ab = ejecutar_consulta(self.con, CONSULTAS_DIR / "ab_largos.sql")
        self.assertIn("semana", cols_ab)
        self.assertEqual(filas_ab[0]["semana"], "2026-45")

    # -----------------------------------------------------------------------
    # Ponderación por vistas y zona horaria Mérida
    # -----------------------------------------------------------------------
    def test_ponderacion_por_vistas_y_merida(self):
        upsert_video(self.con, {
            "video_id": "V_POND_1",
            "canal": "Código OcultoTV",
            "titulo": "Video Poco Visto",
            "formato": "largo_original",
            "tema": "historia",
            "duracion_s": 200.0,
            "fecha_publicacion": date.today().isoformat(),
            "hora_publicacion": "14:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_POND_1",
            "fecha": date.today().isoformat(),
            "vistas": 100,
            "minutos_vistos": 200.0,
            "duracion_media_s": 200.0,
            "pct_visto_medio": 80.0,
        })
        upsert_video(self.con, {
            "video_id": "V_POND_2",
            "canal": "Código OcultoTV",
            "titulo": "Video Muy Visto",
            "formato": "largo_original",
            "tema": "historia",
            "duracion_s": 100.0,
            "fecha_publicacion": date.today().isoformat(),
            "hora_publicacion": "14:00:00",
        })
        upsert_metrica_diaria(self.con, {
            "video_id": "V_POND_2",
            "fecha": date.today().isoformat(),
            "vistas": 900,
            "minutos_vistos": 900.0,
            "duracion_media_s": 100.0,
            "pct_visto_medio": 30.0,
        })
        self.con.commit()

        cols, filas = ejecutar_consulta(self.con, CONSULTAS_DIR / "formato_vs_retencion.sql")
        fila = [f for f in filas if f["formato"] == "largo_original"][0]
        self.assertEqual(fila["promedio_pct_visto"], 35.0)  # Ponderado: (80*100 + 30*900)/1000 = 35%
        self.assertEqual(fila["duracion_media_s"], 110.0)

        # Conversión a Mérida
        f, h = convertir_a_merida("2026-10-25T01:30:00Z")
        self.assertEqual(f, "2026-10-24")
        self.assertEqual(h, "19:30:00")

    def test_verificacion_channel_id_novelas(self):
        mock_data = MagicMock()
        mock_data.channels().list().execute.return_value = {
            "items": [{"id": "UC_CANAL_EQUIVOCADO", "snippet": {"title": "Canal No Autorizado"}}]
        }
        fake_token = Path(self.temp_dir.name) / "tok.json"
        fake_token.write_text('{"token": "fake"}', encoding="utf-8")

        with patch("src.metricas.recolectar.resolver_token", return_value=fake_token):
            with patch("google.oauth2.credentials.Credentials.from_authorized_user_file"):
                with patch("googleapiclient.discovery.build", return_value=mock_data):
                    with self.assertRaises(RuntimeError) as ctx:
                        obtener_servicios_youtube(canal="Novelas Express MX")
                    self.assertIn("Error de verificación de canal", str(ctx.exception))
                    self.assertIn(NOVELAS_CHANNEL_ID, str(ctx.exception))


    def test_novelas_duracion_90s_cap_3_especifico(self):
        """Requisito 4: canal Novelas, duración 90 s, 'Cap 3' -> formato novela_cap, capitulo 3."""
        res = inferir_formato_y_metadatos("Cap 3", 90.0, canal="Novelas Express MX")
        self.assertEqual(res["formato"], "novela_cap")
        self.assertEqual(res["capitulo"], 3)

    def test_clasificacion_temas_nuevos_y_especificos(self):
        """Clasifica los 6 temas manuales y verifica que Ramón Ayala sea reality, no paranormal."""
        self.assertEqual(clasificar_tema("La Pascualita de Chihuahua"), "leyenda")
        self.assertEqual(clasificar_tema("Un robot bajó bajo el Arca de Noé"), "religión")
        self.assertEqual(clasificar_tema("Real o IA: el burro que habla"), "viral")
        self.assertEqual(clasificar_tema("Pelea en vivo en La Granja VIP"), "reality")
        self.assertEqual(clasificar_tema("5 videos paranormales captados en cámara"), "paranormal")
        self.assertEqual(clasificar_tema("Top 5 Enjambres de IA y armas autónomas"), "tecnologia")
        # El apagón de Ramón Ayala es reality, no paranormal
        self.assertEqual(clasificar_tema("El misterioso apagón a Ramón Ayala en La México"), "reality")

    def test_buscar_video_id_publicado_txt(self):
        """buscar_video_id_en_proyecto lee PUBLICADO.txt con regex y decide es_short por URL o render."""
        dir_p = Path(self.temp_dir.name) / "proj_publicado"
        dir_p.mkdir(parents=True, exist_ok=True)
        pub_dir = dir_p / "publicacion"
        pub_dir.mkdir(parents=True, exist_ok=True)

        # 1. URL con /shorts/ -> es_short = True
        (pub_dir / "PUBLICADO.txt").write_text("Publicado en https://youtube.com/shorts/AbCdEf12345\n", encoding="utf-8")
        vid, es_short = buscar_video_id_en_proyecto(dir_p)
        self.assertEqual(vid, "AbCdEf12345")
        self.assertTrue(es_short)

        # 2. URL estándar con youtu.be y render largo (>180s) -> es_short = False
        (dir_p / "proyecto.json").write_text(json.dumps({"minutos": 4.0}), encoding="utf-8")
        (pub_dir / "PUBLICADO.txt").write_text("Publicado en https://youtu.be/ZyXwVu98765\n", encoding="utf-8")
        vid2, es_short2 = buscar_video_id_en_proyecto(dir_p)
        self.assertEqual(vid2, "ZyXwVu98765")
        self.assertFalse(es_short2)

    def test_etiquetas_csv_formato_11_chars(self):
        """Verifica que data/etiquetas_videos.csv use IDs de 11 caracteres y no tenga filas inválidas."""
        etiquetas = cargar_etiquetas_csv(RAIZ / "data" / "etiquetas_videos.csv")
        self.assertGreater(len(etiquetas), 0)
        for vid, meta in etiquetas.items():
            self.assertEqual(len(vid), 11, f"video_id {vid} debe tener exactamente 11 caracteres")
            self.assertFalse(vid.startswith("test_revision_lente"))
            self.assertFalse(vid.startswith("misterio_prueba"))
            self.assertFalse("amor_seul" in vid)
            self.assertFalse("venganza" in vid)


if __name__ == "__main__":
    unittest.main()
