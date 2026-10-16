"""Weight Magazine Protocol and Runtime Package."""
from experiments.uow_magazine_1.magazine.manifest import MagazineEntry, MagazineManifest, PROTOCOL_VERSION
from experiments.uow_magazine_1.magazine.registry import MagazineRegistry
from experiments.uow_magazine_1.magazine.adapter_manager import MagazineAdapterManager

__all__ = [
    "MagazineEntry",
    "MagazineManifest",
    "PROTOCOL_VERSION",
    "MagazineRegistry",
    "MagazineAdapterManager",
]
