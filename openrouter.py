import requests
import json
import random
import os

with open(os.path.join(os.path.dirname(__file__), "key.txt"), "r") as f:
	API_KEY = f.read().strip()

class OpenRouter:
	free_only = True
	#free_only = False

	@staticmethod
	def models(free=True):
		headers = {"Authorization": f"Bearer {API_KEY}"}
		response = requests.get("https://openrouter.ai/api/v1/models", headers=headers)
		data = response.json()
		with open("models.json", "w") as f:
			json.dump(data, f, indent=2)

		all_models = data["data"]
		result = []

		CONDITION_KEYS = {'utc_days', 'utc_start', 'utc_end', 'min_prompt_tokens'}

		for model in all_models:
			if OpenRouter.free_only:
				raw_pricing = model.get("pricing", {})
				# Keep original free-only logic unchanged: check all values equal 0.0
				if free:
					if not all(float(v) == 0.0 for v in raw_pricing.values() if isinstance(v, (int, float))):
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
				"pricing": base_pricing,
				"overrides": overrides_conditions,
				"overridden_pricing": overridden_pricing
			})

		return result




	@staticmethod
	def message(prompt, model=None, think=False, history=[]):
		if model is None:
			available = OpenRouter.models()
			model = random.choice(available)["id"]
		messages = []
		for user_msg, assistant_msg in history:
			messages.append({"role": "user", "content": user_msg})
			if assistant_msg:
				messages.append({"role": "assistant", "content": assistant_msg})
		messages.append({"role": "user", "content": prompt})
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
		response = requests.post(url, headers=headers, json=payload)
		return response.json()
