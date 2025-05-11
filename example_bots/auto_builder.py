#!/usr/bin/env python3
"""
OpenTribals Auto Builder Bot

This script automatically schedules building upgrades based on a predefined queue.
It checks for available slots and resources, then schedules the next building upgrade.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("auto_builder.log")],
)
logger = logging.getLogger(__name__)

# Bot configuration
SERVER = "http://localhost"  # Change to your server URL
PORT = 8000  # Change to your server port
USERNAME = "player1"  # Your game username
PASSWORD = "password123"  # Your game password
VILLAGE_ID = 1  # ID of the village to build in
CHECK_INTERVAL = 60  # Time between checks in seconds (1 minute)
API_VERSION = "v1"  # API version


# Define building types
class BuildingType(str, Enum):
    HEADQUARTERS = "headquarters"
    WOODCUTTER = "woodcutter"
    CLAY_PIT = "clay_pit"
    IRON_MINE = "iron_mine"
    FARM = "farm"


# Define a building queue (in order of priority)
BUILDING_QUEUE = [
    BuildingType.WOODCUTTER,  # Level up to 2
    BuildingType.CLAY_PIT,  # Level up to 2
    BuildingType.IRON_MINE,  # Level up to 2
    BuildingType.FARM,  # Level up to 2
    BuildingType.HEADQUARTERS,  # Level up to 2
    BuildingType.WOODCUTTER,  # Level up to 3
    BuildingType.CLAY_PIT,  # Level up to 3
    BuildingType.IRON_MINE,  # Level up to 3
    BuildingType.HEADQUARTERS,  # Level up to 3
    BuildingType.FARM,  # Level up to 3
    BuildingType.WOODCUTTER,  # Level up to 4
    BuildingType.CLAY_PIT,  # Level up to 4
    BuildingType.IRON_MINE,  # Level up to 4
    BuildingType.HEADQUARTERS,  # Level up to 4
    BuildingType.FARM,  # Level up to 4
    BuildingType.WOODCUTTER,  # Level up to 5
    BuildingType.CLAY_PIT,  # Level up to 5
    BuildingType.IRON_MINE,  # Level up to 5
]


class AutoBuilder:
    """Bot that automatically schedules building upgrades"""

    def __init__(self):
        self.base_url = f"{SERVER}:{PORT}/api/{API_VERSION}"
        self.client = httpx.AsyncClient(timeout=30.0)
        self.token = None
        self.village = None
        self.building_queue = BUILDING_QUEUE.copy()
        self.currently_building = []
        self.available_buildings = {}

    async def login(self) -> bool:
        """Authenticate with the server and get access token"""
        try:
            form_data = {"username": USERNAME, "password": PASSWORD}
            response = await self.client.post(
                f"{self.base_url}/login/access-token",
                data=form_data,
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data["access_token"]
                logger.info("Login successful")
                return True
            else:
                logger.error(f"Login failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    async def get_village_data(self) -> bool:
        """Get information about the village including resources"""
        if not self.token:
            logger.error("Not authenticated")
            return False

        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = await self.client.get(
                f"{self.base_url}/villages/{VILLAGE_ID}/private",
                headers=headers,
            )
            if response.status_code == 200:
                self.village = response.json()
                logger.info(
                    f"Village data retrieved: {self.village['name']} - "
                    f"Resources: Wood: {self.village['wood']}, "
                    f"Clay: {self.village['clay']}, "
                    f"Iron: {self.village['iron']}"
                )
                return True
            else:
                logger.error(
                    f"Failed to get village: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error getting village: {e}")
            return False

    async def get_building_queue(self) -> bool:
        """Get current building queue"""
        if not self.token:
            logger.error("Not authenticated")
            return False

        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = await self.client.get(
                f"{self.base_url}/villages/{VILLAGE_ID}/buildings/queue",
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                self.currently_building = data["queue"]
                logger.info(
                    f"Current building queue: {len(self.currently_building)} items"
                )
                for item in self.currently_building:
                    # Convert complete_at string to datetime for easier comparison
                    complete_at = datetime.fromisoformat(
                        item["complete_at"].replace("Z", "+00:00")
                    )
                    logger.info(
                        f"Building {item['building_type']} - completes at {complete_at}"
                    )
                return True
            else:
                logger.error(
                    f"Failed to get building queue: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error getting building queue: {e}")
            return False

    async def get_available_buildings(self) -> bool:
        """Get information about available buildings and their costs"""
        if not self.token:
            logger.error("Not authenticated")
            return False

        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = await self.client.get(
                f"{self.base_url}/villages/{VILLAGE_ID}/buildings/available",
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                self.available_buildings = {
                    b["building_type"]: b for b in data["buildings"]
                }
                logger.info(
                    f"Available buildings data retrieved for {len(self.available_buildings)} buildings"
                )
                return True
            else:
                logger.error(
                    f"Failed to get available buildings: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error getting available buildings: {e}")
            return False

    async def schedule_building_upgrade(self, building_type: str) -> bool:
        """Schedule a building upgrade"""
        if not self.token:
            logger.error("Not authenticated")
            return False

        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = await self.client.post(
                f"{self.base_url}/villages/{VILLAGE_ID}/buildings/{building_type}",
                headers=headers,
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"Successfully scheduled upgrade for {building_type}. "
                    f"Will complete at {data['complete_at']}"
                )
                return True
            else:
                logger.error(
                    f"Failed to schedule upgrade: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error scheduling upgrade: {e}")
            return False

    async def check_and_build(self) -> bool:
        """Check if we can build something and schedule it"""
        if not self.village or not self.available_buildings:
            logger.error("Missing village or building data")
            return False

        # If queue is full (2 buildings max), do nothing
        if len(self.currently_building) >= 2:
            logger.info("Building queue is full, waiting...")
            return False

        # Check if we have buildings left in our queue
        if not self.building_queue:
            logger.info("Building queue is empty, nothing left to build!")
            return False

        # Try to build from our queue
        for i, building_type in enumerate(self.building_queue[:]):
            # Check if the building info is available
            if building_type not in self.available_buildings:
                logger.error(
                    f"Building {building_type} not found in available buildings"
                )
                # Remove from queue and continue
                self.building_queue.pop(i)
                continue

            building = self.available_buildings[building_type]

            # Check if max level reached
            if building["max_level_reached"]:
                logger.info(f"Building {building_type} already at max level, skipping")
                self.building_queue.pop(i)
                continue

            # Check if we have enough resources
            wood_cost = building["wood_cost"]
            clay_cost = building["clay_cost"]
            iron_cost = building["iron_cost"]

            if (
                self.village["wood"] >= wood_cost
                and self.village["clay"] >= clay_cost
                and self.village["iron"] >= iron_cost
            ):
                # We have enough resources, try to build it
                logger.info(f"Attempting to schedule upgrade for {building_type}")
                if await self.schedule_building_upgrade(building_type):
                    # Success! Remove from queue and update our resource counts
                    self.village["wood"] -= wood_cost
                    self.village["clay"] -= clay_cost
                    self.village["iron"] -= iron_cost
                    self.building_queue.pop(i)
                    return True
            else:
                # Not enough resources
                logger.info(
                    f"Not enough resources for {building_type}. "
                    f"Need Wood: {wood_cost}, Clay: {clay_cost}, Iron: {iron_cost}. "
                    f"Have Wood: {self.village['wood']}, Clay: {self.village['clay']}, "
                    f"Iron: {self.village['iron']}"
                )

                # Try the next building in queue as it might be cheaper
                continue

        logger.info("Couldn't build anything from the queue at this time")
        return False

    async def run(self):
        """Main bot loop"""
        logger.info("Starting Auto Builder bot")

        # Initial login
        if not await self.login():
            logger.error("Failed to authenticate. Exiting.")
            return

        while True:
            try:
                # Always get current village data
                if not await self.get_village_data():
                    # Try to login again if getting village fails
                    if not await self.login():
                        logger.error("Failed to re-authenticate. Waiting before retry.")
                        await asyncio.sleep(60)
                        continue
                    if not await self.get_village_data():
                        logger.error(
                            "Failed to get village info. Waiting before retry."
                        )
                        await asyncio.sleep(60)
                        continue

                # Get current building queue status
                await self.get_building_queue()

                # Get available buildings and costs
                await self.get_available_buildings()

                # Try to build something
                await self.check_and_build()

                # Wait before next check
                logger.info(f"Waiting {CHECK_INTERVAL} seconds until next check...")
                await asyncio.sleep(CHECK_INTERVAL)

            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                await asyncio.sleep(60)  # Wait longer on error


if __name__ == "__main__":
    bot = AutoBuilder()
    asyncio.run(bot.run())
