import unittest
import asyncio
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from server.model_manager.manager import ModelManager
from launcher.model_scanner import select_best_model

class TestModelManager(unittest.TestCase):
    def setUp(self):
        models_dir = root_dir / "models"
        config = {
            "model": {
                "active_model": "llama3.2:latest",
                "max_concurrency": 2,
                "ollama_host": "http://127.0.0.1:11434"
            }
        }
        self.mgr = ModelManager(models_root=str(models_dir), config=config)

    def test_load_registry(self):
        registry_models = self.mgr.load_registry()
        self.assertGreater(len(registry_models), 0)
        ids = [m["id"] for m in registry_models]
        self.assertIn("llama3.2:latest", ids)
        print(f"  [OK] Registry models found: {len(registry_models)}")

    def test_compatibility_check(self):
        model = {
            "id": "test_model",
            "recommended_min_ram_gb": 8,
            "recommended_min_vram_gb": 4
        }
        # Low RAM machine: 4GB RAM, 0 VRAM -> incompatible
        res_low = self.mgr.check_compatibility(model, ram_gb=4.0, vram_gb=0.0)
        self.assertFalse(res_low["compatible"])
        self.assertFalse(res_low["can_accelerate_gpu"])

        # High spec machine: 16GB RAM, 6GB VRAM -> compatible & accelerated
        res_high = self.mgr.check_compatibility(model, ram_gb=16.0, vram_gb=6.0)
        self.assertTrue(res_high["compatible"])
        self.assertTrue(res_high["can_accelerate_gpu"])

    def test_model_selector(self):
        models = [
            {"id": "heavy:12b", "recommended_min_ram_gb": 16, "recommended_min_vram_gb": 8},
            {"id": "llama3.2:latest", "recommended_min_ram_gb": 4, "recommended_min_vram_gb": 2},
            {"id": "tiny:1b", "recommended_min_ram_gb": 2, "recommended_min_vram_gb": 0}
        ]
        # Laptop with 16GB RAM and 6GB VRAM should pick llama3.2 (fits VRAM)
        best = select_best_model(models, ram_gb=16.0, vram_gb=6.0)
        self.assertEqual(best["id"], "llama3.2:latest")

    def test_concurrency_queue(self):
        async def _test():
            stats = self.mgr.queue.get_stats()
            self.assertEqual(stats["active_requests"], 0)
            await self.mgr.queue.acquire()
            stats2 = self.mgr.queue.get_stats()
            self.assertEqual(stats2["active_requests"], 1)
            self.mgr.queue.release()
            stats3 = self.mgr.queue.get_stats()
            self.assertEqual(stats3["active_requests"], 0)
        asyncio.run(_test())

if __name__ == "__main__":
    unittest.main()
