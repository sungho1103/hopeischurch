"""
희망은교회 설교 YouTube 업로더
  - 설교 메타데이터 + m4a 파일 입력
  - 썸네일(1280x720) 자동 생성
  - FFmpeg으로 mp4 영상 생성
  - YouTube Data API v3로 업로드
"""

import os
import json
import pickle
import subprocess
import tempfile
import uuid
from pathlib import Path

from flask import (
    Flask, request, jsonify, send_file,
    render_template, session, redirect, url_for
)
from flask_cors import CORS

from PIL import Image, ImageDraw, ImageFont
import io

# YouTube API
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ─────────────────────────────────────────────
# 설정
# ─────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
UPLOAD_DIR     = BASE_DIR / "uploads"
OUTPUT_DIR     = BASE_DIR / "output"
TOKEN_PATH     = BASE_DIR / "token.pickle"
CLIENT_SECRET  = BASE_DIR / "client_secret.json"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

SCOPES         = ["https://www.googleapis.com/auth/youtube.upload"]
REDIRECT_URI   = "http://localhost:5000/oauth2callback"

# ─────────────────────────────────────────────
# Flask 앱
# ─────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", os.urandom(32))
CORS(app)

os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")  # localhost 개발용


# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────
def _find_korean_font(size: int):
    """시스템에서 한글 지원 TTF 폰트를 찾아 반환합니다."""
    candidates = [
        # Nanum (Ubuntu/Debian)
        "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/nanum/NanumBarunGothicBold.ttf",
        # Noto CJK
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Bold.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJKkr-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        # macOS
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
        "/Library/Fonts/AppleGothic.ttf",
        # Windows
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/gulim.ttc",
        # Fallback (영문)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font, draw, max_width: int) -> list[str]:
    """텍스트를 max_width에 맞게 줄바꿈합니다."""
    words = text.split()
    lines, current = [], []
    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [text]


# ─────────────────────────────────────────────
# 썸네일 생성
# ─────────────────────────────────────────────
def generate_thumbnail(
    sermon_title: str,
    preacher: str,
    date: str,
    church_name: str,
    output_path: Path,
) -> Path:
    """1280x720 YouTube 썸네일을 생성합니다."""
    W, H = 1280, 720
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    # ── 배경 그라디언트 (상: 짙은 남색 → 하: 더 짙은 남색) ──
    top_color    = (15, 23, 42)   # #0f1728
    bottom_color = (30, 27, 75)   # #1e1b4b
    for y in range(H):
        t = y / H
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * t)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * t)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * t)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── 왼쪽 강조 세로선 ──
    accent = (99, 102, 241)   # indigo-500
    draw.rectangle([0, 0, 8, H], fill=accent)

    # ── 오른쪽 장식 원형 ──
    draw.ellipse([W - 320, -100, W + 100, 320], fill=(99, 102, 241, 30))
    draw.ellipse([W - 260, -60,  W + 60,  260], fill=(67, 56, 202, 20))

    # ── 상단: 교회명 ──
    font_church = _find_korean_font(36)
    draw.text((56, 52), church_name, font=font_church, fill=(165, 180, 252))  # indigo-300

    # ── 상단 구분선 ──
    draw.line([(56, 108), (W - 56, 108)], fill=(55, 65, 81), width=1)

    # ── 중앙: 설교 제목 ──
    font_title = _find_korean_font(88)
    font_title_sm = _find_korean_font(68)

    # 제목 줄바꿈 (최대 너비 1140px)
    lines = _wrap_text(sermon_title, font_title, draw, W - 140)
    if len(lines) > 2:
        lines = _wrap_text(sermon_title, font_title_sm, draw, W - 140)
        font_use = font_title_sm
        line_h   = 90
    else:
        font_use = font_title
        line_h   = 110

    total_title_h = len(lines) * line_h
    title_start_y = H // 2 - total_title_h // 2 - 20

    for i, line in enumerate(lines):
        y = title_start_y + i * line_h
        # 그림자 효과
        draw.text((58, y + 4), line, font=font_use, fill=(0, 0, 0, 120))
        draw.text((56, y),     line, font=font_use, fill=(255, 255, 255))

    # ── 하단 구분선 ──
    draw.line([(56, H - 140), (W - 56, H - 140)], fill=(55, 65, 81), width=1)

    # ── 하단: 설교자 | 날짜 ──
    font_meta = _find_korean_font(38)

    # 설교자 (왼쪽) – 십자가 아이콘은 폰트 글리프 대신 직접 그림
    cross_color = (196, 181, 253)  # violet-300
    cx, cy = 70, H - 90
    draw.line([(cx, cy - 18), (cx, cy + 18)], fill=cross_color, width=5)
    draw.line([(cx - 12, cy - 6), (cx + 12, cy - 6)], fill=cross_color, width=5)
    draw.text((100, H - 108), preacher, font=font_meta, fill=cross_color)

    # 날짜 (오른쪽)
    bbox_date = draw.textbbox((0, 0), date, font=font_meta)
    date_w = bbox_date[2] - bbox_date[0]
    draw.text((W - 56 - date_w, H - 108), date, font=font_meta, fill=(148, 163, 184))  # slate-400

    img.save(output_path, "PNG")
    return output_path


