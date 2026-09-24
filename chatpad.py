import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify, abort, Response
import markdown
from chat import Chat, list_sessions, group_sessions_by_day, get_session, group_turns, archive_session, unarchive_session, is_archived, tool_summary, find_tool_result, TOOLS
import re
from rotate_keys import rotate

app = Flask(__name__, template_folder='.', static_folder='.')
chat = Chat()

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

@app.template_filter('format_hm')
def format_hm_filter(ts):
	if not ts:
		return ""
	try:
		dt = datetime.strptime(ts[:14], '%Y%m%d%H%M%S')
		return dt.strftime('%H:%M')
	except:
		return ts

@app.template_filter('format_day')
def format_day_filter(day):
	if not day:
		return ""
	try:
		dt = datetime.strptime(day, '%Y%m%d')
		return dt.strftime('%d %b')
	except:
		return day

app.jinja_env.globals['tool_summary'] = tool_summary
app.jinja_env.globals['find_tool_result'] = find_tool_result

@app.context_processor
def inject_globals():
	return {"TOOLS": TOOLS, "MODELS": chat.free_models}

@app.template_filter('markdown')
def markdown_filter(text):
	if text is None:
		return ""
	return markdown.markdown(text, extensions=['tables', 'fenced_code', 'codehilite', 'nl2br'])



@app.route("/api/<session_id>/raw")
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


def model_icons():
	icons = {}
	for f in os.listdir(os.path.join(ROOT, "@@", "models")):
		icons[os.path.splitext(f)[0]] = f"/@@/models/{f}"
	return icons

@app.route('/models')
def models_view():
	return render_template('models.html', models=chat.models, icons=model_icons())

@app.route('/')
def index():
	return redirect('/chat')

@app.route('/archive')
def archive():
	sessions = group_sessions_by_day(list_sessions(archived=True))
	return render_template('archive.html', sessions=sessions)

@app.route('/session/<session_id>')
@app.route('/archive/<session_id>')
def view_session_redirect(session_id):
	return redirect(f'/chat/{session_id}')

@app.route('/chat')
@app.route('/chat/<session_id>')
def chat_view(session_id=None):
	sessions = group_sessions_by_day(list_sessions()) if session_id is None else None
	messages = get_session(session_id) if session_id else []
	model_list = chat.free_models
	default_model = next((m["model"] for m in reversed(messages) if m.get("model")), None)
	if default_model:
		pass
	elif model_list:
		default_model = model_list[0].id
	else:
		default_model = None
	return render_template('chat.html',
						   session_id=session_id,
						   sessions=sessions,
						   archived=is_archived(session_id) if session_id else False,
						   turns=group_turns(messages),
						   default_model=default_model,
						   icons=model_icons())

@app.route('/api/<session_id>/archive', methods=['POST'])
def archive_session_route(session_id):
	archive_session(session_id)
	return redirect('/chat')

@app.route('/api/<session_id>/unarchive', methods=['POST'])
def unarchive_session_route(session_id):
	unarchive_session(session_id)
	return redirect(f'/chat/{session_id}')

@app.route('/api/markdown', methods=['POST'])
def api_markdown():
	text = request.form.get('text', '')
	return markdown_filter(text)

@app.route('/api/models')
def api_models():
	result = []
	for m in chat.free_models:
		fields = dict(vars(m))
		fields.pop("provider", None)
		result.append(fields)
	return jsonify(result)

@app.route('/api/sessions')
def api_sessions():
	return jsonify(list_sessions())

@app.route('/api/<session_id>')
def api_get_session(session_id):
	return jsonify(get_session(session_id))

@app.route('/api/message', methods=['POST'])
@app.route('/api/<session_id>/message', methods=['POST'])
def api_message(session_id=None):
	prompt = request.form.get('prompt')
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	session = session_id or request.form.get('session')
	for record in chat.session_message(prompt, model, reasoning, session, tools):
		session = record["session"]
	return redirect(f'/chat/{session}')

@app.route('/api/blocks', methods=['POST'])
@app.route('/api/<session_id>/blocks', methods=['POST'])
def api_blocks(session_id=None):
	prompt = request.form.get('prompt')
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	session = session_id or request.form.get('session')
	def generate():
		for record in chat.session_message(prompt, model, reasoning, session, tools):
			yield f"data: {json.dumps(record)}\n\n"
	return Response(generate(), mimetype='text/event-stream')

@app.route('/rotate-keys', methods=['POST'])
def rotate_keys():
	try:
		rotate()
	except SystemExit as e:
		return str(e), 500
	return redirect('/chat?rotated=1')

@app.route('/api/refresh-models', methods=['POST'])
def refresh_models_route():
	chat.openrouter.load_models()
	chat.deepseek.load_models()
	return '', 204





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
		chat.openrouter.load_models()
		chat.deepseek.load_models()
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
