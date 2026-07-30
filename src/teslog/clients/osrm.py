from typing import Any

import httpx

from teslog.config import get_settings


class OSRMError(RuntimeError):
    pass


class OSRMClient:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url if base_url is not None else settings.osrm_base_url).rstrip("/")

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    async def route_distance_km(
        self, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
    ) -> float:
        if not self.enabled:
            raise OSRMError("OSRM_BASE_URL is not configured")

        path = f"/route/v1/driving/{origin_lon},{origin_lat};{dest_lon},{dest_lat}"
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(f"{self.base_url}{path}", params={"overview": "false"})
            response.raise_for_status()
            data: dict[str, Any] = response.json()

        if data.get("code") != "Ok":
            raise OSRMError(f"OSRM error: {data.get('code')} {data.get('message', '')}".strip())

        routes = data.get("routes") or []
        if not routes:
            raise OSRMError("OSRM returned no routes")

        meters = routes[0].get("distance", 0)
        return meters / 1000.0
