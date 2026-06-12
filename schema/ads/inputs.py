"""GraphQL input types for ad campaign mutations + a dict converter for storage."""

from typing import List, Optional

import strawberry


@strawberry.input
class CreativeBackgroundInput:
    type: str = "gradient"
    colors: List[str] = strawberry.field(default_factory=lambda: ["#023133", "#0A5C3F"])
    angle: int = 45
    imagePath: Optional[str] = None


@strawberry.input
class CreativeTextInput:
    role: str
    value: str
    color: str = "#FFFFFF"
    size: str = "md"
    weight: str = "regular"


@strawberry.input
class CreativeBadgeInput:
    text: str
    style: str = "offer"


@strawberry.input
class CreativeCTAInput:
    label: str = "Ver tienda"
    deeplink: Optional[str] = None


@strawberry.input
class CreativeSpecInput:
    aspectRatio: str = "wide"
    animationPreset: str = "none"
    background: Optional[CreativeBackgroundInput] = None
    texts: List[CreativeTextInput] = strawberry.field(default_factory=list)
    badge: Optional[CreativeBadgeInput] = None
    cta: Optional[CreativeCTAInput] = None


@strawberry.input
class CreateAdCampaignInput:
    businessId: str
    branchId: str
    name: str
    placement: str  # "destacado" | "oferta"
    durationDays: int
    creative: CreativeSpecInput


@strawberry.input
class UpdateAdCampaignInput:
    name: Optional[str] = None
    durationDays: Optional[int] = None
    creative: Optional[CreativeSpecInput] = None


def creative_input_to_dict(creative: CreativeSpecInput) -> dict:
    """Convert a CreativeSpecInput into the dict stored on the campaign."""
    bg = creative.background
    background = {
        "type": bg.type if bg else "gradient",
        "colors": list(bg.colors) if bg else ["#023133", "#0A5C3F"],
        "angle": bg.angle if bg else 45,
        "imagePath": bg.imagePath if bg else None,
    }
    return {
        "aspectRatio": creative.aspectRatio,
        "animationPreset": creative.animationPreset,
        "background": background,
        "texts": [
            {
                "role": t.role,
                "value": t.value,
                "color": t.color,
                "size": t.size,
                "weight": t.weight,
            }
            for t in creative.texts
        ],
        "badge": {"text": creative.badge.text, "style": creative.badge.style}
        if creative.badge
        else None,
        "cta": {"label": creative.cta.label, "deeplink": creative.cta.deeplink}
        if creative.cta
        else None,
    }
