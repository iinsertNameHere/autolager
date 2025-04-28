import asyncio
from datetime import datetime

class AlertManager:
    def __init__(self):
        self.alerts = []
        self.lock = asyncio.Lock()
        self.last_id = -1

    async def __create_alert(self, level, message):
        async with self.lock:
            self.last_id += 1
            self.alerts.append((str(self.last_id), datetime.now().strftime("%H:%M:%S"), level, message))

    async def create_error(self, message):
        await self.__create_alert("ERROR", message)

    async def create_warning(self, message):
        await self.__create_alert("WARNING", message)
    
    async def create_info(self, message):
        await self.__create_alert("INFO", message)