import os
import subprocess
import json
from PIL import Image, ImageDraw, ImageFont

def render_deluxe_master():
    root = 'C:/Users/coazo/docu_factory'
    temp_dir = f'{root}/temp/video_1_segments'
    cards_dir = f'{root}/temp/title_cards'
    broll_dir = f'{root}/assets/broll_viral'
    audio_dir = f'{root}/assets/audio/video_1_ia'
    music_track = f'{root}/assets/music/misterio/bg_soundtrack.wav'
    sfx_teclado = f'{root}/assets/sfx/teclado/typing_corto_boosted.wav'
    sfx_trans = f'{root}/assets/sfx/transicion/pop_transicion.wav'
    output_dir = f'{root}/output'

    os.makedirs(cards_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    timeline_items = [
        {
            'index': 0,
            'main': 'EL FIN DEL CONTROL HUMANO',
            'sub': 'TOP 5 TECNOLOGÍAS BÉLICAS Y DE IA (2026)',
            'audio': 'sec_0_intro.mp3',
            'clips': ['matrix_digital_clean.mp4', 'military_satellite_hud.mp4', 'slaughterbots_microdrones.mp4']
        },
        {
            'index': 1,
            'main': 'TOP 5',
            'sub': 'PROYECTO MERIDIAN Y SABUESOS DE ACERO',
            'audio': 'sec_1_top_5.mp3',
            'clips': ['spot_robot.mp4', 'military_satellite_hud.mp4', 'spot_robot.mp4']
        },
        {
            'index': 2,
            'main': 'TOP 4',
            'sub': 'KARGU-2: PRIMER ATAQUE 100% AUTÓNOMO',
            'audio': 'sec_2_top_4.mp3',
            'clips': ['kargu2_drone.mp4', 'matrix_digital_clean.mp4', 'kargu2_drone.mp4']
        },
        {
            'index': 3,
            'main': 'TOP 3',
            'sub': 'ENJAMBRES DE MICRODRONES Y MENTE COLMENA',
            'audio': 'sec_3_top_3.mp3',
            'clips': ['slaughterbots_microdrones.mp4', 'drone_swarm_china.mp4', 'slaughterbots_microdrones.mp4']
        },
        {
            'index': 4,
            'main': 'TOP 2',
            'sub': 'ALGORITMO LAVENDER: SELECCIÓN POR IA',
            'audio': 'sec_4_top_2.mp3',
            'clips': ['lavender_ai_target.mp4', 'military_satellite_hud.mp4', 'matrix_digital_clean.mp4']
        },
        {
            'index': 5,
            'main': 'TOP 1',
            'sub': 'EL DÍA Q Y LA GUERRA DE CABLES SUBMARINOS',
            'audio': 'sec_5_top_1.mp3',
            'clips': ['cables_submarinos.mp4', 'ocean_underwater_clean.mp4', 'quantum_computer_ibm.mp4']
        },
        {
            'index': 6,
            'main': 'SUSCRÍBETE A CÓDIGO OCULTO TV',
            'sub': 'INVESTIGANDO EL LADO OCULTO DE LA TECNOLOGÍA',
            'audio': 'sec_6_outro.mp3',
            'clips': ['matrix_digital_clean.mp4', 'military_satellite_hud.mp4', 'drone_swarm_china.mp4']
        }
    ]

    font_path = 'C:/Windows/Fonts/arialbd.ttf'
    font_main = ImageFont.truetype(font_path, 80)
    font_sub = ImageFont.truetype(font_path, 44)

    segment_videos = []

    for item in timeline_items:
        idx = item['index']
        main_t = item['main']
        sub_t = item['sub']
        audio_file = os.path.join(audio_dir, item['audio']).replace('\\', '/')
        
        # 1. Generar Tarjeta Centrada en Alta Definición (1920x1080)
        card_path = os.path.join(cards_dir, f'card_{idx}.png').replace('\\', '/')
        img = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        box_w = 1520
        box_h = 240
        box_x0 = (1920 - box_w) // 2
        box_y0 = (1080 - box_h) // 2
        box_x1 = box_x0 + box_w
        box_y1 = box_y0 + box_h
        
        # Caja oscura semitransparente con borde cian neón vibrante
        draw.rounded_rectangle([box_x0, box_y0, box_x1, box_y1], radius=24, fill=(10, 15, 25, 220), outline=(0, 229, 255, 255), width=5)
        
        # Medir y centrar título principal (Cian Neón Grande)
        bm = draw.textbbox((0, 0), main_t, font=font_main)
        wm = bm[2] - bm[0]
        xm = (1920 - wm) // 2
        ym = box_y0 + 25
        draw.text((xm, ym), main_t, font=font_main, fill=(0, 229, 255, 255))
        
        # Medir y centrar subtítulo (Blanco Nítido)
        bs = draw.textbbox((0, 0), sub_t, font=font_sub)
        ws = bs[2] - bs[0]
        xs = (1920 - ws) // 2
        ys = ym + 98
        draw.text((xs, ys), sub_t, font=font_sub, fill=(255, 255, 255, 255))
        
        img.save(card_path)

        # 2. Generar video base alternando clips limpios
        cmd_d = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_file]
        dur = float(subprocess.run(cmd_d, capture_output=True, text=True).stdout.strip())
        
        clips = item['clips']
        clip_dur = dur / len(clips)
        
        concat_txt = os.path.join(temp_dir, f'concat_{idx}.txt').replace('\\', '/')
        with open(concat_txt, 'w', encoding='utf-8') as cf:
            for c_i, c_name in enumerate(clips):
                c_src = os.path.join(broll_dir, c_name).replace('\\', '/')
                c_part = os.path.join(temp_dir, f'part_{idx}_{c_i}.mp4').replace('\\', '/')
                c_cmd = [
                    'ffmpeg', '-y', '-stream_loop', '4', '-i', c_src,
                    '-t', str(clip_dur),
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-an',
                    c_part
                ]
                subprocess.run(c_cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                cf.write(f"file '{c_part}'\n")

        raw_video = os.path.join(temp_dir, f'video_raw_{idx}.mp4').replace('\\', '/')
        cmd_cat = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt, '-c', 'copy', raw_video]
        subprocess.run(cmd_cat, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # 3. Superponer título centrado (visible de 0.3s a 4.2s) con SFX de transición + sonido de teclado exacto
        seg_final = os.path.join(temp_dir, f'seg_deluxe_{idx}.mp4').replace('\\', '/')
        
        # Audio graph:
        # [1:a] voz del narrador (volumen 1.25)
        # [2:a] música ambiental de misterio en loop (volumen 0.10)
        # [3:a] sfx transición pop (delay 100ms, volumen 0.70)
        # [4:a] sfx teclado typing corto (delay 250ms, dura 1.3s y se detiene automáticamente, volumen 0.85)
        filter_complex = (
            "[0:v][5:v]overlay=0:0:enable='between(t,0.3,4.2)':format=auto[v];"
            "[1:a]volume=1.25[vocal];"
            "[2:a]volume=0.10[bgm];"
            "[3:a]adelay=100|100,volume=0.70[sfx_pop];"
            "[4:a]adelay=250|250,volume=0.85[sfx_key];"
            "[vocal][bgm][sfx_pop][sfx_key]amix=inputs=4:duration=first[a]"
        )

        cmd_compose = [
            'ffmpeg', '-y',
            '-i', raw_video,
            '-i', audio_file,
            '-stream_loop', '-1', '-i', music_track,
            '-i', sfx_trans.replace('\\', '/'),
            '-i', sfx_teclado.replace('\\', '/'),
            '-i', card_path,
            '-filter_complex', filter_complex,
            '-map', '[v]', '-map', '[a]',
            '-c:v', 'libx264', '-preset', 'veryfast',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            seg_final
        ]
        subprocess.run(cmd_compose, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        segment_videos.append(seg_final)
        print(f"Segmento {idx} renderizado con título centrado y efectos sincronizados: {main_t}")

    # 4. Ensamble de todo el documental
    master_list = os.path.join(temp_dir, 'master_deluxe_list.txt').replace('\\', '/')
    with open(master_list, 'w', encoding='utf-8') as mf:
        for sv in segment_videos:
            mf.write(f"file '{sv}'\n")

    master_output = os.path.join(output_dir, 'estreno_top_5_enjambres_y_armas_autonomas_ia_2026.mp4').replace('\\', '/')
    cmd_master = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', master_list,
        '-c', 'copy', master_output
    ]
    subprocess.run(cmd_master, check=True)
    print("¡VIDEO MASTER OFICIAL ACTUALIZADO CON ÉXITO!")
    print("Archivo:", master_output)

if __name__ == '__main__':
    render_deluxe_master()
