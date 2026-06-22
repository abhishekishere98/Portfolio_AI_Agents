from __future__ import annotations

import unittest
from unittest.mock import patch

from llm_client import LLMClient


class LLMClientTests(unittest.TestCase):
    @patch.object(LLMClient, "_call_ollama")
    @patch.object(LLMClient, "_call_gemini")
    @patch.object(LLMClient, "_call_groq")
    def test_generate_prefers_groq(self, mock_groq, mock_gemini, mock_ollama):
        mock_groq.return_value = "groq-output"

        output = LLMClient().generate("hello")

        self.assertEqual("groq-output", output)
        mock_groq.assert_called_once_with("hello")
        mock_gemini.assert_not_called()
        mock_ollama.assert_not_called()

    @patch.object(LLMClient, "_call_ollama")
    @patch.object(LLMClient, "_call_gemini")
    @patch.object(LLMClient, "_call_groq")
    def test_generate_falls_back_to_gemini_when_groq_fails(self, mock_groq, mock_gemini, mock_ollama):
        mock_groq.side_effect = RuntimeError("groq down")
        mock_gemini.return_value = "gemini-output"

        output = LLMClient().generate("hello")

        self.assertEqual("gemini-output", output)
        mock_groq.assert_called_once_with("hello")
        mock_gemini.assert_called_once_with("hello")
        mock_ollama.assert_not_called()

    @patch.object(LLMClient, "_call_ollama")
    @patch.object(LLMClient, "_call_gemini")
    @patch.object(LLMClient, "_call_groq")
    def test_generate_falls_back_to_ollama_when_gemini_fails(self, mock_groq, mock_gemini, mock_ollama):
        mock_groq.side_effect = RuntimeError("groq down")
        mock_gemini.side_effect = RuntimeError("gemini down")
        mock_ollama.return_value = "ollama-output"

        output = LLMClient().generate("hello")

        self.assertEqual("ollama-output", output)
        mock_groq.assert_called_once_with("hello")
        mock_gemini.assert_called_once_with("hello")
        mock_ollama.assert_called_once_with("hello")

    @patch.object(LLMClient, "_call_ollama")
    @patch.object(LLMClient, "_call_gemini")
    @patch.object(LLMClient, "_call_groq")
    def test_generate_raises_when_all_providers_fail(self, mock_groq, mock_gemini, mock_ollama):
        mock_groq.side_effect = RuntimeError("groq down")
        mock_gemini.side_effect = RuntimeError("gemini down")
        mock_ollama.side_effect = RuntimeError("ollama down")

        with self.assertRaises(RuntimeError) as context:
            LLMClient().generate("hello")

        self.assertIn("All LLM providers failed", str(context.exception))


if __name__ == "__main__":
    unittest.main()
