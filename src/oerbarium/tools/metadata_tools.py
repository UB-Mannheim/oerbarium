import json

from ..resources import DisciplineIndex, FieldExplanations, PicklistCatalog
from .base import LlmTool

MAX_DISCIPLINE_HITS = 5


def _dump(payload) -> str:
    return json.dumps(payload, ensure_ascii=False)


class LookupDisciplineTool(LlmTool):
    """Resolve a subject term to Hochschulfächersystematik IRIs."""

    name = "lookup_discipline"
    description = (
        "Look up IRIs of the German University Subject Classification System "
        "(Hochschulfächersystematik) by subject name. Query with a German "
        "subject term or a fragment of one, e.g. 'Informatik', 'Medizin', "
        "'Kunst'. Returns matching subject names with their IRIs. Always use "
        "this before filling the Discipline field; never invent an IRI."
    )

    def __init__(self, index: DisciplineIndex | None = None):
        self._index = index or DisciplineIndex()

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "German subject name or fragment to search for.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    def run(self, query: str = "", **_) -> str:
        matches = self._index.search(query, limit=MAX_DISCIPLINE_HITS)
        if not matches:
            return _dump(
                {
                    "query": query,
                    "matches": {},
                    "hint": "No match. Retry with a shorter or broader German term.",
                }
            )
        return _dump({"query": query, "matches": matches})


class GetPicklistTool(LlmTool):
    """List the allowed values of a field with a controlled vocabulary."""

    name = "get_picklist"
    description = (
        "Return the allowed values (picklist items and controlled "
        "vocabularies) for one metadata field, each with its definition and "
        "source IRI. Use it whenever you are unsure whether a value is valid."
    )

    def __init__(self, catalog: PicklistCatalog | None = None):
        self._catalog = catalog or PicklistCatalog()

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "description": "Name of the metadata field.",
                    "enum": self._catalog.fields(),
                }
            },
            "required": ["field"],
            "additionalProperties": False,
        }

    def run(self, field: str = "", **_) -> str:
        entries = self._catalog.for_field(field)
        if not entries:
            return _dump(
                {
                    "field": field,
                    "values": [],
                    "hint": f"No picklist. Fields with one: {self._catalog.fields()}",
                }
            )
        return _dump({"field": field, "values": entries})


class ExplainFieldTool(LlmTool):
    """Return description, constraints and examples of a metadata field."""

    name = "explain_field"
    description = (
        "Return the full documentation of one metadata field: what it means, "
        "the required value format, examples and caveats. Use it when the "
        "expected formatting of a field is unclear."
    )

    def __init__(self, explanations: FieldExplanations | None = None):
        self._explanations = explanations or FieldExplanations()

    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "field": {
                    "type": "string",
                    "description": "Name of the metadata field.",
                    "enum": self._explanations.fields(),
                }
            },
            "required": ["field"],
            "additionalProperties": False,
        }

    def run(self, field: str = "", **_) -> str:
        explanation = self._explanations.for_field(field)
        if explanation is None:
            return _dump(
                {
                    "field": field,
                    "explanation": None,
                    "hint": f"Unknown field. Known fields: {self._explanations.fields()}",
                }
            )
        return _dump(explanation)