# ─────────────────────────────────────────────
# 영상 생성 (FFmpeg)
# ─────────────────────────────────────────────
def create_video(audio_path: Path, thumbnail_path: Path, output_path: Path) -> Path:
    """썸네일 이미지 + 오디오 파일로 mp4 영상을 생성합니다."""
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(thumbnail_path),
        "-i", str(audio_path),
        "-c:v", "libx264",
        "-tune", "stillimage",
        "-c:a", "aac",
        "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1280:720",
        "-shortest",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg 오류:\n{result.stderr[-2000:]}")
    return output_path


# ─────────────────────────────────────────────
# YouTube 인증
# ─────────────────────────────────────────────
def _load_credentials() -> Credentials | None:
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, "rb") as f:
            creds = pickle.load(f)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                _save_credentials(creds)
                return creds
            except Exception:
                pass
    return None


def _save_credentials(creds: Credentials) -> None:
    with open(TOKEN_PATH, "wb") as f:
        pickle.dump(creds, f)


def get_youtube_service():
    creds = _load_credentials()
    if not creds:
        raise RuntimeError("YouTube 인증이 필요합니다. /auth/start 를 먼저 방문하세요.")
    return build("youtube", "v3", credentials=creds)


# ─────────────────────────────────────────────
# 라우트 – 프론트엔드
# ─────────────────────────────────────────────
@app.route("/")
def index():
    from datetime import date as _date
    has_secret = CLIENT_SECRET.exists()
    is_authed  = _load_credentials() is not None
    return render_template(
        "index.html",
        has_secret=has_secret,
        is_authed=is_authed,
        today=_date.today().isoformat(),
    )


