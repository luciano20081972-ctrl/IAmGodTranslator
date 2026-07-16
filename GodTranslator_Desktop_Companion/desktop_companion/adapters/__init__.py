from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Any, Callable

from .novelfire import NovelFireAdapter


@dataclass(frozen=True)
class AdapterDescriptor:
    name: str
    display_name: str
    status: str
    notes: str = ""


class PlannedSourceAdapter:
    supports_http = False
    supports_playwright = False

    def build_options(self, **kwargs: Any) -> dict[str, Any]:
        return kwargs

    def detect(self, options: Any, log: Callable[[str], None]) -> dict[int, str]:
        raise NotImplementedError(f"{self.display_name} support is planned for a future adapter.")

    def download(self, options: Any, stop_event: Event, log: Callable[[str], None], progress: Callable[..., None]) -> dict[str, int]:
        raise NotImplementedError(f"{self.display_name} support is planned for a future adapter.")


class Shuba69Adapter(PlannedSourceAdapter):
    name = "69shuba"
    display_name = "69Shuba"


class QidianAdapter(PlannedSourceAdapter):
    name = "qidian"
    display_name = "Qidian"


class RoyalRoadAdapter(PlannedSourceAdapter):
    name = "royalroad"
    display_name = "Royal Road"


class ScribbleHubAdapter(PlannedSourceAdapter):
    name = "scribblehub"
    display_name = "ScribbleHub"


ADAPTERS = {
    "novelfire": NovelFireAdapter,
    "69shuba": Shuba69Adapter,
    "qidian": QidianAdapter,
    "royalroad": RoyalRoadAdapter,
    "scribblehub": ScribbleHubAdapter,
}


def adapter_names() -> list[str]:
    return sorted(ADAPTERS)


def adapter_descriptors() -> list[AdapterDescriptor]:
    descriptors: list[AdapterDescriptor] = []
    for name, adapter_type in sorted(ADAPTERS.items()):
        descriptors.append(
            AdapterDescriptor(
                name=name,
                display_name=getattr(adapter_type, "display_name", name),
                status="active" if name == "novelfire" else "planned",
                notes="" if name == "novelfire" else "Adapter slot is available without changing downloader core.",
            )
        )
    return descriptors
