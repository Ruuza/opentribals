#!/usr/bin/env python3
"""
OpenTribals Auto Attacker Bot

This script automatically farms abandoned villages by sending attacks with predefined units.
"""

import asyncio
import logging
import time
from typing import Any

import httpx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("auto_attacker.log")],
)
logger = logging.getLogger(__name__)

# Bot configuration
SERVER = "http://localhost"  # Change to your server URL
PORT = 8000  # Change to your server port
USERNAME = "player1"  # Your game username
PASSWORD = "password123"  # Your game password
VILLAGE_ID = 1  # ID of the village to send attacks from
SEARCH_RADIUS = 10  # Search radius (area will be 2*RADIUS x 2*RADIUS)
ATTACK_UNITS = {  # Units to send in each attack
    "archer": 10,
    "swordsman": 0,
    "knight": 0,
    "skirmisher": 0,
    "nobleman": 0,
}
CHECK_INTERVAL = 60  # Time between checks in seconds (1 minute)
API_VERSION = "v1"  # API version


class AutoAttacker:
    """Bot that automatically farms abandoned villages"""

    def __init__(self):
        self.base_url = f"{SERVER}:{PORT}/api/{API_VERSION}"
        self.client = httpx.AsyncClient(timeout=30.0)
        self.token = None
        self.village = None
        self.last_check_time = 0
        self.abandoned_villages = []

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
            logger.error(f"Login error: {e}", exc_info=True)
            return False

    async def get_own_village(self) -> bool:
        """Get information about our village"""
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
                    f"Village data retrieved: {self.village['name']} at [{self.village['x']}, {self.village['y']}]"
                )
                return True
            else:
                logger.error(
                    f"Failed to get village: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error getting village: {e}", exc_info=True)
            return False

    async def find_abandoned_villages(self) -> list[dict[str, Any]]:
        """Find abandoned villages in the area around our village"""
        if not self.village:
            logger.error("Own village data not available")
            return []

        abandoned = []
        try:
            x, y = self.village["x"], self.village["y"]
            headers = {"Authorization": f"Bearer {self.token}"}

            # Get all villages in a bounding box around our village
            response = await self.client.get(
                f"{self.base_url}/villages",
                headers=headers,
                params={
                    "x_min": x - SEARCH_RADIUS,
                    "y_min": y - SEARCH_RADIUS,
                    "x_max": x + SEARCH_RADIUS,
                    "y_max": y + SEARCH_RADIUS,
                },
            )

            if response.status_code == 200:
                villages_data = response.json()
                villages = villages_data["data"]

                # Filter abandoned villages (no player_id)
                abandoned = [v for v in villages if not v.get("player")]
                logger.info(
                    f"Found {len(abandoned)} abandoned villages near coordinates [{x}, {y}]"
                )
                return abandoned
            else:
                logger.error(
                    f"Failed to get villages: {response.status_code} - {response.text}"
                )
                return []
        except Exception as e:
            logger.error(f"Error finding abandoned villages: {e}", exc_info=True)
            return []

    async def send_attack(self, target_village_id: int) -> bool:
        """Send an attack to the target village"""
        if not self.token:
            return False

        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = await self.client.post(
                f"{self.base_url}/villages/{VILLAGE_ID}/attack/{target_village_id}",
                headers=headers,
                json=ATTACK_UNITS,
            )

            if response.status_code == 200:
                data = response.json()
                logger.info(
                    f"Attack sent to village ID {target_village_id}. Movement ID: {data['id']}"
                )
                return True
            else:
                logger.error(
                    f"Failed to send attack: {response.status_code} - {response.text}"
                )
                return False
        except Exception as e:
            logger.error(f"Error sending attack: {e}", exc_info=True)
            return False

    async def check_movements(self) -> int:
        """Check current movements and return count of ongoing attacks"""
        if not self.token:
            return 0

        try:
            headers = {"Authorization": f"Bearer {self.token}"}
            response = await self.client.get(
                f"{self.base_url}/villages/{VILLAGE_ID}/movements",
                headers=headers,
            )

            if response.status_code == 200:
                movements = response.json()
                # Count outgoing attacks
                outgoing_attacks = sum(
                    1
                    for m in movements
                    if m["origin_village"]["id"] == VILLAGE_ID
                    and m["is_attack"]
                    and not m["completed"]
                )
                logger.info(f"Current outgoing attacks: {outgoing_attacks}")
                return outgoing_attacks
            else:
                logger.error(
                    f"Failed to check movements: {response.status_code} - {response.text}"
                )
                return 0
        except Exception:
            logger.error("Error checking movements", exc_info=True)
            return 0

    async def run(self):
        """Main bot loop"""
        logger.info("Starting Auto Attacker bot")

        # Initial login
        if not await self.login():
            logger.error("Failed to authenticate. Exiting.")
            return

        while True:
            try:
                # Get current time
                current_time = time.time()

                # Only check for new villages to attack at intervals
                if current_time - self.last_check_time >= CHECK_INTERVAL:
                    # Update our village information
                    if not await self.get_own_village():
                        # Try to login again if getting village fails
                        if not await self.login():
                            logger.error(
                                "Failed to re-authenticate. Waiting before retry."
                            )
                            await asyncio.sleep(60)
                            continue
                        if not await self.get_own_village():
                            logger.error(
                                "Failed to get village info. Waiting before retry."
                            )
                            await asyncio.sleep(60)
                            continue

                    # Find abandoned villages
                    self.abandoned_villages = await self.find_abandoned_villages()
                    self.last_check_time = current_time

                # Check current attack movements
                current_attacks = await self.check_movements()

                # Attack abandoned villages if we have any villages to attack
                # and we're not already attacking too many villages
                if self.abandoned_villages and current_attacks < 10:
                    target = self.abandoned_villages.pop(0)
                    logger.info(
                        f"Preparing to attack abandoned village ID {target['id']} at [{target['x']}, {target['y']}]"
                    )
                    await self.send_attack(target["id"])

                # Wait a bit before the next iteration
                await asyncio.sleep(10)

            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                await asyncio.sleep(60)  # Wait longer on error


if __name__ == "__main__":
    bot = AutoAttacker()
    asyncio.run(bot.run())
