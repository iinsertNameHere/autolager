from sanic import Sanic, response, redirect, json, text
from sanic_ext import Extend
from jinja2 import Environment, FileSystemLoader
from alerts import AlertManager
from devices import DeviceManager, StorageCell, ConveyorBelt
import os
import psutil
import time
from threading import Thread
import asyncio

app = Sanic("LogisticsSystem")
app.static('/static', 'static')
template_env = Environment(loader=FileSystemLoader("templates"))
alert_manager = AlertManager()
device_manager = DeviceManager("config/devices.yaml")

# Store all boxes
boxes = {}  # {box_id: {"items": int, "weight": float, "cell": StorageCell}}

STATUS = "STARTUP"

def manage_status():
    global STATUS
    while STATUS != "SHUTDOWN":
        if device_manager.command_queue.qsize() > 0 and STATUS == "OPERATIONAL":
            STATUS = "PROCESSING"
        elif device_manager.command_queue.qsize() <= 0 and STATUS == "PROCESSING":
            STATUS = "OPERATIONAL"
        time.sleep(1.5)

@app.listener("after_server_start")
async def after_server_start(app):
    global STATUS
    await alert_manager.create_info("Welcome to the OmniTrack WebUI :)")
    await alert_manager.create_info("Startup in process...")

    failed_devices = [d for d in device_manager.devices.values() if not d.reachable ]
    for d in failed_devices:
        await alert_manager.create_error("Failed to connect to Device " + d.name + " on " + d.com_path)
    
    await device_manager.send_command(device_manager.devices.keys(), 'CALIB')  # Example command

    STATUS = "OPERATIONAL"
    await alert_manager.create_info("OmniTrack: Operational")
    Thread(target=manage_status).start()

@app.listener("before_server_stop")
async def before_server_stop(app):
    global STATUS
    await alert_manager.create_info("Shutdown in process...")
    STATUS = "SHUTDOWN"
    await device_manager.close()
    await alert_manager.create_info("OmniTrack: Shutdown")

@app.get("/")
async def index(request):
    return redirect("/dashboard")

@app.get("/favicon.ico")
async def favicon(request):
    return redirect("/static/favicon.ico")

@app.get("/dashboard")
async def dashboard(request):
    template = template_env.get_template("dashboard.html.j2")
    return response.html(template.render(active="Dashboard"))

@app.get("/storage")
async def storage(request):
    template = template_env.get_template("storage.html.j2") 
    return response.html(template.render(active="Storage", storage_cells=[d for d in device_manager.devices.values() if isinstance(d, StorageCell)]))

@app.get("/conveyor")
async def conveyor(request):
    template = template_env.get_template("conveyor.html.j2") 
    return response.html(template.render(active="Conveyor"))

@app.get("/logistics")
async def logistics(request):
    template = template_env.get_template("logistics.html.j2") 
    return response.html(template.render(active="Logistics"))

@app.post("/conveyor/move")
async def conveyor_move(request):
    amount = float(request.json.get("amount"))
    command = "MOVE "
    if amount < 0:
        command += "R " + str(-1 * amount)
    else:
        command += str(amount)
    print(command)
    await device_manager.send_command(["ConveyorBelt"], command)
    return text("OK")

@app.get("/boxes")
async def get_boxes(request):
    """Returns all stored boxes with their details."""
    return json([{"id": box_id, "items": data["items"], "weight": data["weight"]} for box_id, data in boxes.items()])

