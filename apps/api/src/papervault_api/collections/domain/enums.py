from enum import StrEnum


class CollectionKind(StrEnum):
    DYNAMIC = "dynamic"
    MANUAL = "manual"


class CollectionView(StrEnum):
    GRID = "grid"
    LIST = "list"
