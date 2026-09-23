import json
import os
import time
import requests

from openrouter import Model


def api_key():
	with open(os.path.join(os.path.dirname(__file__), "deepseek.txt"), "r") as f:
		return f.read().strip()


class DeepSeek:
	timeout = 120

	def __init__(self):
		self._cache = None

	def load_models(self):
		print("\033[94mhttps://api.deepseek.com/v1/models\033[0m", flush=True)
		headers = {"Authorization": f"Bearer {api_key()}"}
		response = requests.get("https://api.deepseek.com/v1/models", headers=headers, timeout=30)
		self._cache = response.json()["data"]

	@property
	def models(self):
		if self._cache is None:
			return []
		result = []
		for model in self._cache:
			result.append(Model(self, f"deepseek/deepseek/{model.get('id')}", True,
				name=model.get("name"),
				description=None,
				context_length=model.get("context_window"),
				supported_parameters=["tools", "reasoning"],
				input_modalities=model.get("input_modalities"),
				output_modalities=model.get("output_modalities"),
				pricing={},
				overrides=[],
				overridden_pricing=[],
			))
		result.sort(key=lambda m: m.id)
		return result

	@property
	def free_models(self):
		return self.models

	def message(self, messages, model, think=False, tools=None):
		print("\033[94mhttps://api.deepseek.com/v1/chat/completions\033[0m", flush=True)
		url = "https://api.deepseek.com/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {api_key()}",
			"Content-Type": "application/json"
		}
		payload = {
			"model": model.split('/', 1)[1],  # drop the "deepseek/" vendor segment, real API wants just deepseek-flash
			"messages": messages,
			"effort": "high" if think else "low",
		}
		if tools:
			payload["tools"] = tools
		try:
			response = requests.post(url, headers=headers, json=payload, timeout=(10, DeepSeek.timeout), stream=True)
			deadline = time.monotonic() + DeepSeek.timeout
			body = b""
			for chunk in response.iter_content(8192):
				body += chunk
				if time.monotonic() > deadline:
					raise TimeoutError(f"no complete reply after {DeepSeek.timeout} seconds")
			result = json.loads(body)
			if "error" in result:
				error = result["error"]
				return {"error": {"message": error.get("message", str(error)), "code": error.get("code")}}
			raw_message = result["choices"][0]["message"]
			message = {"role": raw_message.get("role"), "content": raw_message.get("content")}
			if raw_message.get("reasoning_content"):
				message["reasoning"] = raw_message["reasoning_content"]
			if raw_message.get("tool_calls"):
				message["tool_calls"] = raw_message["tool_calls"]
			result["choices"][0]["message"] = message
			return result
		except Exception as e:
			return {"error": {"message": f"{type(e).__name__}: {e}", "code": None}}
