import os
import unittest
from unittest import mock

from pvm import config
from pvm.llm import make_llm
from pvm.render.video import default_jobs
from pvm.util import PvmError


class SettingsTest(unittest.TestCase):
    def settings(self, env: dict):
        config.get_settings.cache_clear()
        try:
            with mock.patch.object(config, "load_dotenv", return_value={}), mock.patch.dict(os.environ, env, clear=True):
                return config.get_settings()
        finally:
            config.get_settings.cache_clear()

    def test_agent_plan_key_covers_the_planner_with_v41_flash(self):
        s = self.settings({"AGENT_PLAN_API_KEY": "plan-key"})
        self.assertEqual((s.llm_api_key, s.llm_base_url, s.llm_model),
                         ("plan-key", config.AGENT_PLAN_BASE_URL, "deepseek-v4.1-flash"))
        llm = make_llm(s)
        self.assertEqual((llm.model, llm.rates), ("deepseek-v4.1-flash", (2.5, 2.5)))  # billed in AFP on the plan
        self.assertEqual(self.settings({"AGENT_PLAN_API_KEY": "k", "PVM_LLM_MODEL": "deepseek-v4-pro"}).llm_model,
                         "deepseek-v4-pro")

    def test_own_deepseek_key_wins(self):
        s = self.settings({"AGENT_PLAN_API_KEY": "plan-key", "PVM_LLM_API_KEY": "ds-key"})
        self.assertEqual((s.llm_api_key, s.llm_base_url, s.llm_model), ("ds-key", "https://api.deepseek.com", "deepseek-chat"))
        self.assertIsNone(make_llm(s).rates)  # DeepSeek bills its own account, not the plan's AFP

    def test_no_keys_means_no_llm(self):
        s = self.settings({})
        self.assertIsNone(s.llm_api_key)
        with self.assertRaises(PvmError) as ctx:
            make_llm(s)
        self.assertIn("AGENT_PLAN_API_KEY", str(ctx.exception))

    def test_image_model_default_and_price_override(self):
        s = self.settings({})
        self.assertEqual((s.image_model, s.afp_per_image), ("doubao-seedream-5-0-pro", None))
        self.assertEqual(self.settings({"PVM_AFP_PER_IMAGE": "120"}).afp_per_image, 120)


class RenderJobsTest(unittest.TestCase):
    def test_short_renders_stay_in_one_process(self):
        self.assertEqual(default_jobs(299), 1)
        self.assertGreaterEqual(default_jobs(3000), 1)


if __name__ == "__main__":
    unittest.main()