# ─────────────────────────────────────────────
# 라우트 – 영상 생성
# ─────────────────────────────────────────────
@app.route("/generate", methods=["POST"])
def generate():
    try:
        sermon_title = request.form.get("sermonTitle", "").strip()
        preacher     = request.form.get("preacher",    "").strip()
        date         = request.form.get("date",        "").strip()
        church_name  = request.form.get("churchName",  "희망은교회").strip()

        if not all([sermon_title, preacher, date]):
            return jsonify({"error": "설교주제, 설교자, 날짜를 모두 입력하세요."}), 400

        audio_file = request.files.get("audioFile")
        if not audio_file:
            return jsonify({"error": "음성 파일(m4a)을 선택해주세요."}), 400

        # 파일명 안전하게: 날짜 기반 + UUID 앞 8자리
        uid  = uuid.uuid4().hex[:8]
        slug = f"{date}_{uid}"

        audio_path     = UPLOAD_DIR / f"audio_{slug}.m4a"
        thumbnail_path = OUTPUT_DIR  / f"thumbnail_{slug}.png"
        video_path     = OUTPUT_DIR  / f"sermon_{slug}.mp4"

        audio_file.save(audio_path)

        # 1) 썸네일 생성
        generate_thumbnail(sermon_title, preacher, date, church_name, thumbnail_path)

        # 2) 영상 생성
        create_video(audio_path, thumbnail_path, video_path)

        # slug를 세션에 저장해서 업로드 시 재사용
        session["last_slug"]        = slug
        session["last_meta"] = {
            "sermonTitle": sermon_title,
            "preacher":    preacher,
            "date":        date,
            "churchName":  church_name,
        }

        return jsonify({
            "success":       True,
            "slug":          slug,
            "thumbnailUrl":  f"/preview/thumbnail_{slug}.png",
            "videoUrl":      f"/download/sermon_{slug}.mp4",
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
# 라우트 – 파일 제공
# ─────────────────────────────────────────────
@app.route("/preview/<filename>")
def preview(filename):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return "파일 없음", 404
    return send_file(path, mimetype="image/png")


@app.route("/download/<filename>")
def download(filename):
    path = OUTPUT_DIR / filename
    if not path.exists():
        return "파일 없음", 404
    return send_file(path, as_attachment=True)


# ─────────────────────────────────────────────
# 라우트 – YouTube OAuth2
# ─────────────────────────────────────────────
@app.route("/auth/start")
def auth_start():
    if not CLIENT_SECRET.exists():
        return (
            "<h2>client_secret.json 파일이 없습니다.</h2>"
            "<p>Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 만들고<br>"
            "client_secret.json 파일을 이 앱 폴더에 넣어주세요.</p>",
            400,
        )
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["oauth_state"] = state
    return redirect(auth_url)


@app.route("/oauth2callback")
def oauth2callback():
    state = session.get("oauth_state")
    flow  = Flow.from_client_secrets_file(
        str(CLIENT_SECRET),
        scopes=SCOPES,
        state=state,
        redirect_uri=REDIRECT_URI,
    )
    flow.fetch_token(authorization_response=request.url)
    _save_credentials(flow.credentials)
    return redirect(url_for("index") + "?authed=1")


@app.route("/auth/status")
def auth_status():
    return jsonify({"authed": _load_credentials() is not None})


@app.route("/auth/revoke", methods=["POST"])
def auth_revoke():
    if TOKEN_PATH.exists():
        TOKEN_PATH.unlink()
    return jsonify({"success": True})


# ─────────────────────────────────────────────
# 라우트 – YouTube 업로드
# ─────────────────────────────────────────────
@app.route("/upload", methods=["POST"])
def upload():
    try:
        data = request.get_json(force=True)
        slug = data.get("slug") or session.get("last_slug")
        meta = data.get("meta") or session.get("last_meta", {})

        if not slug:
            return jsonify({"error": "생성된 영상이 없습니다. 먼저 영상을 생성하세요."}), 400

        video_path     = OUTPUT_DIR / f"sermon_{slug}.mp4"
        thumbnail_path = OUTPUT_DIR / f"thumbnail_{slug}.png"

        if not video_path.exists():
            return jsonify({"error": "영상 파일을 찾을 수 없습니다. 다시 생성해주세요."}), 400

        sermon_title = meta.get("sermonTitle", "")
        preacher     = meta.get("preacher",    "")
        date         = meta.get("date",        "")
        church_name  = meta.get("churchName",  "희망은교회")

        youtube = get_youtube_service()

        # ── 영상 메타데이터 ──
        yt_title = f"[설교] {sermon_title} | {preacher} | {date}"[:100]
        yt_desc  = (
            f"교회: {church_name}\n"
            f"설교자: {preacher}\n"
            f"날짜: {date}\n"
            f"제목: {sermon_title}\n\n"
            f"희망은교회 주일예배 설교입니다."
        )

        body = {
            "snippet": {
                "title":       yt_title,
                "description": yt_desc,
                "tags":        ["설교", church_name, preacher, "주일예배", "기독교"],
                "categoryId":  "29",   # Nonprofits & Activism
                "defaultLanguage": "ko",
            },
            "status": {
                "privacyStatus": data.get("privacy", "public"),
            },
        }

        media   = MediaFileUpload(str(video_path), mimetype="video/mp4",
                                  chunksize=4 * 1024 * 1024, resumable=True)
        yt_req  = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )

        # 청크 업로드
        response = None
        while response is None:
            _, response = yt_req.next_chunk()

        video_id = response["id"]

        # ── 썸네일 업로드 ──
        if thumbnail_path.exists():
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(str(thumbnail_path), mimetype="image/png"),
            ).execute()

        return jsonify({
            "success":  True,
            "videoId":  video_id,
            "videoUrl": f"https://www.youtube.com/watch?v={video_id}",
        })

    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401
    except HttpError as e:
        return jsonify({"error": f"YouTube API 오류: {e.reason}"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 50)
    print("희망은교회 YouTube 업로더")
    print("http://localhost:5000  에서 실행 중")
    print("=" * 50)
    app.run(debug=True, port=5000)
