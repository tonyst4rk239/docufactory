import os
import subprocess
import json

def render():
    with open('C:/Users/coazo/docu_factory/scripts/timeline_video_1.json', 'r', encoding='utf-8') as f:
        timeline = json.load(f)

    audio_dir = 'C:/Users/coazo/docu_factory/assets/audio/video_1_ia'
    broll_dir = 'C:/Users/coazo/docu_factory/assets/broll_viral'
    temp_dir = 'C:/Users/coazo/docu_factory/temp/video_1_segments'
    music_track = 'C:/Users/coazo/docu_factory/assets/music/misterio/freepd_asking_questions.mp3'
    output_dir = 'C:/Users/coazo/docu_factory/output'
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    segment_videos = []

    for item in timeline:
        idx = item['index']
        audio_path = os.path.join(audio_dir, item['audio'])
        raw_title = item['title'].replace(':', ' -').replace("'", "")
        
        # Obtener duración del audio
        cmd_d = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_path]
        dur = float(subprocess.run(cmd_d, capture_output=True, text=True).stdout.strip())
        
        clips = item['clips']
        clip_dur = dur / len(clips)
        
        subclips_txt = os.path.join(temp_dir, f'concat_{idx}.txt')
        with open(subclips_txt, 'w', encoding='utf-8') as cf:
            for c_idx, c_name in enumerate(clips):
                c_path = os.path.join(broll_dir, c_name).replace('\\', '/')
                c_out = os.path.join(temp_dir, f'part_{idx}_{c_idx}.mp4').replace('\\', '/')
                c_cmd = [
                    'ffmpeg', '-y', '-stream_loop', '4', '-i', c_path,
                    '-t', str(clip_dur),
                    '-vf', 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,format=yuv420p',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-an',
                    c_out
                ]
                subprocess.run(c_cmd, capture_output=True)
                cf.write(f"file '{c_out}'\n")
                
        seg_raw_video = os.path.join(temp_dir, f'video_raw_{idx}.mp4')
        cmd_cat = [
            'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', subclips_txt,
            '-c', 'copy', seg_raw_video
        ]
        subprocess.run(cmd_cat, capture_output=True)
        
        seg_final = os.path.join(temp_dir, f'seg_final_{idx}.mp4')
        
        # Text overlay
        draw_title = f"drawtext=text='{raw_title}':fontcolor=0x00E5FF:fontsize=42:box=1:boxcolor=black@0.65:boxborderw=16:x=(w-text_w)/2:y=90:enable='between(t,0.5,8)'"
        draw_watermark = "drawtext=text='CÓDIGO OCULTO TV':fontcolor=white@0.5:fontsize=24:x=60:y=h-60"
        vf_filter = f"{draw_title},{draw_watermark}"
        
        cmd_compose = [
            'ffmpeg', '-y',
            '-i', seg_raw_video,
            '-i', audio_path,
            '-stream_loop', '-1', '-i', music_track,
            '-filter_complex',
            f'[0:v]{vf_filter}[v];[1:a]volume=1.2[vocal];[2:a]volume=0.10[bgm];[vocal][bgm]amix=inputs=2:duration=first[a]',
            '-map', '[v]', '-map', '[a]',
            '-c:v', 'libx264', '-preset', 'veryfast', '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            seg_final
        ]
        res = subprocess.run(cmd_compose, capture_output=True)
        if res.returncode != 0:
            print(f'Error en segmento {idx}:', res.stderr.decode('utf-8', errors='ignore'))
        segment_videos.append(seg_final)
        print(f'Segmento {idx} completado: {raw_title}')

    final_concat_list = os.path.join(temp_dir, 'all_segments.txt')
    with open(final_concat_list, 'w', encoding='utf-8') as af:
        for sv in segment_videos:
            clean_path = sv.replace('\\', '/')
            af.write(f"file '{clean_path}'\n")

    master_output = os.path.join(output_dir, 'estreno_top_5_enjambres_y_armas_autonomas_ia_2026.mp4')
    cmd_master = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', final_concat_list,
        '-c', 'copy', master_output
    ]
    subprocess.run(cmd_master, capture_output=True)
    print('VIDEO MASTER FINAL COMPLETADO:', master_output)

if __name__ == '__main__':
    render()
