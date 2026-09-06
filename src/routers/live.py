"""Public process liveness probe with no dependency calls."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/live")
async def live() -> dict[str, str]:
    """Confirm that the API process and event loop can serve requests."""

    return {"status": "alive"}
