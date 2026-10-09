import sys
import ctypes
import torch


# ============================================================
# Windows RAM structure
# ============================================================

class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


# ============================================================
# Memory Guard
# ============================================================

class MemoryGuardChecker:

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # Wildcard input.
                #
                # Frontend JS will propagate the actual type
                # to the output socket.
                "any_input": ("*",),

                "min_vram_gb": (
                    "FLOAT",
                    {
                        "default": 1.0,
                        "min": 0.0,
                        "max": 128.0,
                        "step": 0.1,
                        "display": "number",
                    },
                ),

                "min_ram_gb": (
                    "FLOAT",
                    {
                        "default": 2.0,
                        "min": 0.0,
                        "max": 256.0,
                        "step": 0.1,
                        "display": "number",
                    },
                ),
            }
        }

    # ========================================================
    # IMPORTANT
    #
    # Backend remains wildcard.
    #
    # JS changes the actual visible socket type.
    # ========================================================

    RETURN_TYPES = (
        "*",
        "STRING",
        "STRING",
        "FLOAT",
        "FLOAT",
    )

    RETURN_NAMES = (
        "output_passthrough",
        "vram_status",
        "ram_status",
        "free_vram_gb",
        "free_ram_gb",
    )

    FUNCTION = "check_memory_at_point"

    CATEGORY = "CoreChecker"

    DESCRIPTION = (
        "Pass-through memory guard. "
        "The output type follows the connected input type."
    )

    # ========================================================
    # Backend validation
    # ========================================================

    @classmethod
    def VALIDATE_INPUTS(cls, any_input=None, **kwargs):
        """
        The wildcard input accepts all ComfyUI types.

        Actual type compatibility is primarily handled by the
        frontend socket propagation.

        Returning True here is intentional because Python does
        not receive the socket's declared type as metadata.
        """

        return True

    # ========================================================
    # Main execution
    # ========================================================

    def check_memory_at_point(
        self,
        any_input=None,
        min_vram_gb=1.0,
        min_ram_gb=2.0,
    ):

        min_vram_limit = float(min_vram_gb)
        min_ram_limit = float(min_ram_gb)

        # ====================================================
        # 1. VRAM
        # ====================================================

        vram_report = "🎮 VRAM: N/A (CPU Mode)"
        free_vram_gb = 999.0

        if torch.cuda.is_available():

            try:

                device = torch.cuda.current_device()

                free_bytes, total_bytes = torch.cuda.mem_get_info(device)

                free_vram_val_gb = (
                    free_bytes / (1024 ** 3)
                )

                total_vram_gb_val = (
                    total_bytes / (1024 ** 3)
                )

                used_vram_gb_val = (
                    total_vram_gb_val -
                    free_vram_val_gb
                )

                vram_report = (
                    f"🎮 VRAM Used: "
                    f"{used_vram_gb_val:.2f} GB / "
                    f"Real Free: "
                    f"{free_vram_val_gb:.2f} GB "
                    f"(Total: "
                    f"{total_vram_gb_val:.2f} GB)"
                )

                free_vram_gb = float(
                    round(free_vram_val_gb, 2)
                )

                # Release unused PyTorch cache.
                torch.cuda.empty_cache()

            except Exception as e:

                vram_report = (
                    f"🎮 VRAM Diagnostic Error: {e}"
                )

                free_vram_gb = 0.0

        # ====================================================
        # 2. System RAM
        # ====================================================

        ram_report = "🧠 RAM: OS Not Supported"
        free_ram_gb = 999.0

        # ----------------------------------------------------
        # Windows
        # ----------------------------------------------------

        if sys.platform == "win32":

            try:

                stat = MEMORYSTATUSEX()

                stat.dwLength = ctypes.sizeof(stat)

                success = (
                    ctypes.windll.kernel32
                    .GlobalMemoryStatusEx(
                        ctypes.byref(stat)
                    )
                )

                if not success:
                    raise RuntimeError(
                        "GlobalMemoryStatusEx failed"
                    )

                total_ram_val = (
                    stat.ullTotalPhys /
                    (1024 ** 3)
                )

                free_ram_val = (
                    stat.ullAvailPhys /
                    (1024 ** 3)
                )

                used_ram_val = (
                    total_ram_val -
                    free_ram_val
                )

                ram_report = (
                    f"🧠 RAM Used: "
                    f"{used_ram_val:.2f} GB / "
                    f"Free: "
                    f"{free_ram_val:.2f} GB "
                    f"(Total: "
                    f"{total_ram_val:.2f} GB)"
                )

                free_ram_gb = float(
                    round(free_ram_val, 2)
                )

            except Exception as e:

                ram_report = (
                    f"🧠 RAM Windows API Error: {e}"
                )

                free_ram_gb = 0.0

        # ----------------------------------------------------
        # Linux
        # ----------------------------------------------------

        else:

            try:

                mem_total = 0
                mem_available = 0

                with open(
                    "/proc/meminfo",
                    "r",
                    encoding="utf-8",
                ) as f:

                    for line in f:

                        parts = line.split()

                        if len(parts) < 2:
                            continue

                        if parts[0] == "MemTotal:":
                            mem_total = (
                                int(parts[1]) * 1024
                            )

                        elif parts[0] == "MemAvailable:":
                            mem_available = (
                                int(parts[1]) * 1024
                            )

                if mem_total > 0:

                    total_ram_val = (
                        mem_total /
                        (1024 ** 3)
                    )

                    free_ram_val = (
                        mem_available /
                        (1024 ** 3)
                    )

                    used_ram_val = (
                        total_ram_val -
                        free_ram_val
                    )

                    ram_report = (
                        f"🐧 Linux RAM Used: "
                        f"{used_ram_val:.2f} GB / "
                        f"Free: "
                        f"{free_ram_val:.2f} GB "
                        f"(Total: "
                        f"{total_ram_val:.2f} GB)"
                    )

                    free_ram_gb = float(
                        round(free_ram_val, 2)
                    )

            except Exception as e:

                ram_report = (
                    f"🧠 RAM Check Error: {e}"
                )

                free_ram_gb = 0.0

        # ====================================================
        # 3. Safety check
        # ====================================================

        is_vram_low = (
            torch.cuda.is_available()
            and free_vram_gb < min_vram_limit
        )

        is_ram_low = (
            free_ram_gb < min_ram_limit
        )

        if is_vram_low or is_ram_low:

            error_message = (
                "\n\n"
                "🚨 [Memory Guard Protection Triggered]\n"
                "=========================================\n"
            )

            error_message += (
                f"{vram_report}\n"
                f"{ram_report}\n"
            )

            error_message += (
                "-----------------------------------------\n"
                "🎯 Safety Threshold Settings:\n"
                f"• Min VRAM Required: "
                f"{min_vram_limit:.1f} GB\n"
                f"• Min RAM Required: "
                f"{min_ram_limit:.1f} GB\n"
                "=========================================\n"
                "❌ Reason: "
            )

            if is_vram_low and is_ram_low:

                error_message += (
                    "Both VRAM and RAM are below "
                    "safety limits!"
                )

            elif is_vram_low:

                error_message += (
                    "VRAM is too low to continue! "
                    "Execution stopped to prevent "
                    "Out-Of-Memory Crash."
                )

            else:

                error_message += (
                    "System RAM is too low! "
                    "Execution stopped to prevent "
                    "Windows Pagefile swapping lag."
                )

            raise ValueError(error_message)

        # ====================================================
        # 4. Passthrough
        # ====================================================

        return (
            any_input,
            vram_report,
            ram_report,
            free_vram_gb,
            free_ram_gb,
        )
