import json
from pathlib import Path
from typing import Dict, List, Any, Optional

def select_best_model(models: List[Dict[str, Any]], ram_gb: float, vram_gb: float) -> Optional[Dict[str, Any]]:
    """
    Select the optimal model for the host machine.
    Prioritizes models that fit completely into VRAM for GPU acceleration,
    falling back to RAM-compatible models.
    """
    if not models:
        return None

    # Filter out models that exceed system RAM
    candidates = []
    for m in models:
        min_ram = m.get("recommended_min_ram_gb", 4)
        if ram_gb >= min_ram:
            candidates.append(m)

    if not candidates:
        # If all exceed minimum, pick smallest model available
        return min(models, key=lambda x: x.get("recommended_min_ram_gb", 99))

    # Check if any fit in GPU VRAM
    gpu_candidates = []
    for m in candidates:
        min_vram = m.get("recommended_min_vram_gb", 0)
        if min_vram > 0 and vram_gb >= min_vram:
            gpu_candidates.append(m)

    if gpu_candidates:
        # Prefer vision model or balanced 3-4B model
        for m in gpu_candidates:
            if "3.2" in m["id"] or "llama-3.2" in m["id"] or "2b" in m["id"].lower():
                return m
        return gpu_candidates[0]

    # Return best RAM-compatible model
    for m in candidates:
        if "3.2" in m["id"] or "2b" in m["id"].lower():
            return m
    return candidates[0]
