import os
import subprocess
import json

def run():
    temp_dir = 'C:/Users/coazo/docu_factory/temp/video_1_segments'

    with open('C:/Users/coazo/docu_factory/scripts/timeline_video_1.json', 'r', encoding='utf-8') as f:
        timeline = json.load(f)

    audio_dir = 'C:/Users/coazo/docu_factory/assets/audio/video_1_ia'
    music_track = 'C:/Users/coazo/docu_factory/assets/music/misterio/freepd_asking_questions.mp3'
    output_dir = 'C:/Users/coazo/docu_factory/output'
    os.makedirs(output_dir, exist_ok=True)

    segment_videos = []

    for item in timeline:
        idx = item['index']
        raw_video = os.path.join(temp_dir, f'video_raw_{idx}.mp4').replace('\\', '/')
        audio_path = os.path.join(audio_dir, item['audio']).replace('\\', '/')
        mixed_audio = os.path.join(temp_dir, f'audio_mixed_{idx}.aac').replace('\\', '/')
        seg_final = os.path.join(temp_dir, f'seg_final_{idx}.mp4').replace('\\', '/')
        
        # 1. Mezclar voz y música de fondo limpiamente
        cmd_a = [
            'ffmpeg', '-y',
            '-i', audio_path,
            '-stream_loop', '-1', '-i', music_track,
            '-filter_complex', '[0:a]volume=1.25[vocal];[1:a]volume=0.10[bgm];[vocal][bgm]amix=inputs=2:duration=first[a]',
            '-map', '[a]',
            '-c:a', 'aac', '-b:a', '192k',
            mixed_audio
        ]
        subprocess.run(cmd_a, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # 2. Mux directo con el video raw
        cmd_m = [
            'ffmpeg', '-y',
            '-i', raw_video,
            '-i', mixed_audio,
            '-c:v', 'copy',
            '-c:a', 'copy',
            '-shortest',
            seg_final
        ]
        subprocess.run(cmd_m, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        item_title = item['title']
        print(f'Segmento {idx} completado: {item_title}')
        segment_videos.append(seg_final)

    # 3. Concatenar todos los segmentos
    concat_txt = os.path.join(temp_dir, 'master_list.txt')
    with open(concat_txt, 'w', encoding='utf-8') as f:
        for sv in segment_videos:
            f.write(f"file '{sv}'\n")

    master_output = os.path.join(output_dir, 'estreno_top_5_enjambres_y_armas_autonomas_ia_2026.mp4')
    cmd_master = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', concat_txt,
        '-c', 'copy', master_output
    ]
    subprocess.run(cmd_master, check=True)
    print('¡VIDEO MASTER FINAL COMPLETADO EXITOSAMENTE!')
    print('Ruta:', master_output)

if __name__ == '__main__':
    run()
