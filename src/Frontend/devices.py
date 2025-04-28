import asyncio
import yaml
import serial
import serial_asyncio
import serial.tools.list_ports

class Device:
    def __init__(self, name, com_path):
        self.name = name
        self.com_path = com_path
        self.reader = None
        self.writer = None
        self.reachable = False

    async def connect(self):
        try:
            self.reader, self.writer = await serial_asyncio.open_serial_connection(url=self.com_path, baudrate=9600)
            self.reachable = True
            print(f"Device {self.name} connected.")
        except Exception as e:
            print(f"Failed to connect to {self.name}: {e}")
            self.reachable = False

    async def send_command(self, command):
        if self.reachable and self.writer:
            self.writer.write((command + "\n").encode())
            await self.writer.drain()
            print(f"Command sent to {self.name}: {command}")
            
            # Wait for response in a non-blocking way
            response = await self.wait_for_response()
            return response
        return None

    async def wait_for_response(self):
        if self.reader:
            try:
                response = await asyncio.wait_for(self.reader.readline(), timeout=240)
                return response.decode().strip()
            except asyncio.TimeoutError:
                print(f"Timeout waiting for response from {self.name}")
                return None
        return None

    async def close(self):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.reachable = False
            print(f"Connection to {self.name} closed.")

class StorageCell(Device):
    def __init__(self, name, com_path, conveyor_rotations):
        super().__init__(name, com_path)
        self.conveyor_rotations = conveyor_rotations
        self.position = 0
        self.filled = False

class ConveyorBelt(Device):
    def __init__(self, name, com_path):
        super().__init__(name, com_path)

class DeviceManager:
    def __init__(self, config_path):
        self.devices = {}
        self.command_queue = asyncio.Queue()
        self.loop = asyncio.get_event_loop()
        self.config_path = config_path
        self.connected = False  # Flag to indicate when all devices are connected
        self.loop.create_task(self._load_config(config_path))
        self.loop.create_task(self._process_queue())

    async def _load_config(self, config_path):
        with open(config_path, 'r') as file:
            self.config = yaml.safe_load(file)
        
        # Discover available devices
        await self._discover_devices()

    async def _discover_devices(self):
        # List all available COM ports
        available_ports = serial.tools.list_ports.comports()
        for port in available_ports:
            # Send a test message to identify the device on this COM port
            device_id = await self._get_device_id(port.device)
            if device_id:
                # Match the discovered device ID with the config
                matched_device = next((d for d in self.config if d.get('id') == device_id), None)
                if matched_device:
                    # Add the device based on the matched config
                    name = matched_device['name']
                    com_path = port.device
                    if matched_device['type'] == 'ConveyorBelt':
                        self.devices[name] = ConveyorBelt(name, com_path)
                    elif matched_device['type'] == 'StorageCell':
                        rotations = matched_device['conveyor_rotations']
                        self.devices[name] = StorageCell(name, com_path, rotations)
                    print(f"Device {name} detected on {com_path}")

        # Connect all devices
        await self._connect_devices()

    async def _get_device_id(self, com_path):
        try:
            # Open the port and send a command to fetch the device ID
            reader, writer = await serial_asyncio.open_serial_connection(url=com_path, baudrate=9600)
            await asyncio.sleep(2)
            writer.write("ID\n".encode())
            await writer.drain()
            response = await asyncio.wait_for(reader.readline(), timeout=2)
            writer.close()
            await writer.wait_closed()
            device_id = response.decode().strip()
            print(f"Device ID received from {com_path}: {device_id}")
            return device_id
        except Exception as e:
            print(f"Failed to get device ID from {com_path}: {e}")
            return None

    async def _connect_devices(self):
        await asyncio.gather(*(device.connect() for device in self.devices.values()))
        self.connected = True  # All devices are now connected

    async def _process_queue(self):
        while True:
            device_names, command = await self.command_queue.get()

            # Ensure commands are processed only after devices are connected
            if not self.connected:
                print("Devices are still connecting, command will be retried.")
                self.command_queue.put_nowait((device_names, command))  # Retry the command later
                await asyncio.sleep(10)  # Retry delay (could adjust as needed)
                continue

            # Ensure commands are processed asynchronously for all reachable devices
            responses = await asyncio.gather(*(self.devices[name].send_command(command) for name in device_names if name in self.devices and self.devices[name].reachable))
            print(f"Responses for command '{command}': {responses}")
            self.command_queue.task_done()

    async def send_command(self, device_names, command):
        # Add the command to the queue for processing
        await self.command_queue.put((device_names, command))
    
    async def close(self):
        print("Waiting for all commands to be processed...")
        # await self.command_queue.join()  # Ensure all commands are processed before closing
        await asyncio.gather(*(device.close() for device in self.devices.values()))
        print("All devices disconnected.")

async def test_device_manager():
    # Initialize the DeviceManager with the test config file
    device_manager = DeviceManager("config/devices.yaml")

    # Give the manager some time to initialize and connect devices
    await asyncio.sleep(2)

    # Test sending commands to the devices
    await device_manager.send_command(['MainConveyor', 'StorageCellA'], 'CALIB')  # Example command

    # Test closing all connections after commands are processed
    await device_manager.close()

# Run the test function
if __name__ == "__main__":
    asyncio.run(test_device_manager())
