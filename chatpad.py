import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify, abort
import markdown
from openrouter import OpenRouter
from chat import session_message, list_sessions, get_session
import re

app = Flask(__name__, template_folder='.', static_folder='.')

BASE_DIR = "/sdcard"
ROOT = os.path.dirname(os.path.abspath(__file__))
URLROOT = os.getcwd()

@app.template_filter('format_number')
def format_number(n):
	if n is None:
		return ""
	if n == 0:
		return "0"
	if n % 1024 == 0:
		if n < 1024:
			return f"{int(n)} B"
		units = ["KiB", "MiB", "GiB", "TiB"]
		i = -1
		while n >= 1024 and i < len(units) - 1:
			n /= 1024.0
			i += 1
		s = f"{n:.1f}".rstrip("0").rstrip(".")
		return f"{s} {units[i]}"
	else:
		if n < 1000:
			return str(int(n))
		units = ["K", "M", "B", "T"]
		i = -1
		while n >= 1000 and i < len(units) - 1:
			n /= 1000.0
			i += 1
		s = f"{n:.1f}".rstrip("0").rstrip(".")
		return f"{s}{units[i]}"




@app.template_filter('format_timestamp')
def format_timestamp_filter(ts):
	if not ts:
		return ""
	try:
		dt = datetime.strptime(ts[:14], '%Y%m%d%H%M%S')
		return dt.strftime('%d %b %Y %H:%M:%S')
	except:
		return ts

@app.template_filter('markdown')
def markdown_filter(text):
	if text is None:
		return ""
	return markdown.markdown(text, extensions=['tables', 'fenced_code', 'codehilite', 'nl2br'])



@app.route("/session/<session_id>/raw")
def raw_view(session_id):
    messages = get_session(session_id)
    if not messages:
        return "Session not found", 404
    text_parts = []
    for msg in messages:
        if 'prompt' in msg and msg['prompt'] is not None:
            prompt = re.sub(r'\[FILE: ([^\]]+)\]\s*\n\[FILE_CONTENT_START\].*?\n\[FILE_CONTENT_END: \1\]', lambda m: f"[FILE: {m.group(1)}]", msg['prompt'], flags=re.DOTALL)
            prompt = re.sub(r'\n{3,}', '\n\n', prompt).strip()
            text_parts.append(prompt)
        if 'response' in msg and msg['response'] is not None:
            text_parts.append(f"[{msg['model']}] {msg['response']}")
        text_parts.append('')
    export_text = '\n\n'.join(text_parts).strip()
    return export_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/models')
def show_models():
	models = OpenRouter.models()
	return render_template('models.html', models=models)

@app.route('/')
def index():
	sessions = list_sessions()
	model_list = OpenRouter.models()
	return render_template('index.html', sessions=sessions, models=model_list)

@app.route('/session/<session_id>')
def view_session(session_id):
	messages = get_session(session_id)
	model_list = OpenRouter.models()
	if messages and messages[-1].get("model"):
		default_model = messages[-1]["model"]
	elif model_list:
		default_model = model_list[0]["id"]
	else:
		default_model = None
	return render_template('session.html',
						   session_id=session_id,
						   messages=messages,
						   models=model_list,
						   default_model=default_model)

@app.route('/api/models')
def api_models():
	return jsonify(OpenRouter.models())

@app.route('/api/sessions')
def api_sessions():
	return jsonify(list_sessions())

@app.route('/api/sessions/<session_id>')
def api_get_session(session_id):
	return jsonify(get_session(session_id))

@app.route('/api/message', methods=['POST'])
@app.route('/api/message/<session_id>', methods=['POST'])
def api_message(session_id=None):
	prompt = request.form.get('prompt')
	model = request.form.get('model', 'stealth/ox-alpha')
	reasoning = 'reasoning' in request.form
	session = session_id or request.form.get('session')
	response = session_message(prompt, model, reasoning, session)
	return redirect(f'/session/{response["session"]}')





@app.route('/<path:filename>')
def serve_file(filename):
    # First try to serve from the current working directory (URLROOT)
    urlroot_path = os.path.join(URLROOT, filename)
    if os.path.isfile(urlroot_path):
        return send_from_directory(URLROOT, filename)
    # Fallback to the application's own directory (ROOT)
    return send_from_directory(ROOT, filename)



if __name__ == "__main__":
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