@app.post("/boxes")
async def store_box(request):
    """Stores a new box by marking an empty StorageCell as filled."""
    global boxes
    data = request.json
    items = data.get("items")
    weight = data.get("weight")

    # Find an empty storage cell
    empty_cell = next((cell for cell in device_manager.devices.values() if isinstance(cell, StorageCell) and not getattr(cell, "filled", False)), None)

    if not empty_cell:
        return json({"error": "No empty storage cells available"}, status=400)

    # Assign a new box ID
    box_id = f"BOX-{len(boxes) + 1}"

    await device_manager.send_command(["ConveyorBelt"], f"MOVE {empty_cell.conveyor_rotations}")
    await device_manager.send_command(["PistonWallA"], f"POS 100, POS 0")

    # Mark the cell as filled and store box details
    empty_cell.filled = True
    boxes[box_id] = {"items": items, "weight": weight, "cell": empty_cell}

    await alert_manager.create_info("Stored new Box with id '" + box_id + "' in " + empty_cell.name + ": containing " + str(items) + " items and weighing " + str(weight) + "kg")

    return json({"id": box_id})

@app.delete("/boxes/<box_id>")
async def retrieve_box(request, box_id):
    """Retrieves a stored box and moves it via the conveyor system."""
    global boxes

    if box_id not in boxes:
        return json({"error": "Box not found"}, status=404)

    box_data = boxes.pop(box_id)
    storage_cell = box_data["cell"]

    # Move storage cell to position 100 (ready to retrieve)
    await device_manager.send_command([storage_cell.name], "POS 100")
    await asyncio.sleep(1)  # Simulate movement time
    await device_manager.send_command([storage_cell.name], "POS 0")

    # Move conveyor belt to retrieve the box
    await device_manager.send_command(["ConveyorBelt"], f"MOVE R {storage_cell.conveyor_rotations}")

    # Mark cell as empty
    storage_cell.filled = False

    await alert_manager.create_info("Retrieved Box " + box_id + " from Storage Cell " + storage_cell.name + ".")

    return json({"success": True, "message": f"Box {box_id} retrieved successfully"})

@app.get("/data")
async def data(request):
    def get_system_stats():
        cpu_usage = psutil.cpu_percent(interval=1)
        ram_usage = psutil.virtual_memory().percent
        try:
            temp = psutil.sensors_temperatures().get("coretemp", [{}])[0].get("current", "N/A")
        except AttributeError:
            temp = "N/A"
        return f"{cpu_usage}", f"{ram_usage}", f"{temp}" if temp != "N/A" else "0"
    
    cpu_usage, ram_usage, cpu_temp = get_system_stats()
    max_cells = sum(1 for device in device_manager.devices.values() if isinstance(device, StorageCell))
    filled_cells = sum(1 for device in device_manager.devices.values() if isinstance(device, StorageCell) and getattr(device, "filled", False))

    return json({
        "alerts": alert_manager.alerts,
        "filledCells": filled_cells,
        "maxCells": max_cells,
        "storedItems": sum(box["items"] for box in boxes.values()),
        "systemState": STATUS,
        "cpuTemp": cpu_temp,
        "cpuUsage": cpu_usage,
        "ramUsage": ram_usage,
        "queuedCommands": device_manager.command_queue.qsize()
    })

@app.post("/cell/<name:str>/position")
async def cell_position(request, name: str):
    await device_manager.send_command([name], "POS " + request.body.decode())
    if name in device_manager.devices:
        device_manager.devices[name].position = int(request.body.decode())
    return text("OK")

@app.get("/cell/positions")
async def get_cell_position(request):
    return json({
        "positions": {name: device.position for name, device in device_manager.devices.items() if isinstance(device, StorageCell)}
    })

@app.post("/cell/<name:str>/unload")
async def cell_unload(request, name: str):
    await device_manager.send_command([name], "UNLOAD")
    if name in device_manager.devices:
        device_manager.devices[name].position = 0
    return text("OK")

@app.post("/cell/<name:str>/load")
async def cell_load(request, name: str):
    await device_manager.send_command([name], "LOAD")
    if name in device_manager.devices:
        device_manager.devices[name].position = 0
    return text("OK")

@app.post("/cell/<name:str>/calibrate")
async def cell_calibrate(request, name: str):
    await device_manager.send_command([name], "CALIB")
    if name in device_manager.devices:
        device_manager.devices[name].position = 0
    return text("OK")
