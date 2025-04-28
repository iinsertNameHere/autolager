import pyudev

VID_PID = "1a86:7523"

def get_comport(vid_pid: str):
    port = None
    context = pyudev.Context()
    for device in context.list_devices(subsystem="tty"):
        if VID_PID in device.get("ID_USB_VENDOR_ID", "") + ":" + device.get("ID_USB_MODEL_ID", ""):
            port = device.device_node
            break
    return port