import os
import unittest
from unittest import mock

from pvm import config
from pvm.render.video import default_jobs


class LlmRoutingTest(unittest.TestCase):
    def settings(self, env: dict):
        config.get_settings.cache_clear()
        try:
            with mock.patch.object(config, "load_dotenv", return_value={}), mock.patch.dict(os.environ, env, clear=True):
                return config.get_settings()
        finally:
            config.get_settings.cache_clear()

    def test_agent_plan_key_covers_the_planner(self):
        s = self.settings({"AGENT_PLAN_API_KEY": "plan-key"})
        self.assertEqual((s.llm_api_key, s.llm_base_url, s.llm_model),
                         ("plan-key", config.AGENT_PLAN_BASE_URL, "deepseek-v4-pro-beta"))

    def test_own_deepseek_key_wins(self):
        s = self.settings({"AGENT_PLAN_API_KEY": "plan-key", "PVM_LLM_API_KEY": "ds-key"})
        self.assertEqual((s.llm_api_key, s.llm_base_url, s.llm_model), ("ds-key", "https://api.deepseek.com", "deepseek-chat"))

    def test_no_keys_means_no_llm(self):
        self.assertIsNone(self.settings({}).llm_api_key)


class RenderJobsTest(unittest.TestCase):
    def test_short_renders_stay_in_one_process(self):
        self.assertEqual(default_jobs(299), 1)
        self.assertGreaterEqual(default_jobs(3000), 1)


if __name__ == "__main__":
    unittest.main()
