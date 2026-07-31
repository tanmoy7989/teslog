"""Clients for the external services Teslog talks to: TeslaMateApi and OSRM."""

from datetime import datetime
from typing import Any

import httpx

from teslog.config import get_settings


class TeslaMateApiClient:
    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        self.base_url = (base_url or settings.teslamate_api_url).rstrip("/")
        self.car_id = settings.teslog_car_id

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.base_url}{path}", params=params)
            response.raise_for_status()
            return response.json()

    async def health(self) -> dict[str, Any]:
        return await self._get("/api/healthz")

    async def get_cars(self) -> list[dict[str, Any]]:
        data = await self._get("/api/v1/cars")
        return data.get("data", data) if isinstance(data, dict) else data

    async def get_car(self) -> dict[str, Any]:
        return await self._get(f"/api/v1/cars/{self.car_id}")

    async def get_status(self) -> dict[str, Any]:
        data = await self._get(f"/api/v1/cars/{self.car_id}/status")
        return data.get("data", data)

    async def get_battery_health(self) -> dict[str, Any]:
        data = await self._get(f"/api/v1/cars/{self.car_id}/battery-health")
        return data.get("data", data)

    async def get_drives(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        data = await self._get(f"/api/v1/cars/{self.car_id}/drives", params=params or None)
        if isinstance(data, dict):
            return data.get("data", [])
        return data

    async def get_charges(
        self,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {}
        if start_date:
            params["startDate"] = start_date.isoformat()
        if end_date:
            params["endDate"] = end_date.isoformat()
        data = await self._get(f"/api/v1/cars/{self.car_id}/charges", params=params or None)
        if isinstance(data, dict):
            return data.get("data", [])
        return data

    async def get_global_settings(self) -> dict[str, Any]:
        data = await self._get("/api/v1/globalsettings")
        return data.get("data", data)


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
