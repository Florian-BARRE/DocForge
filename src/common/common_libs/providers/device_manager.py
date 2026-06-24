# ====== Code Summary ======
# Backward-compatible shim — re-exports Device, DeviceCapability, and DeviceManager
# from the device/ package.  Preserves the public import path:
#   from libs.providers.device_manager import DeviceManager

# ====== Local Project Imports ======
from .device import Device, DeviceCapability, DeviceManager

__all__ = [
    "Device",
    "DeviceCapability",
    "DeviceManager",
]
