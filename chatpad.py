import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify, abort
import markdown
from openrouter import OpenRouter
from chat import session_message, list_sessions, get_session, group_turns, archive_session, unarchive_session, tool_summary
import re
from rotate_keys import rotate

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

@app.template_filter('format_time')
def format_time_filter(ts):
	if not ts:
		return ""
	try:
		dt = datetime.strptime(ts[:14], '%Y%m%d%H%M%S')
		return dt.strftime('%H:%M:%S')
	except:
		return ts

app.jinja_env.globals['tool_summary'] = tool_summary

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
        if msg['type'] == 'prompt':
            prompt = re.sub(r'\[FILE: ([^\]]+)\]\s*\n\[FILE_CONTENT_START\].*?\n\[FILE_CONTENT_END: \1\]', lambda m: f"[FILE: {m.group(1)}]", msg['content'], flags=re.DOTALL)
            prompt = re.sub(r'\n{3,}', '\n\n', prompt).strip()
            text_parts.append(prompt)
        elif msg['type'] == 'response' and msg.get('content') is not None:
            text_parts.append(f"[{msg['model']}] {msg['content']}")
            text_parts.append('')
    export_text = '\n\n'.join(text_parts).strip()
    return export_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/models')
def show_models():
	models = OpenRouter.models(free=False)
	free = [m for m in models if m["id"].endswith(":free")]
	other = [m for m in models if not m["id"].endswith(":free")]
	return render_template('models.html', free=free, other=other)

@app.route('/')
def index():
	sessions = list_sessions()
	model_list = OpenRouter.models()
	return render_template('index.html', sessions=sessions, models=model_list)

@app.route('/archive')
def archive():
	sessions = list_sessions(archived=True)
	return render_template('archive.html', sessions=sessions)

@app.route('/session/<session_id>')
@app.route('/archive/<session_id>')
def view_session(session_id):
	messages = get_session(session_id)
	model_list = OpenRouter.models()
	default_model = next((m["model"] for m in reversed(messages) if m.get("model")), None)
	if default_model:
		pass
	elif model_list:
		default_model = model_list[0]["id"]
	else:
		default_model = None
	return render_template('session.html',
						   session_id=session_id,
						   turns=group_turns(messages),
						   models=model_list,
						   default_model=default_model)

@app.route('/session/<session_id>/archive', methods=['POST'])
def archive_session_route(session_id):
	archive_session(session_id)
	return redirect(f'/archive/{session_id}')

@app.route('/session/<session_id>/unarchive', methods=['POST'])
def unarchive_session_route(session_id):
	unarchive_session(session_id)
	return redirect(f'/session/{session_id}')

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

@app.route('/rotate-keys', methods=['POST'])
def rotate_keys():
	try:
		rotate()
	except SystemExit as e:
		return str(e), 500
	return redirect('/?rotated=1')





@app.route('/<path:filename>')
def serve_file(filename):
    # First try to serve from the current working directory (URLROOT)
    urlroot_path = os.path.join(URLROOT, filename)
    if os.path.isfile(urlroot_path):
        return send_from_directory(URLROOT, filename)
    # Fallback to the application's own directory (ROOT)
    return send_from_directory(ROOT, filename)



if __name__ == "__main__":
	if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
		OpenRouter.load_models()
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
