import json
import os
import requests

from openrouter import Model, http_error


def api_key():
	with open(os.path.join(os.path.dirname(__file__), "deepseek.txt"), "r") as f:
		return f.read().strip()


class DeepSeek:
	timeout = 120

	# Thinking mode is stateful: reasoning from earlier assistant messages must
	# be replayed as `reasoning_content`, otherwise every follow-up request is
	# rejected with HTTP 400. See Session.history in chatpad.py.
	requires_reasoning_content = True

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
			"stream": True,
			"stream_options": {"include_usage": True},
		}
		if tools:
			payload["tools"] = tools

		content_parts = []
		reasoning_parts = []
		tool_calls = {}
		usage = {}
		finish_reason = None

		try:
			response = requests.post(url, headers=headers, json=payload, timeout=(10, DeepSeek.timeout), stream=True)
			try:
				failure = http_error(response)
				if failure:
					yield failure
					return
				for raw_line in response.iter_lines():
					if not raw_line:
						continue
					line = raw_line.decode("utf-8")
					if not line.startswith("data: "):
						continue
					data = line[len("data: "):]
					if data == "[DONE]":
						break
					chunk = json.loads(data)
					if "error" in chunk:
						error = chunk["error"]
						yield {"error": {"message": error.get("message", str(error)), "code": error.get("code")}}
						return
					if chunk.get("usage"):
						usage = chunk["usage"]
					choices = chunk.get("choices") or []
					if not choices:
						continue
					choice = choices[0]
					if choice.get("finish_reason"):
						finish_reason = choice["finish_reason"]
					delta = choice.get("delta") or {}
					if delta.get("reasoning_content"):
						reasoning_parts.append(delta["reasoning_content"])
						yield {"delta": "reasoning", "text": delta["reasoning_content"]}
					if delta.get("content"):
						content_parts.append(delta["content"])
						yield {"delta": "content", "text": delta["content"]}
					if delta.get("tool_calls"):
						for tc in delta["tool_calls"]:
							idx = tc.get("index", 0)
							call = tool_calls.setdefault(idx, {"id": None, "type": "function", "function": {"name": "", "arguments": ""}})
							if tc.get("id"):
								call["id"] = tc["id"]
							fn = tc.get("function") or {}
							if fn.get("name"):
								call["function"]["name"] += fn["name"]
							if fn.get("arguments"):
								call["function"]["arguments"] += fn["arguments"]
			finally:
				response.close()
		except Exception as e:
			yield {"error": {"message": f"{type(e).__name__}: {e}", "code": None}}
			return

		message = {"role": "assistant", "content": "".join(content_parts) or None}
		if reasoning_parts:
			message["reasoning"] = "".join(reasoning_parts)
		if tool_calls:
			message["tool_calls"] = [tool_calls[i] for i in sorted(tool_calls)]
		result = {"choices": [{"message": message, "finish_reason": finish_reason}], "usage": usage}
		yield {"result": result}
