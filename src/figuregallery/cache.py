from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PyQt6.QtGui import QImage


class ImageCache:
    def __init__(self, max_items: int = 32) -> None:
        self._max_items = max(1, max_items)
        self._items: OrderedDict[str, QImage] = OrderedDict()

    @property
    def max_items(self) -> int:
        return self._max_items

    def set_max_items(self, max_items: int) -> None:
        self._max_items = max(1, max_items)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)

    def __len__(self) -> int:
        return len(self._items)

    def _key(self, path: Path, *, pdf_dpi: int = 200, trim: bool = False) -> str:
        return f"{path.resolve()}|{pdf_dpi}|{int(trim)}"

    def get(self, path: Path, *, pdf_dpi: int = 200, trim: bool = False) -> QImage | None:
        key = self._key(path, pdf_dpi=pdf_dpi, trim=trim)
        if key not in self._items:
            return None
        self._items.move_to_end(key)
        return self._items[key]

    def put(self, path: Path, image: QImage, *, pdf_dpi: int = 200, trim: bool = False) -> None:
        key = self._key(path, pdf_dpi=pdf_dpi, trim=trim)
        self._items[key] = image
        self._items.move_to_end(key)
        while len(self._items) > self._max_items:
            self._items.popitem(last=False)

    def clear(self) -> None:
        self._items.clear()
