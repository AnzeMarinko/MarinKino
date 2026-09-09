#!/bin/bash
set -e

URL="${1}"
if [ -z "$URL" ]; then
    read -p "Vnesi URL videa: " URL
fi

# 1. Pridobivanje naslova videa za ime mape
TITLE=$(yt-dlp --get-filename -o "%(title)s" "$URL" | tr '/\\' '_')
OUTPUT_DIR="${TITLE}"

mkdir -p "$OUTPUT_DIR"
cd "$OUTPUT_DIR"

echo "==> 1. Prenašanje raw tokov..."
yt-dlp -f "12452/7683/bestvideo[height<=1440]" -o "tmp_video.mp4" "$URL"
yt-dlp -f "audio-Slovenian/ba[language=sl]" -o "tmp_audio_sl.mp4" "$URL"
yt-dlp -f "audio-English/ba[language=en]" -o "tmp_audio_en.mp4" "$URL"

echo "==> 2. Priprava fragmentiranih MP4 vsebnikov..."
ffmpeg -y -i tmp_video.mp4 -c copy -movflags empty_moov+default_base_moof+frag_keyframe tmp_video_frag.mp4
ffmpeg -y -i tmp_audio_sl.mp4 -c copy -movflags empty_moov+default_base_moof+frag_keyframe tmp_audio_sl_frag.mp4
ffmpeg -y -i tmp_audio_en.mp4 -c copy -movflags empty_moov+default_base_moof+frag_keyframe tmp_audio_en_frag.mp4

echo "==> 3. Pakiranje z Shaka Packager v single-segment HLS..."
TMPDIR="/tmp" packager \
  in=tmp_video_frag.mp4,stream=video,output=video.ts,format=mp4 \
  in=tmp_audio_sl_frag.mp4,stream=audio,output=audio_sl.ts,format=mp4,lang=sl,hls_name=Slovenščina \
  in=tmp_audio_en_frag.mp4,stream=audio,output=audio_en.ts,format=mp4,lang=en,hls_name=English \
  --io_block_size 65536 \
  --hls_master_playlist_output master.m3u8

echo "==> 4. Prenašanje podnapisov..."
yt-dlp --write-subs --sub-langs "sl.*,en.*" --skip-download --convert-subs srt -o "sub_%(lang)s.%(ext)s" "$URL" || true

echo "==> 5. Čiščenje začasnih datotek..."
rm -rf tmp_*.mp4

echo "==> Končano v mapi '${OUTPUT_DIR}'!"
