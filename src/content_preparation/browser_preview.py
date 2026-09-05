"""Majhni pomožniki za grafični pregled v brskalniku med interaktivno
pripravo filmov (izbira podnapisov, potrditev poravnave)."""

import http.server
import json
import logging
import tempfile
import threading
import webbrowser
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .subtitles.rescale_captions import TARGET_RATE, extract_subtitles

log = logging.getLogger(__name__)


def show_subtitle_excerpts_gallery(subtitle_files, max_lines=6):
    """Odpre v brskalniku pregled prvih vrstic vsakega podnapisa,
    da jih je lažje primerjati pred izbiro."""
    cards = []
    for i, srt_path in enumerate(subtitle_files, start=1):
        try:
            entries = extract_subtitles(str(srt_path))[:max_lines]
            excerpt = "<br>".join(
                f"{s:.0f}s: {text.replace(chr(10), ' ')}"
                for s, _e, text in entries
            )
        except Exception as e:
            excerpt = f"(napaka pri branju: {e})"
        cards.append(
            f"""
            <div style="border:1px solid #ccc;padding:10px;margin:8px 0;
            font-family:sans-serif;">
                <h3>{i}. {srt_path.name}</h3>
                <p style="font-size:13px;">{excerpt}</p>
            </div>
            """
        )
    page = f"<html><body>{''.join(cards)}</body></html>"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".html", delete=False, encoding="utf-8"
    ) as f:
        f.write(page)
        path = f.name
    webbrowser.open(f"file://{path}")


def _vtt_timestamp(seconds):
    seconds = max(0, seconds)
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{int(hours):02d}:{int(minutes):02d}:{secs:06.3f}"


