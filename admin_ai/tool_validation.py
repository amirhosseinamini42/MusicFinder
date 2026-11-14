"""Strict validation and execution boundary for AI tool calls."""

from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, ValidationError, field_validator

import mf_policy as policy
from admin_ai.tools import READ_ONLY_TOOLS


class EmptyToolArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchTracksArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: StrictStr = Field(default="", max_length=80)
    status: StrictStr | None = None
    limit: StrictInt = Field(default=20, ge=1, le=50)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        if value is not None and value not in policy.STATUSES:
            raise ValueError("Invalid track status")
        return value


class TrackDetailsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    track_id: UUID


TOOL_ARGUMENT_MODELS = {
    "get_dashboard_stats": EmptyToolArgs,
    "get_track_status_summary": EmptyToolArgs,
    "search_tracks": SearchTracksArgs,
    "get_track_details": TrackDetailsArgs,
}


def validate_and_execute_tool(name: str, arguments: Any) -> dict:
    """Execute only explicitly allowlisted tools with validated arguments."""

    if not isinstance(name, str) or name not in READ_ONLY_TOOLS:
        raise HTTPException(status_code=400, detail="tool_not_allowed")

    if not isinstance(arguments, dict):
        raise HTTPException(status_code=422, detail="invalid_tool_arguments")

    schema = TOOL_ARGUMENT_MODELS[name]

    try:
        validated = schema.model_validate(arguments)
    except ValidationError:
        raise HTTPException(status_code=422, detail="invalid_tool_arguments")

    clean_arguments = validated.model_dump(mode="json")

    return READ_ONLY_TOOLS[name](**clean_arguments)
