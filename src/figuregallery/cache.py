from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PyQt6.QtGui import QImage


class ImageCache:
    def __init__(self, max_items: int = 5) -> None:
        self._max_items = max_items
        self._items: OrderedDict[str, QImage] = OrderedDict()

    def get(self, path: Path) -> QImage | None:
        key = str(path.resolve())
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def put(self, path: Path, image: QImage) -> None:
        key = str(path.resolve())
        self._items[key] = image
        self._items.move_to_end(key)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()
