"""Build a vertical MP4 reel from a list of PNG slides via ffmpeg.

Niente moviepy / niente dipendenze Python extra: usiamo direttamente la
CLI di ffmpeg via subprocess. ffmpeg deve essere installato nel container
(apt-get install ffmpeg).

Output:
- 1080x1920 H.264 + AAC (anche se video silenzioso, AAC track migliora
  compatibilita' con Instagram Reels)
- 30 fps
- Ogni slide dura `per_slide` secondi (default 3.5s)
- Crossfade `xfade_duration` secondi (default 0.6s) tra slide consecutive

Strategia: costruiamo un filter_complex con xfade a catena.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class VideoBuildError(RuntimeError):
    pass


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def build_reel_video(
    *,
    slide_paths: list[Path],
    output_path: Path,
    per_slide: float = 3.5,
    xfade_duration: float = 0.6,
    width: int = 1080,
    height: int = 1920,
    fps: int = 30,
) -> Path:
    """Compone un MP4 verticale dal dato elenco di immagini.

    - `slide_paths`: lista ordinata di PNG (devono esistere). Se vuota → errore.
    - `output_path`: file di destinazione (.mp4).
    """
    if not _ffmpeg_available():
        raise VideoBuildError(
            "ffmpeg non installato nel container. Aggiungi 'fonts-noto-core ffmpeg' "
            "nella RUN apt-get del Dockerfile e ricostruisci con 'docker compose up --build'."
        )
    if not slide_paths:
        raise VideoBuildError("Nessuna slide fornita per il video.")

    # Verifica esistenza dei file
    for p in slide_paths:
        if not p.is_file():
            raise VideoBuildError(f"Slide mancante: {p}")

    # Caso degenere: una sola slide → video statico con il primo PNG
    if len(slide_paths) == 1:
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-t", str(per_slide), "-i", str(slide_paths[0]),
            "-f", "lavfi", "-t", str(per_slide), "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},format=yuv420p",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            str(output_path),
        ]
        return _run(cmd, output_path)

    # Caso normale: piu' slide con crossfade
    # Per N slide e xfade tra ogni coppia, ogni slide deve durare per_slide secondi,
    # ma l'ultima clip dell'xfade DEVE durare almeno (per_slide) secondi.
    # Il timing degli xfade e' cumulativo: offset_i = i*(per_slide - xfade_duration).

    input_args: list[str] = []
    for p in slide_paths:
        input_args += [
            "-loop", "1",
            "-t", f"{per_slide:.3f}",
            "-i", str(p),
        ]
    # Audio silenzioso di durata pari a quella del video finale
    total_video_sec = per_slide + (len(slide_paths) - 1) * (per_slide - xfade_duration)
    input_args += [
        "-f", "lavfi",
        "-t", f"{total_video_sec:.3f}",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
    ]

    # Filter complex: scale/crop ogni input poi xfade a catena
    fc_lines: list[str] = []
    # 1) Normalizza ciascun input a width x height + format yuv420p
    for i in range(len(slide_paths)):
        fc_lines.append(
            f"[{i}:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,format=yuv420p[v{i}]"
        )
    # 2) Catena di xfade
    last_label = "v0"
    cumulative_offset = per_slide - xfade_duration  # offset del primo xfade
    for i in range(1, len(slide_paths)):
        next_label = f"x{i}" if i < len(slide_paths) - 1 else "vout"
        fc_lines.append(
            f"[{last_label}][v{i}]xfade=transition=fade:duration={xfade_duration}:"
            f"offset={cumulative_offset:.3f}[{next_label}]"
        )
        last_label = next_label
        cumulative_offset += per_slide - xfade_duration

    filter_complex = ";".join(fc_lines)

    cmd = [
        "ffmpeg", "-y",
        *input_args,
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", f"{len(slide_paths)}:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_path),
    ]
    return _run(cmd, output_path)


def _run(cmd: list[str], output_path: Path) -> Path:
    logger.info("ffmpeg cmd: %s", " ".join(cmd))
    try:
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=180,
        )
    except subprocess.TimeoutExpired as e:
        raise VideoBuildError(f"ffmpeg timeout: {e}") from e
    if proc.returncode != 0:
        # Logga solo le ultime righe dello stderr (ffmpeg e' verboso)
        tail = "\n".join(proc.stderr.splitlines()[-15:])
        raise VideoBuildError(f"ffmpeg exit {proc.returncode}\n{tail}")
    if not output_path.is_file():
        raise VideoBuildError(f"ffmpeg ha riportato successo ma {output_path} non esiste")
    return output_path
