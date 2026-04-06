from __future__ import annotations

import logging

from ai.src.config.settings import ARX_MODEL_PATH
from ai.src.inference.predictor import ARXController

log = logging.getLogger(__name__)


class ARXControllerService:
    def __init__(self) -> None:
        self._controller: ARXController | None = None

    @property
    def loaded(self) -> bool:
        return self._controller is not None

    @property
    def controller(self) -> ARXController | None:
        return self._controller

    def load(self) -> bool:
        if not ARX_MODEL_PATH.exists():
            log.warning("ARX model file not found: %s", ARX_MODEL_PATH)
            self._controller = None
            return False
        try:
            self._controller = ARXController()
            log.info("ARX controller loaded")
            return True
        except Exception as exc:
            log.exception("Failed to load ARX controller: %s", exc)
            self._controller = None
            return False

    def reset(self) -> None:
        if self._controller is not None:
            self._controller.reset()

    @property
    def seed_steps(self) -> int:
        return self._controller.model.order if self._controller is not None else 0

    @property
    def buffer_ready(self) -> bool:
        return bool(self._controller and self._controller.buffer_ready)

    @property
    def buffer_count(self) -> int:
        return self._controller.buffer_count if self._controller else 0