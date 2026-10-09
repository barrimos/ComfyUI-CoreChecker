# ดึงข้อมูลการลงทะเบียนโหนดมาจากไฟล์เดี่ยวทั้ง 2 ตัวด้านใน
from .ultimateModelChecker import UltimateModelChecker
from .memoryGuardChecker import MemoryGuardChecker


# รวมร่างช่องทางการเรียกใช้งานโหนดทั้งหมดส่งไปให้ ComfyUI หลักรันระบบ
NODE_CLASS_MAPPINGS = {
    "UltimateModelChecker": UltimateModelChecker,
    "MemoryGuardChecker": MemoryGuardChecker,
}


NODE_DISPLAY_NAME_MAPPINGS = {
    "UltimateModelChecker": "Ultimate Model Checker [CC]",
    "MemoryGuardChecker": "Memory Guard Checker [CC]",
}


# ============================================================
# Frontend JavaScript Extension
# ============================================================
#
# ComfyUI จะโหลด JavaScript ในโฟลเดอร์นี้โดยอัตโนมัติ
#
WEB_DIRECTORY = "./js"


__all__ = [
    "NODE_CLASS_MAPPINGS",
    "NODE_DISPLAY_NAME_MAPPINGS",
    "WEB_DIRECTORY",
]
