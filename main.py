import uuid, threading
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://babypinmanager.lovable.app/"],  # depois a gente restringe pro seu domínio do Lovable
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE = Path("downloads")
BASE.mkdir(exist_ok=True)

jobs = {}

class CreateJob(BaseModel):
    urls: list[str]

def download_one(url: str, out_dir: Path, hook):
    ydl_opts = {
        "ffmpeg_location": r"C:\Users\marco\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.0.1-full_build\bin",
        "outtmpl": str(out_dir / "%(title).120s [%(id)s].%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "max_filesize": 20 * 1024 * 1024,  # 20 MB
        "format": "bv*[ext=mp4][filesize<=20M]+ba[ext=m4a][filesize<=20M]/b[ext=mp4][filesize<=20M]/bv*+ba/b",
        "merge_output_format": "mp4",
        "progress_hooks": [hook],
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

def run_job(job_id: str, urls: list[str]):
    out_dir = BASE / job_id
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs[job_id]["status"] = "running"

    for i, url in enumerate(urls):
        item = jobs[job_id]["items"][i]

        def hook(d, item=item):
            if d.get("status") == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate")
                done = d.get("downloaded_bytes")
                item["status"] = "downloading"
                if total and done is not None:
                    item["progress"] = min(1.0, done / total)
            elif d.get("status") == "finished":
                item["status"] = "finished"
                item["progress"] = 1.0
                fn = d.get("filename")
                if fn:
                    item["file"] = Path(fn).name

        try:
            download_one(url, out_dir, hook)
        except Exception as e:
            item["status"] = "error"
            item["error"] = str(e)

    jobs[job_id]["status"] = "done"

@app.post("/jobs")
def create_job(payload: CreateJob):
    urls = [u.strip() for u in payload.urls if u.strip()]
    if not urls:
        raise HTTPException(400, "urls vazia")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "items": [{"url": u, "status":"queued", "progress":0.0, "file":None, "error":None} for u in urls]
    }

    threading.Thread(target=run_job, args=(job_id, urls), daemon=True).start()
    return {"job_id": job_id}

@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(404, "job não encontrado")
    return jobs[job_id]

@app.get("/jobs/{job_id}/files/{filename}")
def get_file(job_id: str, filename: str):
    path = BASE / job_id / filename
    if not path.exists():
        raise HTTPException(404, "arquivo não encontrado")
    return FileResponse(path)
