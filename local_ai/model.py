import threading
from typing import Any

from .config import Settings


class OpenELMRuntime:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._model: Any = None
        self._tokenizer: Any = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self.loaded:
            return
        from mlx_lm import load

        self._model, self._tokenizer = load(
            self.settings.model_id, tokenizer_config={"trust_remote_code": False}
        )

    def generate(self, prompt: str, max_tokens: int | None = None, temperature: float = 0.2) -> str:
        self.load()
        from mlx_lm import generate

        budget = max_tokens or self.settings.max_new_tokens
        with self._lock:
            try:
                from mlx_lm.sample_utils import make_sampler

                sampler = make_sampler(temp=temperature, top_p=0.9)
                output = generate(
                    self._model,
                    self._tokenizer,
                    prompt=prompt,
                    max_tokens=budget,
                    sampler=sampler,
                    verbose=False,
                ).strip()
            except (ImportError, TypeError):
                output = generate(
                    self._model,
                    self._tokenizer,
                    prompt=prompt,
                    max_tokens=budget,
                    temp=temperature,
                    verbose=False,
                ).strip()
        for marker in ("\nQuestion:", "\nInstruction:", "\nRetrieved evidence:", "\n###"):
            output = output.split(marker, 1)[0]
        return output.strip()
