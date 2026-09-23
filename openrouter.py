import requests
import json
import random
import time
import os

def api_key():
	with open(os.path.join(os.path.dirname(__file__), "key.txt"), "r") as f:
		return f.read().strip()


class Model:
	def __init__(self, provider, id, **fields):
		self.provider = provider
		self.id = id
		self.__dict__.update(fields)

	@property
	def is_free(self):
		return self.id.endswith(":free")

	def message(self, messages, think, tools):
		real_id = self.id.split('/', 1)[1]
		return self.provider.message(messages, real_id, think, tools)


class OpenRouter:
	timeout = 120

	def __init__(self):
		self._cache = None

	def load_models(self):
		print("\033[94mhttps://openrouter.ai/api/v1/models\033[0m", flush=True)
		headers = {"Authorization": f"Bearer {api_key()}"}
		response = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=30)
		self._cache = response.json()["data"]

	@property
	def models(self):
		if self._cache is None:
			return []
		result = []

		CONDITION_KEYS = {'utc_days', 'utc_start', 'utc_end', 'min_prompt_tokens'}

		for model in self._cache:
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

			result.append(Model(self, f"openrouter/{model.get('id')}",
				name=model.get("name"),
				description=model.get("description"),
				context_length=model.get("context_length"),
				supported_parameters=model.get("supported_parameters"),
				input_modalities=model.get("architecture", {}).get("input_modalities"),
				output_modalities=model.get("architecture", {}).get("output_modalities"),
				pricing=base_pricing,
				overrides=overrides_conditions,
				overridden_pricing=overridden_pricing,
			))

		result.sort(key=lambda m: m.id)
		return result

	@property
	def free_models(self):
		return [m for m in self.models if m.is_free]

	def message(self, messages, model=None, think=False, tools=None):
		print("\033[94mhttps://openrouter.ai/api/v1/chat/completions\033[0m", flush=True)
		if model is None:
			model = random.choice(self.models).id.split('/', 1)[1]
		url = "https://openrouter.ai/api/v1/chat/completions"
		headers = {
			"Authorization": f"Bearer {api_key()}",
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
