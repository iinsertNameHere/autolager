import os
import serial
import time
import re
import threading
import queue
import asyncio

class StorageCell:
    def __init__(self, device_id, speed, name):
        self.device_id = device_id
        self.speed = speed
        self.serial_connection = None
        self.response_received = False
        self.lock = threading.Lock()
        self.filled = False
        self.name = name
        self.position = 0

    def __repr__(self):
        return f"StorageCell(device_id='{self.device_id}', speed={self.speed})"

    def connect_to_device(self):
        device_path = f"/dev/serial/by-id/{self.device_id}"
        
        if os.path.exists(device_path):
            try:
                self.serial_connection = serial.Serial(device_path, 9600, timeout=1)
                print(f"Connected to {self.device_id} at {device_path}")
                time.sleep(1)
                self.send_command(f"SPEED {self.speed}")
                time.sleep(0.2)
                return True
            except Exception as e:
                print(f"Failed to connect to {self.device_id}: {e}")
                return False
        else:
            print(f"Device {self.device_id} not found at {device_path}")
            return False

    def send_command(self, command):
        if self.serial_connection:
            with self.lock:
                self.serial_connection.write(f"{command}\n".encode())
                print(f"Sent command: {command}")
        else:
            print(f"Error: No serial connection for {self.device_id}.")

    def wait_for_response(self):
        if self.serial_connection:
            while True:
                response = self.serial_connection.readline().decode().strip()
                if response == "#NEXT#":
                    print(f"Response from {self.device_id}: {response}")
                    self.response_received = True
                    break
        else:
            print(f"Error: No serial connection for {self.device_id}.")

    def close_connection(self):
        if self.serial_connection:
            self.serial_connection.close()
            print(f"Connection to {self.device_id} closed.")
        else:
            print(f"Error: No connection to close for {self.device_id}.")

class CellsManager:
    def __init__(self, conf_file):
        self.storage_cells = self.parse_cells_conf(conf_file)
        self.command_queue = queue.Queue()
        self.processing_thread = threading.Thread(target=self._process_commands, daemon=True)
        self.processing_thread.start()

    def get_device_indices(self):
        return list(range(0, len(self.storage_cells)))

    def parse_cells_conf(self, file_path):
        storage_cells = []

        with open(file_path, 'r') as file:
            content = file.read()

        section_pattern = r"\[([^\]]+)\]\s*device_id\s*=\s*(\S+)\s*speed\s*=\s*(\d+)"
        matches = re.findall(section_pattern, content)

        for match in matches:
            pos_name, device_id, speed = match
            storage_cells.append(StorageCell(device_id, int(speed), pos_name))

        return storage_cells

    def connect_to_all_cells(self):
        cells_to_remove = []
        for cell in self.storage_cells:
            if not cell.connect_to_device():
                cells_to_remove.append(cell)

        for cell in cells_to_remove:
            self.storage_cells.remove(cell)
            print(f"Removed failed device {cell.device_id} from list.")

        print("All devices processed.")
        return cells_to_remove

    def _process_commands(self):
        while True:
            device_indices, command = self.command_queue.get()
            self._execute_command(device_indices, command)
            self.command_queue.task_done()

    def _execute_command(self, device_indices, command):
        for index in device_indices:
            if 0 <= index < len(self.storage_cells):
                self.storage_cells[index].send_command(command)

        for index in device_indices:
            if 0 <= index < len(self.storage_cells):
                self.storage_cells[index].wait_for_response()

        print("All commands processed.")

    async def send_command_to_cells(self, device_indices, command):
        self.command_queue.put((device_indices, command))
        await asyncio.sleep(0.1)

    async def close_all_connections(self):
        """
        Waits for all queued commands to finish before closing connections.
        """
        print("Waiting for all commands to finish before closing...")
        self.command_queue.join()  # Wait until all tasks in queue are processed

        for cell in self.storage_cells:
            cell.close_connection()

        print("All connections closed.")