def _render_vtt(subtitles, scale, shift):
    lines = ["WEBVTT", ""]
    for start, end, text in subtitles:
        lines.append(
            f"{_vtt_timestamp(start * scale + shift)} --> "
            f"{_vtt_timestamp(end * scale + shift)}"
        )
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def _downsample(values, max_points=1500):
    step = max(1, len(values) // max_points)
    return [round(float(v), 4) for v in values[::step]]


def preview_and_confirm_alignment(folder, video_rel_path, proposal, srt_name):
    """Odpre interaktiven predogled v brskalniku (video s podnapisi + graf
    poravnave govora, z drsniki za zamik/raztezek ter gumboma za potrditev
    ali preklic). Blokira, dokler uporabnik v brskalniku ne klikne enega od
    gumbov. Vrne {"confirmed": bool, "scale": float, "shift": float}."""
    folder_path = Path(folder)
    subtitles = proposal["subtitles"]
    speech = proposal["speech"]
    audio = proposal["audio"]
    compute_score = proposal["compute_score"]
    current_score = proposal["current_score"]

    time_axis = [i / TARGET_RATE for i in range(len(speech))]
    graph_data = {
        "time": _downsample(time_axis),
        "audio": _downsample(audio),
        "speech": _downsample(speech),
    }

    result = {}
    done = threading.Event()

    def score_pct(scale, shift):
        return round(
            (compute_score(scale, shift) / current_score - 1) * 100, 2
        )

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def _json(self, payload):
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/api/state":
                self._json(
                    {
                        "graph": graph_data,
                        "scale": proposal["scale"],
                        "shift": proposal["shift"],
                        "score_pct": score_pct(
                            proposal["scale"], proposal["shift"]
                        ),
                        "get_subtitle_audio": _downsample(
                            proposal["get_subtitle_audio"](
                                proposal["scale"], proposal["shift"]
                            )
                        ),
                    }
                )
                return
            if parsed.path == "/api/preview":
                q = parse_qs(parsed.query)
                scale = float(q.get("scale", [1.0])[0])
                shift = float(q.get("shift", [0.0])[0])
                self._json(
                    {
                        "score_pct": score_pct(scale, shift),
                        "subtitle_audio": _downsample(
                            proposal["get_subtitle_audio"](scale, shift)
                        ),
                    }
                )
                return
            if parsed.path == "/api/preview.vtt":
                q = parse_qs(parsed.query)
                scale = float(q.get("scale", [1.0])[0])
                shift = float(q.get("shift", [0.0])[0])
                body = _render_vtt(subtitles, scale, shift).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/vtt")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().do_GET()

        def do_POST(self):
            if self.path != "/api/finish":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
            result["confirmed"] = bool(body.get("confirmed"))
            result["scale"] = float(body.get("scale", proposal["scale"]))
            result["shift"] = float(body.get("shift", proposal["shift"]))
            self._json({"ok": True})
            done.set()

    handler = partial(Handler, directory=str(folder_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    preview_html = folder_path / ".alignment_preview.html"
    preview_html.write_text(
        _ALIGNMENT_PAGE.format(video=video_rel_path, srt_name=srt_name),
        encoding="utf-8",
    )

    try:
        webbrowser.open(f"http://127.0.0.1:{port}/.alignment_preview.html")
        print(
            "🎬 Predvajalnik s poravnavo je odprt v brskalniku - "
            "s pomočjo drsnikov prilagodi zamik/raztezek in "
            "potrdi ali prekliči s klikom v brskalniku."
        )
        done.wait()
    finally:
        server.shutdown()
        thread.join(timeout=5)
        preview_html.unlink(missing_ok=True)

    return result or {
        "confirmed": False,
        "scale": proposal["scale"],
        "shift": proposal["shift"],
    }


_ALIGNMENT_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Poravnava podnapisov: {srt_name}</title>
<script src="https://cdn.plot.ly/plotly-3.3.1.min.js"></script>
<style>
    body {{ background:#111; color:#eee; font-family:sans-serif; margin:0; padding:16px; }}
    video {{ width:100%; max-height:45vh; background:#000; }}
    .row {{ display:flex; gap:24px; flex-wrap:wrap; margin:10px 0; }}
    .control {{ flex:1; min-width:260px; }}
    label {{ display:block; margin-bottom:4px; }}
    input[type=range] {{ width:100%; }}
    #score {{ font-size:1.2em; font-weight:bold; margin:10px 0; }}
    button {{ font-size:1em; padding:8px 18px; margin-right:10px; cursor:pointer; }}
    #confirm {{ background:#2e7d32; color:#fff; border:none; border-radius:4px; }}
    #cancel {{ background:#555; color:#fff; border:none; border-radius:4px; }}
</style>
</head>
<body>
    <video id="video" src="{video}" controls style="width:100%">
        <track id="track" kind="subtitles" src="/api/preview.vtt?scale=1&shift=0" default>
    </video>
    <div id="graph" style="height:320px;"></div>
    <div id="score">Izboljšava poravnave: ...</div>
    <div class="row">
        <div class="control">
            <label>Zamik (sekunde): <span id="shift-val"></span></label>
            <input type="range" id="shift" min="-90" max="90" step="0.1">
        </div>
        <div class="control">
            <label>Raztezek: <span id="scale-val"></span></label>
            <input type="range" id="scale" min="0.85" max="1.15" step="0.001">
        </div>
    </div>
    <button id="confirm">✅ Potrdi poravnavo</button>
    <button id="cancel">✖ Prekliči (obdrži prvotno)</button>

    <script>
        let state = null;
        let debounceTimer = null;
        let fullTimeRange = null;
        let ticksBound = false;

        function formatMinSec(totalSeconds) {{
            const sign = totalSeconds < 0 ? '-' : '';
            totalSeconds = Math.round(Math.abs(totalSeconds));
            const m = Math.floor(totalSeconds / 60);
            const s = totalSeconds % 60;
            return sign + m + ':' + String(s).padStart(2, '0');
        }}

        function niceStep(rawStep) {{
            const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];
            for (const s of steps) {{
                if (rawStep <= s) return s;
            }}
            return Math.ceil(rawStep / 3600) * 3600;
        }}

        function computeTicks(range) {{
            const [minX, maxX] = range;
            const step = niceStep((maxX - minX) / 8) || 1;
            const start = Math.ceil(minX / step) * step;
            const tickvals = [];
            const ticktext = [];
            for (let t = start; t <= maxX; t += step) {{
                tickvals.push(t);
                ticktext.push(formatMinSec(t));
            }}
            return {{ tickvals, ticktext }};
        }}

        function applyTicksForRange(range) {{
            const ticks = computeTicks(range);
            Plotly.relayout('graph', {{
                'xaxis.tickvals': ticks.tickvals,
                'xaxis.ticktext': ticks.ticktext
            }});
        }}

        async function loadState() {{
            const res = await fetch('/api/state');
            state = await res.json();
            fullTimeRange = [state.graph.time[0], state.graph.time[state.graph.time.length - 1]];
            document.getElementById('shift').value = state.shift;
            document.getElementById('scale').value = state.scale;
            document.getElementById('shift-val').textContent = state.shift.toFixed(1) + ' s';
            document.getElementById('scale-val').textContent = (state.scale * 100).toFixed(1) + ' %';
            updateScoreText(state.score_pct);
            drawGraph(state.get_subtitle_audio);
            reloadTrack(state.scale, state.shift);
        }}

        function updateScoreText(pct) {{
            const sign = pct >= 0 ? '+' : '';
            document.getElementById('score').textContent =
                'Izboljšava poravnave glede na neporavnano: ' + sign + pct.toFixed(2) + ' %';
        }}

        function drawGraph(subtitleAudio) {{
            const traces = [
                {{ x: state.graph.time, y: state.graph.audio, name: 'Zvok', line: {{ color: '#888' }} }},
                {{ x: state.graph.time, y: state.graph.speech, name: 'Zaznan govor', line: {{ color: '#4fc3f7' }} }},
                {{ x: state.graph.time, y: subtitleAudio, name: 'Podnapisi', line: {{ color: '#ffb300' }} }}
            ];
            const ticks = computeTicks(fullTimeRange);
            const layout = {{
                paper_bgcolor: '#111', plot_bgcolor: '#111',
                font: {{ color: '#eee' }},
                margin: {{ t: 20, b: 40, l: 40, r: 10 }},
                xaxis: {{
                    title: 'Čas (min:sek)',
                    tickvals: ticks.tickvals,
                    ticktext: ticks.ticktext
                }},
                yaxis: {{ title: 'Aktivnost' }},
                uirevision: 'alignment'
            }};
            Plotly.react('graph', traces, layout, {{ responsive: true }});

            if (!ticksBound) {{
                ticksBound = true;
                document.getElementById('graph').on('plotly_relayout', (evt) => {{
                    if (evt['xaxis.range[0]'] !== undefined) {{
                        applyTicksForRange([evt['xaxis.range[0]'], evt['xaxis.range[1]']]);
                    }} else if (evt['xaxis.autorange']) {{
                        applyTicksForRange(fullTimeRange);
                    }}
                }});
            }}
        }}

        function reloadTrack(scale, shift) {{
            const video = document.getElementById('video');
            const time = video.currentTime;
            const wasPlaying = !video.paused;
            const old = document.getElementById('track');
            old.remove();
            const track = document.createElement('track');
            track.id = 'track';
            track.kind = 'subtitles';
            track.default = true;
            track.src = `/api/preview.vtt?scale=${{scale}}&shift=${{shift}}&v=${{Date.now()}}`;
            track.addEventListener('load', () => {{ track.track.mode = 'showing'; }});
            video.appendChild(track);
            track.track.mode = 'showing';
            video.currentTime = time;
            if (wasPlaying) video.play();
        }}

        function onSliderChange() {{
            const shift = parseFloat(document.getElementById('shift').value);
            const scale = parseFloat(document.getElementById('scale').value);
            document.getElementById('shift-val').textContent = shift.toFixed(1) + ' s';
            document.getElementById('scale-val').textContent = (scale * 100).toFixed(1) + ' %';
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(async () => {{
                const res = await fetch(`/api/preview?scale=${{scale}}&shift=${{shift}}`);
                const data = await res.json();
                updateScoreText(data.score_pct);
                drawGraph(data.subtitle_audio);
                reloadTrack(scale, shift);
            }}, 200);
        }}

        document.getElementById('shift').addEventListener('input', onSliderChange);
        document.getElementById('scale').addEventListener('input', onSliderChange);

        async function finish(confirmed) {{
            const shift = parseFloat(document.getElementById('shift').value);
            const scale = parseFloat(document.getElementById('scale').value);
            await fetch('/api/finish', {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ confirmed, scale, shift }})
            }});
            document.body.innerHTML =
                '<h2>' + (confirmed ? '✅ Poravnava potrjena.' : '✖ Poravnava preklicana.') +
                ' To okno lahko zapreš in se vrneš v terminal.</h2>';
        }}

        document.getElementById('confirm').addEventListener('click', () => finish(true));
        document.getElementById('cancel').addEventListener('click', () => finish(false));

        loadState();
    </script>
</body>
</html>
"""
