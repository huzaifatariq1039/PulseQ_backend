import httpx
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime
import os

logger = logging.getLogger(__name__)

# External Go POS API Configuration
GO_POS_BASE_URL = os.getenv("GO_POS_BASE_URL", "http://localhost:8080/api/v1")
GO_POS_TIMEOUT = 5.0 # seconds

class GoPOSService:
    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=GO_POS_BASE_URL,
            timeout=GO_POS_TIMEOUT,
            headers={"Content-Type": "application/json"}
        )

    async def get_inventory(self, hospital_id: str) -> List[Dict[str, Any]]:
        """Fetch full inventory from Go POS API concurrently."""
        try:
            response = await self.client.get(f"/inventory/{hospital_id}")
            response.raise_for_status()
            return response.json().get("items", [])
        except Exception as e:
            logger.error(f"Failed to fetch inventory from Go POS: {e}")
            return [] # Fallback to empty list

    async def get_stock_status(self, hospital_id: str, product_ids: List[int]) -> Dict[int, int]:
        """Fetch stock levels for specific products concurrently."""
        tasks = [self.client.get(f"/stock/{hospital_id}/{pid}") for pid in product_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        stock_map = {}
        for i, res in enumerate(results):
            if isinstance(res, httpx.Response) and res.status_code == 200:
                stock_map[product_ids[i]] = res.json().get("quantity", 0)
            else:
                logger.warning(f"Could not fetch stock for product {product_ids[i]}")
                stock_map[product_ids[i]] = 0
        return stock_map

    async def close(self):
        await self.client.aclose()

# Singleton instance
go_pos_service = GoPOSService()
