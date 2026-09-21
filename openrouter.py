import requests
import json
import random
import time
import os

with open(os.path.join(os.path.dirname(__file__), "key.txt"), "r") as f:
	API_KEY = f.read().strip()

class OpenRouter:
	timeout = 120
	free_only = True
	#free_only = False

	@staticmethod
	def models(free=True):
		headers = {"Authorization": f"Bearer {API_KEY}"}
		try:
			response = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=30)
			data = response.json()
			all_models = data["data"]
		except Exception:
			return []
		with open("models.json", "w") as f:
			json.dump(data, f, indent=2)
		result = []

		CONDITION_KEYS = {'utc_days', 'utc_start', 'utc_end', 'min_prompt_tokens'}

		for model in all_models:
			if OpenRouter.free_only and free:
				if not model.get("id", "").endswith(":free"):
					continue

			raw_pricing = model.get("pricing", {})

			# Base pricing: all keys except 'overrides'
			base_pricing = {
				k: (None if v == -1 else v)
				for k, v in raw_pricing.items()
				if k != 'overrides'
			}

			# Overrides handling
			overrides_raw = raw_pricing.get('overrides', [])
			overrides_conditions = []
			overridden_pricing = []

			for override in overrides_raw:
				cond = {}
				price_ov = {}
				for k, v in override.items():
					if k in CONDITION_KEYS:
						cond[k] = v
					else:
						# Normalize -1 to None for price fields
						price_ov[k] = None if v == -1 else v
				overrides_conditions.append(cond)
				overridden_pricing.append(price_ov)

			result.append({
				"id": model.get("id"),
				"name": model.get("name"),
				"description": model.get("description"),
				"context_length": model.get("context_length"),
				"supported_parameters": model.get("supported_parameters"),
				"pricing": base_pricing,
				"overrides": overrides_conditions,
				"overridden_pricing": overridden_pricing
			})

		return result




	@staticmethod
	def message(messages, model=None, think=False, tools=None):
		if model is None:
			available = OpenRouter.models()
			model = random.choice(available)["id"]
		url = "https://openrouter.ai/api/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {API_KEY}",
			"Content-Type": "application/json"
		}
		payload = {
			"model": model,
			"messages": messages,
			"reasoning": {"enabled": think}
		}
		if tools:
			payload["tools"] = tools
		try:
			response = requests.post(url, headers=headers, json=payload, timeout=(10, OpenRouter.timeout), stream=True)
			deadline = time.monotonic() + OpenRouter.timeout
			body = b""
			for chunk in response.iter_content(8192):
				body += chunk
				if time.monotonic() > deadline:
					raise TimeoutError(f"no complete reply after {OpenRouter.timeout} seconds")
			result = json.loads(body)
			if "error" not in result:
				result["choices"][0]["message"]
		except Exception as e:
			result = {"error": {"message": f"{type(e).__name__}: {e}", "code": None}}
		return result
