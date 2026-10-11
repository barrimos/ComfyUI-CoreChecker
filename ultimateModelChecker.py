import re

class UltimateModelChecker:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "model": ("MODEL",), 
                # ช่องพิมพ์ค้นหาเงื่อนไข รองรับ AND / OR และพิมพ์คีย์เวิร์ดสั้นๆ ได้ตามต้องการ
                "target_match": ("STRING", {"default": "flow or z-image"}),
            },
            "hidden": {
                "prompt": "PROMPT", 
                "extra_pnginfo": "EXTRA_PNGINFO",
                "unique_id": "UNIQUE_ID" 
            }
        }
    
    RETURN_TYPES = ("BOOLEAN", "STRING", "STRING")
    RETURN_NAMES = ("is_match", "model_name", "architecture_group")
    FUNCTION = "check_all"
    CATEGORY = "CoreChecker"

    def check_all(self, model, target_match, prompt=None, extra_pnginfo=None, unique_id=None):
        file_name = "Unknown_Model"
        raw_arch = "unknown_architecture"
        is_speed_distilled = False
        
        # 1. 🖨️ ดึงชื่อไฟล์ (File Name) จากต้นทางสายส่งข้อมูล
        try:
            if unique_id and prompt and str(unique_id) in prompt:
                node_info = prompt[str(unique_id)]
                if "inputs" in node_info and "model" in node_info["inputs"]:
                    model_link = node_info["inputs"]["model"]
                    origin_node_id = None
                    if isinstance(model_link, list) and len(model_link) > 0:
                        origin_node_id = str(model_link[0])
                    elif isinstance(model_link, str):
                        match = re.search(r'\[[\'"]?(\d+)[\'"]?', model_link)
                        origin_node_id = match.group(1) if match else model_link
                    
                    if origin_node_id and origin_node_id in prompt:
                        origin_inputs = prompt[origin_node_id].get("inputs", {})
                        if "unet_name" in origin_inputs:
                            file_name = str(origin_inputs["unet_name"])
                        elif "ckpt_name" in origin_inputs:
                            file_name = str(origin_inputs["ckpt_name"])
        except:
            pass

        # 2. 🔬 แกะรหัสสถาปัตยกรรมภายในโมเดลแบบ Recursive (ป้องกันบั๊ก Object Wrapper)
        try:
            if model is not None:
                # ไล่ตรวจสอบหาวัตถุประมวลผลหลักด้านใน
                inner_model = model
                for _ in range(3): # วนสแกนลึก 3 ชั้นกันการครอบ Wrapper หนา
                    if hasattr(inner_model, "model"):
                        inner_model = inner_model.model
                    else:
                        break
                
                # ดึงค่า model_type และแปลงจาก Enum เป็นข้อความสตริงอย่างปลอดภัย
                if hasattr(inner_model, "model_type"):
                    raw_arch = str(inner_model.model_type).strip().lower()
                elif hasattr(model, "model_config") and "model_type" in model.model_config:
                    raw_arch = str(model.model_config["model_type"]).strip().lower()
                
                # เช็คผ่านคลาส Latent Format
                if hasattr(inner_model, "latent_format"):
                    latent_name = str(inner_model.latent_format.__class__.__name__).lower()
                    if "flux" in latent_name:
                        raw_arch = "flow"
                    elif "sd3" in latent_name:
                        raw_arch = "flow"
                
                # เช็คคุณสมบัติพิเศษการ Distill ความเร็ว (เช่นกลุ่ม LCM / Lightning / Turbo)
                if hasattr(inner_model, "motion_model"):
                    is_speed_distilled = True
                
                # เช็คคำคีย์เวิร์ดใน Object Config
                if hasattr(inner_model, "config"):
                    config_str = str(inner_model.config).lower()
                    if any(k in config_str for k in ["lcm", "lightning", "turbo", "distill"]):
                        is_speed_distilled = True
        except:
            pass

        # 3. 🎯 ระบุกลุ่มตามหลักคณิตศาสตร์ทั้ง 4 กลุ่มหลักตามเงื่อนไขบรีฟ
        group_info = "Unknown_Group"
        clean_file = file_name.lower()
        
        # คีย์เวิร์ดสำหรับตรวจจับเพิ่มเติมกรณีระบุรุ่นย่อยจากชื่อไฟล์
        is_flow_kw = any(k in clean_file for k in ["krea", "flux", "minimax", "wan", "sd3", "cosmos", "z-image", "cogvideo", "ltx", "aura", "hunyuan"])
        is_lcm_kw = any(k in clean_file for k in ["lcm", "add", "latent_consistency", "tcd", "hyper-sd"]) or is_speed_distilled
        is_v_kw = any(k in clean_file for k in ["svd", "cosxl", "lightning", "ssd", "v2.", "v-pred"])

        # เช็คความสำคัญของกลุ่มโมเดลความเร็วสูงก่อน (เพื่อสกัดเอาโมเดลกลุ่ม Turbo/LCM ออกมา)
        # ⚡ กลุ่มที่ 4: Clean Image / Data Prediction (x0 หรือ lcm)
        if "lcm" in raw_arch or "x0" in raw_arch or is_lcm_kw:
            group_info = "lcm"

        # 🌊 กลุ่มที่ 1: Flow Matching (flow)
        elif "flow" in raw_arch or "sd3" in raw_arch or "hunyuan" in raw_arch or "minimax" in raw_arch or "wan" in raw_arch or "cosmos" in raw_arch or is_flow_kw:
            group_info = "flow"

        # ⏱️ กลุ่มที่ 3: Velocity (v_prediction)
        elif raw_arch == "v" or "v_pred" in raw_arch or "svd" in raw_arch or is_v_kw:
            group_info = "v"

        # 📈 กลุ่มที่ 2: Epsilon (eps)
        elif "eps" in raw_arch:
            group_info = "eps"
            
            # ตรวจสอบแชนเนลในระบบดักจับเพื่อระบุความต่างระหว่าง SD1.5 กับ SDXL อีกชั้นเพื่อรายงานผล
            try:
                inner_model = model.model if hasattr(model, "model") else model
                if hasattr(inner_model, "diffusion_model") and hasattr(inner_model.diffusion_model, "adm_channels"):
                    if inner_model.diffusion_model.adm_channels > 0:
                        group_info = "Epsilon (eps) [SDXL 1.0 / Pony / Juggernaut]"
                    else:
                        group_info = "Epsilon (eps) [SD1.5 / Standard Checkpoint]"
            except:
                pass
        else:
            group_info = "Epsilon (eps) [Traditional Noise Prediction (Default Fallback)]"

        # 4. 🎛️ ลอจิกการประมวลผลคำสั่งค้นหาแบบ AND / OR
        combined_search_pool = f"{file_name} {group_info}".strip().lower()
        raw_target = target_match.strip()
        is_match = False
        
        if raw_target != "":
            is_and_logic = bool(re.search(r'\+|(?<=\s)and(?=\s)', raw_target, re.IGNORECASE))
            
            if is_and_logic:
                keywords = re.split(r'\+|(?<=\s)and(?=\s)', raw_target, flags=re.IGNORECASE)
                keywords = [kw.strip().lower() for kw in keywords if kw.strip()]
                is_match = all(kw in combined_search_pool for kw in keywords) if keywords else False
            else:
                keywords = re.split(r',|(?<=\s)or(?=\s)', raw_target, flags=re.IGNORECASE)
                keywords = [kw.strip().lower() for kw in keywords if kw.strip()]
                is_match = any(kw in combined_search_pool for kw in keywords) if keywords else False
                
        return (is_match, file_name, group_info)

