import base64
from io import BytesIO
from pathlib import Path
from typing import Any

import httpx


class VisionRuntime:
    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "llama3.2-vision"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._cache: dict[str, str] = {}

    def status(self) -> dict[str, Any]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=2.0)
            if response.status_code == 200:
                names = [item.get("name", "") for item in response.json().get("models", [])]
                return {
                    "available": True,
                    "provider": "ollama",
                    "model": self.model,
                    "installed": any(self.model in name for name in names),
                    "models": names,
                }
        except Exception:
            pass

        try:
            response = httpx.get(f"{self.base_url}/v1/models", timeout=2.0)
            if response.status_code == 200:
                names = [item.get("id", "") for item in response.json().get("data", [])]
                return {
                    "available": True,
                    "provider": "openai_compatible",
                    "model": self.model,
                    "installed": any(self.model in name for name in names),
                    "models": names,
                }
        except Exception:
            pass

        return {
            "available": False,
            "provider": "local_fallback",
            "model": self.model,
            "fallback_ready": True,
            "note": "Server offline; fallback PIL visual analyzer aktif.",
        }

    def analyze_bytes(self, image: bytes, prompt: str = "") -> str:
        if len(image) > 12 * 1024 * 1024:
            raise ValueError("Image exceeds 12 MB")
        import hashlib
        cache_key = hashlib.sha256(image + prompt.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

        # 1. Ollama
        try:
            payload = {
                "model": self.model,
                "stream": False,
                "messages": [{
                    "role": "user",
                    "content": prompt or "Jelaskan gambar ini secara detail dan akurat dalam Bahasa Indonesia.",
                    "images": [base64.b64encode(image).decode("ascii")],
                }],
                "options": {"temperature": 0.1},
            }
            resp = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=60.0)
            if resp.status_code == 200:
                content = str(resp.json().get("message", {}).get("content", "")).strip()
                if content:
                    return f"[Vision Model: {self.model}]\n{content}"
        except Exception:
            pass

        # 2. OpenAI-compatible
        try:
            b64_img = base64.b64encode(image).decode("ascii")
            data_uri = f"data:image/jpeg;base64,{b64_img}"
            payload = {
                "model": self.model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt or "Jelaskan gambar ini secara detail."},
                        {"type": "image_url", "image_url": {"url": data_uri}},
                    ],
                }],
                "temperature": 0.1,
            }
            resp = httpx.post(f"{self.base_url}/v1/chat/completions", json=payload, timeout=60.0)
            if resp.status_code == 200:
                choices = resp.json().get("choices", [])
                if choices:
                    content = str(choices[0].get("message", {}).get("content", "")).strip()
                    if content:
                        return f"[Vision Model: {self.model}]\n{content}"
        except Exception:
            pass

        # 3. Fallback PIL
        return self._local_pil_inspect(image, prompt)

    def _local_pil_inspect(self, image_bytes: bytes, prompt: str) -> str:
        try:
            from PIL import Image
            img = Image.open(BytesIO(image_bytes))
            width, height = img.size
            fmt = img.format or "Unknown"
            mode = img.mode
            aspect = round(width / height, 2) if height else 1.0

            rgb_img = img.convert("RGB")
            thumb = rgb_img.resize((16, 16))
            pixels = list(thumb.getdata())
            r_avg = int(sum(p[0] for p in pixels) / len(pixels))
            g_avg = int(sum(p[1] for p in pixels) / len(pixels))
            b_avg = int(sum(p[2] for p in pixels) / len(pixels))

            return (
                f"[Local Visual Inspector (Offline)]: Gambar {fmt} ({width}x{height} px, rasio {aspect}:1, mode {mode}). "
                f"Dominasi warna RGB rata-rata: #{r_avg:02x}{g_avg:02x}{b_avg:02x}. "
                f"Catatan: Server Vision sedang offline ({self.base_url}), properti visual diverifikasi secara lokal."
            )
        except Exception:
            return (
                f"[Local Visual Inspector (Offline)]: File gambar ({len(image_bytes)} bytes) terverifikasi. "
                f"Catatan: Server Vision offline ({self.base_url})."
            )

    def analyze_path(self, path: Path, prompt: str = "") -> str:
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
            raise ValueError("Unsupported image type")
        return self.analyze_bytes(path.read_bytes(), prompt)
