from flask import Flask, render_template, request, session, jsonify
from openai import OpenAI
import markdown
import os
import requests
import time

app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='/')
app.secret_key = os.urandom(24)

try:
	with open("deepseek.txt", "r") as f:
		DEEPSEEK_API_KEY = f.read().strip()
except FileNotFoundError:
	DEEPSEEK_API_KEY = None
	print("Error: deepseek.txt not found. Please create this file with your DeepSeek API key.")
except Exception as e:
	DEEPSEEK_API_KEY = None
	print(f"Error reading deepseek.txt: {e}")

DEEPSEEK_API_BASE = "https://api.deepseek.com/v1"
CHAT_MODEL_NAME = "deepseek-chat"
REASONING_MODEL_NAME = "deepseek-reasoner"
BALANCE_URL = "https://api.deepseek.com/user/balance"

if DEEPSEEK_API_KEY:
	client = OpenAI(
		api_key=DEEPSEEK_API_KEY,
		base_url=DEEPSEEK_API_BASE
	)
else:
	client = None
	print("DeepSeek API client not initialized due to missing API key")

balance_cache = {
	"last_fetch": 0,
	"data": None
}

def get_user_balance():
	global balance_cache
	if time.time() - balance_cache["last_fetch"] < 30 and balance_cache["data"]:
		return balance_cache["data"]
	if not DEEPSEEK_API_KEY:
		return None
	try:
		headers = {
			"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
			"Accept": "application/json"
		}
		response = requests.get(BALANCE_URL, headers=headers)
		if response.status_code == 200:
			balance_data = response.json()
			balance_cache = {
				"last_fetch": time.time(),
				"data": balance_data
			}
			return balance_data
		return None
	except Exception as e:
		print(f"Error fetching balance: {e}")
		return None

@app.route("/")
def index():
	processed_messages = []
	if "chat_history" in session:
		try:
			for msg in session["chat_history"]:
				processed_msg = {
					'role': msg['role'],
					'content_html': markdown.markdown(msg['content'])
				}
				if 'reasoning_content' in msg and msg['reasoning_content']:
					processed_msg['reasoning_html'] = markdown.markdown(msg['reasoning_content'])
				processed_messages.append(processed_msg)
		except Exception as e:
			print(f"Error processing messages: {e}")
	balance_data = get_user_balance()
	return render_template("deepseek.html", messages=processed_messages, balance=balance_data)

@app.route("/chat", methods=["POST"])
def chat():
	if not client:
		return jsonify({"error": "DeepSeek API client not configured"}), 500
	if "chat_history" not in session:
		session["chat_history"] = []
	data = request.get_json()
	user_message = data["message"]
	use_reasoning = data.get("use_reasoning", False)
	model_to_use = REASONING_MODEL_NAME if use_reasoning else CHAT_MODEL_NAME
	session["chat_history"].append({"role": "user", "content": user_message})
	session.modified = True
	try:
		api_messages = [{"role": msg["role"], "content": msg["content"]} 
				for msg in session["chat_history"]]
		response = client.chat.completions.create(
			model=model_to_use,
			messages=api_messages,
			stream=False
		)
		content = response.choices[0].message.content or ""
		reasoning = getattr(response.choices[0].message, "reasoning_content", "") or ""
		session["chat_history"].append({
			"role": "assistant",
			"content": content,
			"reasoning_content": reasoning
		})
		session.modified = True
		return jsonify({
			"content": content,
			"reasoning": reasoning,
			"balance": get_user_balance()
		})
	except Exception as e:
		error_msg = f"Error: {str(e)}"
		return jsonify({"error": error_msg}), 500

@app.route("/balance", methods=["GET"])
def get_balance():
	balance_data = get_user_balance()
	return jsonify(balance_data)

if __name__ == "__main__":
	app.run(debug=True, port=5000)
