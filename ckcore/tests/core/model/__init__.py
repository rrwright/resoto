from typing import Optional

from core.model.model import Model, Kind
from core.model.model_handler import ModelHandler


class ModelHandlerStatic(ModelHandler):
    def __init__(self, model: Model):
        self.model = model

    async def load_model(self) -> Model:
        return self.model

    async def uml_image(self, show_packages: Optional[list[str]] = None, output: str = "svg") -> bytes:
        raise NotImplemented

    async def update_model(self, kinds: list[Kind]) -> Model:
        self.model = Model.from_kinds(kinds)
        return self.model