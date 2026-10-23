"""文生图管理器"""
import json
import time
import urllib.request as request
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from core.runtime.cancellation import current_token, check_cancelled, run_async


class T2IAdapter:
    """T2I 适配器基类"""
    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        raise NotImplementedError


class ComfyUIAdapter(T2IAdapter):
    """ComfyUI 适配器"""
    DEFAULT_POLL_ATTEMPTS = 60
    DEFAULT_POLL_INTERVAL = 1.0

    DEFAULT_OPTIONS = {
        "checkpoint": "v1-5-pruned-emaonly.ckpt",
        "width": 512,
        "height": 512,
        "steps": 20,
        "cfg": 8.0,
        "sampler_name": "euler",
        "scheduler": "normal",
        "negative_prompt": "",
        "seed": 1,
    }

    def __init__(self, api_url: str = "http://127.0.0.1:8188", **kwargs):
        self.api_url = self._normalize_api_url(api_url)
        self.kwargs = kwargs

    @staticmethod
    def _normalize_api_url(api_url: str) -> str:
        return api_url.rstrip("/")

    def _workflow_options(self, **kwargs) -> Dict[str, Any]:
        options = dict(self.DEFAULT_OPTIONS)
        options.update(self.kwargs)
        options.update(kwargs)
        return options

    def _build_workflow(self, prompt: str, **kwargs) -> Dict[str, Dict[str, Any]]:
        """构建 ComfyUI 最小文生图 workflow。"""
        options = self._workflow_options(**kwargs)
        return {
            "4": {
                "class_type": "CheckpointLoaderSimple",
                "inputs": {
                    "ckpt_name": options["checkpoint"],
                },
            },
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {
                    "width": options["width"],
                    "height": options["height"],
                    "batch_size": 1,
                },
            },
            "6": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": prompt,
                    "clip": ["4", 1],
                },
            },
            "7": {
                "class_type": "CLIPTextEncode",
                "inputs": {
                    "text": options["negative_prompt"],
                    "clip": ["4", 1],
                },
            },
            "3": {
                "class_type": "KSampler",
                "inputs": {
                    "seed": options["seed"],
                    "steps": options["steps"],
                    "cfg": options["cfg"],
                    "sampler_name": options["sampler_name"],
                    "scheduler": options["scheduler"],
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
            },
            "8": {
                "class_type": "VAEDecode",
                "inputs": {
                    "samples": ["3", 0],
                    "vae": ["4", 2],
                },
            },
            "9": {
                "class_type": "SaveImage",
                "inputs": {
                    "filename_prefix": "yayu",
                    "images": ["8", 0],
                },
            },
        }

    def _build_prompt_payload(self, prompt: str, **kwargs) -> Dict[str, Dict[str, Dict[str, Any]]]:
        return {"prompt": self._build_workflow(prompt, **kwargs)}

    @staticmethod
    def _extract_prompt_id(response: Dict[str, Any]) -> str:
        prompt_id = response.get("prompt_id")
        if not prompt_id:
            raise ValueError("ComfyUI response missing prompt_id")
        return str(prompt_id)

    @staticmethod
    def _build_prompt_handle(prompt_id: str) -> str:
        return f"comfyui://prompt/{prompt_id}"

    @staticmethod
    def _build_image_handle(prompt_id: str, image: Dict[str, Any]) -> str:
        return f"comfyui://image/{prompt_id}/{image['filename']}"

    def _output_dir(self) -> Path:
        return Path(self.kwargs.get("output_dir", "data/cg/generated"))

    def _build_view_url(self, image: Dict[str, Any]) -> str:
        query = urlencode({
            "filename": image.get("filename", ""),
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        })
        return f"{self.api_url}/view?{query}"

    def _build_cache_path(self, prompt_id: str, image: Dict[str, Any]) -> Path:
        safe_prompt_id = Path(prompt_id).name.replace("/", "_").replace("\\", "_")
        safe_filename = Path(str(image["filename"])).name
        return self._output_dir() / f"{safe_prompt_id}-{safe_filename}"

    def _download_image(self, prompt_id: str, image: Dict[str, Any]) -> Path:
        req = request.Request(self._build_view_url(image), method="GET")
        with request.urlopen(req, timeout=self._request_timeout()) as response:
            content = response.read()
        cache_path = self._build_cache_path(prompt_id, image)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(content)
        return cache_path

    def _request_timeout(self) -> float:
        return float(self.kwargs.get("timeout", 10))

    def _poll_attempts(self) -> int:
        return max(0, int(self.kwargs.get("poll_attempts", self.DEFAULT_POLL_ATTEMPTS)))

    def _poll_interval(self) -> float:
        return max(0.0, float(self.kwargs.get("poll_interval", self.DEFAULT_POLL_INTERVAL)))

    def _post_prompt(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            f"{self.api_url}/prompt",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=self._request_timeout()) as response:
            return json.loads(response.read().decode("utf-8"))

    def _get_history(self, prompt_id: str) -> Dict[str, Any]:
        req = request.Request(
            f"{self.api_url}/history/{quote(prompt_id, safe='')}",
            method="GET",
        )
        with request.urlopen(req, timeout=self._request_timeout()) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _extract_first_image(history: Dict[str, Any], prompt_id: str) -> Optional[Dict[str, Any]]:
        if not isinstance(history, dict):
            return None

        prompt_history = history.get(prompt_id)
        if not isinstance(prompt_history, dict):
            return None

        outputs = prompt_history.get("outputs")
        if not isinstance(outputs, dict):
            return None

        for output in outputs.values():
            if not isinstance(output, dict):
                continue

            images = output.get("images")
            if not isinstance(images, list):
                continue

            for image in images:
                if not isinstance(image, dict):
                    continue

                filename = image.get("filename")
                if isinstance(filename, str) and filename:
                    return image
        return None

    def _poll_first_image(self, prompt_id: str) -> Optional[Dict[str, Any]]:
        attempts = self._poll_attempts()
        interval = self._poll_interval()

        for attempt in range(attempts):
            history = self._get_history(prompt_id)
            image = self._extract_first_image(history, prompt_id)
            if image is not None:
                return image

            if attempt < attempts - 1:
                time.sleep(interval)

        return None

    def generate(self, prompt: str, **kwargs) -> Optional[str]:
        if current_token() is not None:
            return self._generate_cancellable(prompt, **kwargs)
        try:
            payload = self._build_prompt_payload(prompt, **kwargs)
            response = self._post_prompt(payload)
            prompt_id = self._extract_prompt_id(response)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[ComfyUI] 提交失败: {e}")
            return None

        prompt_handle = self._build_prompt_handle(prompt_id)
        try:
            image = self._poll_first_image(prompt_id)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[ComfyUI] 查询历史失败: {e}")
            return prompt_handle

        if image is None:
            return prompt_handle

        image_handle = self._build_image_handle(prompt_id, image)
        try:
            return str(self._download_image(prompt_id, image))
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as e:
            print(f"[ComfyUI] 下载图片失败: {e}")
            return image_handle

    def _generate_cancellable(self, prompt: str, **kwargs) -> Optional[str]:
        import asyncio
        import httpx

        async def generate():
            async with httpx.AsyncClient(timeout=self._request_timeout()) as client:
                try:
                    response = await client.post(f"{self.api_url}/prompt", json=self._build_prompt_payload(prompt, **kwargs))
                    response.raise_for_status()
                    prompt_id = self._extract_prompt_id(response.json())
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    print(f"[ComfyUI] 提交失败: {exc}")
                    return None
                image = None
                try:
                    for attempt in range(self._poll_attempts()):
                        check_cancelled()
                        response = await client.get(f"{self.api_url}/history/{quote(prompt_id, safe='')}")
                        response.raise_for_status()
                        image = self._extract_first_image(response.json(), prompt_id)
                        if image:
                            break
                        if attempt < self._poll_attempts() - 1:
                            await asyncio.sleep(self._poll_interval())
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    print(f"[ComfyUI] 查询历史失败: {exc}")
                    return self._build_prompt_handle(prompt_id)
                if image is None:
                    return self._build_prompt_handle(prompt_id)
                try:
                    response = await client.get(self._build_view_url(image))
                    response.raise_for_status()
                    check_cancelled()
                    cache_path = self._build_cache_path(prompt_id, image)
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_bytes(response.content)
                    return str(cache_path)
                except (httpx.HTTPError, OSError, ValueError) as exc:
                    print(f"[ComfyUI] 下载图片失败: {exc}")
                    return self._build_image_handle(prompt_id, image)

        return run_async(generate)


class T2IAdapterFactory:
    """T2I 适配器工厂"""
    _adapters: Dict[str, type] = {
        "comfyui": ComfyUIAdapter,
    }

    @classmethod
    def register(cls, name: str, adapter_cls: type):
        cls._adapters[name] = adapter_cls

    @classmethod
    def create_adapter(cls, adapter_name: str, **kwargs) -> T2IAdapter:
        adapter_cls = cls._adapters.get(adapter_name.lower())
        if not adapter_cls:
            raise ValueError(f"未知的 T2I 适配器: {adapter_name}")
        return adapter_cls(**kwargs)


class T2IManager:
    """文生图管理器"""
    def __init__(self, adapter: T2IAdapter):
        self.adapter = adapter

    def generate_image(self, prompt: str, **kwargs) -> Optional[str]:
        return self.adapter.generate(prompt, **kwargs)
