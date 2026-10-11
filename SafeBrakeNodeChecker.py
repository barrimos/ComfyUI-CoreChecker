import os
import time
import threading
import subprocess
import urllib.request
import urllib.error
import json
from server import PromptServer

DEFAULT_MAX_RAM = 22.0
DEFAULT_MAX_VRAM = 3.8

shared_config = {
    "max_ram_gb": DEFAULT_MAX_RAM,
    "max_vram_gb": DEFAULT_MAX_VRAM
}

class SafeMemoryMonitor:
    def __init__(self):
        self.running = True
        self.cooldown_active = False

    def get_vram_used(self):
        try:
            cmd = "nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits"
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode('utf-8')
            return round(int(output.strip()) / 1024, 2)
        except: return 0.0

    def get_ram_used(self):
        """ ดึงค่า RAM ที่ถูกใช้งานจริงบน Windows ด้วย PowerShell (เสถียรและแม่นยำกว่า wmic) """
        try:
            cmd = "powershell -Command \"$os = Get-CimInstance Win32_OperatingSystem; [math]::round(($os.TotalVisibleMemorySize - $os.FreePhysicalMemory) / 1024 / 1024, 2)\""
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode('utf-8')
            return float(output.strip())
        except: 
            # Fallback หากดึงผ่าน powershell ไม่สำเร็จ
            try:
                cmd = "wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value"
                output = subprocess.check_output(cmd, shell=True).decode('utf-8')
                lines = [line.strip() for line in output.split('\n') if line.strip()]
                total_kb, free_kb = 0, 0
                for line in lines:
                    if "TotalVisibleMemorySize" in line: total_kb = int(line.split('=')[1].strip())
                    if "FreePhysicalMemory" in line: free_kb = int(line.split('=')[1].strip())
                if total_kb > 0: return round((total_kb - free_kb) / 1024 / 1024, 2)
            except: pass
        return 0.0

    def trigger_api_interrupt(self):
        try:
            port = PromptServer.instance.port if PromptServer.instance else 8188
            host = PromptServer.instance.address if PromptServer.instance and PromptServer.instance.address else "127.0.0.1"
            if host == "0.0.0.0": host = "127.0.0.1" # ป้องกันกรณีผูกไอพีแบบ All Interfaces
            
            # 1. ส่งคำสั่ง /interrupt
            interrupt_url = f"http://{host}:{port}/interrupt"
            req_int = urllib.request.Request(interrupt_url, method="POST")
            with urllib.request.urlopen(req_int) as response: pass

            # 2. ส่งคำสั่งล้างคิวงาน
            queue_url = f"http://{host}:{port}/queue"
            data = json.dumps({"clear": True}).encode('utf-8')
            req_queue = urllib.request.Request(queue_url, data=data, headers={'Content-Type': 'application/json'}, method="POST")
            with urllib.request.urlopen(req_queue) as response: pass
            
            print(" -> [API SUCCESS] KSampler stopped and queue cleared safely via HTTP API.")
        except Exception as e:
            print(f" -> [API ERROR] Failed to send interrupt via API: {e}")

    def monitor_loop(self):
        time.sleep(5)
        print("\n[🛡️ SafeMemoryBrake] Realtime Smart Guard fully initialized.")
        
        while self.running:
            try:
                if self.cooldown_active:
                    time.sleep(1)
                    continue

                current_max_ram = shared_config["max_ram_gb"]
                current_max_vram = shared_config["max_vram_gb"]

                used_ram = self.get_ram_used()
                used_vram = self.get_vram_used()
                
                trigger = False
                reason = ""
                
                # ตรรกะแบบชาญฉลาด (Smart Logic):
                # 1. ถ้า RAM หลักเกินที่ตั้งไว้ -> ต้องตัดทันที (เพราะ OS จะค้าง)
                if used_ram > current_max_ram:
                    trigger = True
                    reason = f"CRITICAL: System RAM reached {used_ram} GB (Limit: {current_max_ram}GB)"
                
                # 2. ถ้า VRAM เกิน แต่พิจารณาร่วมกับ RAM (ป้องกันการตัดมั่วเมื่อใช้ Shared VRAM)
                # จะตัดก็ต่อเมื่อ VRAM เกินไปมาก และพบว่า RAM หลักก็ถูกดึงไปใช้จนเริ่มหนาแน่นแล้ว (เช่น เกิน 85% ของลิมิต RAM)
                elif used_vram > current_max_vram and used_ram > (current_max_ram * 0.85):
                    trigger = True
                    reason = f"WARNING: VRAM Overflowing ({used_vram}GB) & RAM Exhausted ({used_ram}GB)"
                    
                if trigger:
                    print(f"\n\n[🛡️ SafeMemoryBrake ALERT] {reason}! Triggering API Interrupt...")
                    self.trigger_api_interrupt()
                    
                    self.cooldown_active = True
                    threading.Thread(target=self.run_cooldown).start()
                    
                time.sleep(0.2)
            except Exception as e:
                time.sleep(1)

    def run_cooldown(self):
        print(" -> Entering 15 seconds cooldown for system recovery...")
        time.sleep(15)
        self.cooldown_active = False
        print("\n[🛡️ SafeMemoryBrake] Monitoring Resumed.")

monitor_instance = SafeMemoryMonitor()
threading.Thread(target=monitor_instance.monitor_loop, daemon=True).start()

class SafeMemoryBrakeNode:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        current_ram = monitor_instance.get_ram_used()
        current_vram = monitor_instance.get_vram_used()
        return {
            "required": {
                "max_ram_gb": ("FLOAT", {"default": DEFAULT_MAX_RAM, "min": 1.0, "max": 128.0, "step": 0.5}),
                "max_vram_gb": ("FLOAT", {"default": DEFAULT_MAX_VRAM, "min": 1.0, "max": 24.0, "step": 0.1}),
            },
            "optional": {
                f"[ STATS ON QUEUE ] RAM: {current_ram}GB | VRAM: {current_vram}GB": ("INT", {"default": 0}),
            }
        }

    RETURN_TYPES = ()
    OUTPUT_NODE = True
    FUNCTION = "update_config"
    CATEGORY = "🛡️ Safety"

    def update_config(self, max_ram_gb, max_vram_gb, **kwargs):
        shared_config["max_ram_gb"] = max_ram_gb
        shared_config["max_vram_gb"] = max_vram_gb
        return {}
