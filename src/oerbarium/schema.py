from pydantic import BaseModel, ConfigDict


class DaliaInterchangeFormat(BaseModel):
    """
    The 17 DALIA Interchange Format v1.4 metadata fields describing a single
    Open Educational Resource.

    Field names match the schema keys expected in the LLM's JSON reply, so this
    model is both the API contract (via :meth:`response_format`) and the
    validator for what comes back.
    """
    model_config = ConfigDict(extra="forbid")

    Authors: str
    License: str
    Link: str
    Title: str
    AccessibilityFeature: str | None = None
    Community: str | None = None
    Description: str | None = None
    Discipline: str | None = None
    FileFormat: str | None = None
    Keywords: str | None = None
    Language: str | None = None
    LearningResourceType: str | None = None
    MediaType: str | None = None
    ProficiencyLevel: str | None = None
    PublicationDate: str | None = None
    TargetGroup: str | None = None
    Teaches: str | None = None

    @classmethod
    def json_schema(cls) -> dict:
        """
        JSON schema of the reply, tightened for strict structured output.

        Strict mode wants every property listed in ``required`` and has no use
        for ``default``, while the model itself still accepts missing optional
        keys. So the wire schema asks for all 17 keys (nullable ones may be
        null) without making the Python side stricter than it needs to be.
        """
        schema = cls.model_json_schema()
        for prop in schema.get("properties", {}).values():
            prop.pop("default", None)
        schema["required"] = list(schema.get("properties", {}))
        schema["additionalProperties"] = False
        return schema

    @classmethod
    def response_format(cls) -> dict:
        """
        The OpenAI `response_format` argument enforcing this schema.
        """
        return {
            "type": "json_schema",
            "json_schema": {
                "name": "oer_metadata",
                "schema": cls.json_schema(),
                "strict": True,
            },
        }
