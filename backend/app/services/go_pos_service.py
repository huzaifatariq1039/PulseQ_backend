import httpx
import logging
import asyncio
from typing import List, Dict, Any, Optional
import os

logger = logging.getLogger(__name__)

# External Go POS API Configuration
GO_POS_BASE_URL = os.getenv("GO_POS_BASE_URL", "").strip()
GO_POS_API_KEY = os.getenv("GO_POS_API_KEY", "").strip()
GO_POS_TIMEOUT = 5.0


class GoPOSService:
    def __init__(self):
        if not GO_POS_BASE_URL:
            logger.warning("[GoPOS] GO_POS_BASE_URL is not set in .env — GoPOS integration disabled.")

        headers = {"Content-Type": "application/json"}
        if GO_POS_API_KEY:
            headers["Authorization"] = f"Bearer {GO_POS_API_KEY}"

        self.client = httpx.AsyncClient(
            base_url=GO_POS_BASE_URL or "http://localhost:8080",
            timeout=GO_POS_TIMEOUT,
            headers=headers,
        )
        self.enabled = bool(GO_POS_BASE_URL)

    async def get_inventory(self, hospital_id: str) -> List[Dict[str, Any]]:
        """Fetch full inventory from Go POS API."""

        # ✅ Guard: skip if integration is disabled
        if not self.enabled:
            logger.warning("[GoPOS] Integration disabled — GO_POS_BASE_URL not set.")
            return []

        # ✅ Guard: skip if hospital_id is invalid
        if not hospital_id or str(hospital_id).strip().lower() in ("", "default", "none", "null"):
            logger.warning(f"[GoPOS] Invalid hospital_id '{hospital_id}' — skipping inventory fetch.")
            return []

        try:
            response = await self.client.get(f"/inventory/{hospital_id}")
            response.raise_for_status()
            data = response.json()
            items = data.get("items", data if isinstance(data, list) else [])
            logger.info(f"[GoPOS] Fetched {len(items)} inventory items for hospital {hospital_id}")
            return items
        except httpx.HTTPStatusError as e:
            logger.error(f"[GoPOS] HTTP error fetching inventory for {hospital_id}: {e.response.status_code} {e}")
            return []
        except httpx.RequestError as e:
            logger.error(f"[GoPOS] Connection error fetching inventory for {hospital_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"[GoPOS] Unexpected error fetching inventory for {hospital_id}: {e}")
            return []

    async def get_stock_status(self, hospital_id: str, product_ids: List[int]) -> Dict[int, int]:
        """Fetch stock levels for specific products concurrently."""

        # ✅ Guard: skip if integration is disabled
        if not self.enabled:
            logger.warning("[GoPOS] Integration disabled — GO_POS_BASE_URL not set.")
            return {pid: 0 for pid in product_ids}

        # ✅ Guard: skip if hospital_id is invalid
        if not hospital_id or str(hospital_id).strip().lower() in ("", "default", "none", "null"):
            logger.warning(f"[GoPOS] Invalid hospital_id '{hospital_id}' — skipping stock fetch.")
            return {pid: 0 for pid in product_ids}

        if not product_ids:
            return {}

        tasks = [
            self.client.get(f"/stock/{hospital_id}/{pid}")
            for pid in product_ids
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        stock_map = {}
        for i, res in enumerate(results):
            pid = product_ids[i]
            if isinstance(res, httpx.Response) and res.status_code == 200:
                stock_map[pid] = res.json().get("quantity", 0)
            else:
                logger.warning(f"[GoPOS] Could not fetch stock for product {pid}: {res}")
                stock_map[pid] = 0

        return stock_map

    async def close(self):
        await self.client.aclose()


# Singleton instance
go_pos_service = GoPOSService()