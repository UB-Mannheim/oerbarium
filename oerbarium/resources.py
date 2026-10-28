import json
from functools import cached_property
from importlib.resources import files

from .config import (
    FIELD_EXPLANATIONS_FILENAME,
    HFS_MAPPING_FILENAME,
    METADATA_PACKAGE,
    PICKLISTS_FILENAME,
)

ATTRIBUTE_KEY = "attribute name"


def _load(filename: str):
    """Read one JSON file shipped inside the package."""
    return json.loads(
        files(METADATA_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
    )


class DisciplineIndex:
    """The Hochschulfächersystematik: German subject name -> IRI."""

    def __init__(self, filename: str = HFS_MAPPING_FILENAME):
        self._filename = filename

    @cached_property
    def _mapping(self) -> dict[str, str]:
        return _load(self._filename)

    def search(self, query: str, limit: int = 15) -> dict[str, str]:
        """Subject names containing `query` (case-insensitive), name -> IRI."""
        needle = query.strip().casefold()
        if not needle:
            return {}
        hits = {
            name: iri
            for name, iri in self._mapping.items()
            if needle in name.casefold()
        }
        return dict(list(hits.items())[:limit])


class PicklistCatalog:
    """Allowed picklist items and controlled vocabularies, grouped by field."""

    def __init__(self, filename: str = PICKLISTS_FILENAME):
        self._filename = filename

    @cached_property
    def _by_field(self) -> dict[str, list[dict]]:
        grouped: dict[str, list[dict]] = {}
        for entry in _load(self._filename):
            grouped.setdefault(entry[ATTRIBUTE_KEY], []).append(entry)
        return grouped

    def fields(self) -> list[str]:
        """Field names that have a picklist."""
        return sorted(self._by_field)

    def for_field(self, field: str) -> list[dict]:
        """Picklist entries for one field, empty if the field has none."""
        return self._by_field.get(field, [])


class FieldExplanations:
    """Prose descriptions, constraints and examples for each metadata field."""

    def __init__(self, filename: str = FIELD_EXPLANATIONS_FILENAME):
        self._filename = filename

    @cached_property
    def _by_field(self) -> dict[str, dict]:
        return {entry[ATTRIBUTE_KEY]: entry for entry in _load(self._filename)}

    def fields(self) -> list[str]:
        """Field names that have an explanation."""
        return sorted(self._by_field)

    def for_field(self, field: str) -> dict | None:
        """Explanation of one field, None if the field is unknown."""
        return self._by_field.get(field)
