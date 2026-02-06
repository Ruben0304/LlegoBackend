"""Tutorials GraphQL schema module."""
from .types import TutorialType, AppTarget
from .queries import TutorialQuery
from .mutations import TutorialMutation
from .inputs import CreateTutorialInput, UpdateTutorialInput

__all__ = [
    "TutorialType",
    "AppTarget",
    "TutorialQuery",
    "TutorialMutation",
    "CreateTutorialInput",
    "UpdateTutorialInput",
]
