import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify, abort, Response
from chat import Chat, Session, Turn, NO_CONTENT_TOOLS, tool_summary
import re
from rotate_keys import rotate

app = Flask(__name__, template_folder='.', static_folder='.')
chat = Chat()


def find_tool_result(turn, tool_call_id):
	for m in turn:
		if m.get("type") == "tool_result" and m.get("tool_call_id") == tool_call_id:
			return m
	return None

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
app.jinja_env.globals['NO_CONTENT_TOOLS'] = NO_CONTENT_TOOLS

@app.context_processor
def inject_globals():
	return {"TOOLS": [t.schema for t in chat.toolbox.tools], "MODELS": chat.free_models}

@app.template_filter('markdown')
def markdown_filter(text):
	return Turn.render_markdown(text)



@app.route("/api/<session_id>/raw")
def raw_view(session_id):
    messages = Session(session_id).blocks
    if not messages:
        return "Session not found", 404
    text_parts = []
    for msg in messages:
        if msg['type'] == 'prompt':
            prompt = re.sub(r'\[FILE: ([^\]]+)\]\s*\n\[FILE_CONTENT_START\].*?\n\[FILE_CONTENT_END: \1\]', lambda m: f"[FILE: {m.group(1)}]", msg['content'], flags=re.DOTALL)
            prompt = re.sub(r'\n{3,}', '\n\n', prompt).strip()
            text_parts.append(prompt)
        elif msg['type'] == 'reasoning' and msg.get('content'):
            text_parts.append(f"[reasoning] {msg['content']}")
            text_parts.append('')
        elif msg['type'] == 'tool_call':
            for call in msg.get('tool_calls') or []:
                text_parts.append(f"[tool call] {tool_summary(call['function']['name'], call['function']['arguments'])}")
                result = find_tool_result(messages, call['id'])
                if result:
                    output = result.get('content') or ''
                    if len(output) > 200:
                        output = output[:200] + f"... ({len(output)} chars)"
                    text_parts.append(f"[tool result] {output}")
            text_parts.append('')
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
	sessions = chat.group_by_day(archived=True)
	return render_template('archive.html', sessions=sessions)

@app.route('/session/<session_id>')
@app.route('/archive/<session_id>')
def view_session_redirect(session_id):
	return redirect(f'/chat/{session_id}')

@app.route('/chat')
@app.route('/chat/<session_id>')
def chat_view(session_id=None):
	sessions = chat.group_by_day() if session_id is None else None
	session = Session(session_id) if session_id else None
	messages = session.messages if session else []
	blocks = [b for m in messages for b in m.blocks]
	model_list = chat.free_models
	default_model = next((b["model"] for b in reversed(blocks) if b.get("model")), None)
	if default_model:
		pass
	elif model_list:
		default_model = model_list[0].id
	else:
		default_model = None
	return render_template('chat.html',
						   session_id=session_id,
						   sessions=sessions,
						   archived=session.archived if session else False,
						   turns=[m.blocks for m in messages],
						   default_model=default_model,
						   icons=model_icons(),
						   pending_tool_calls=messages[-1].pending if messages else None)

@app.route('/api/<session_id>/archive', methods=['POST'])
def archive_session_route(session_id):
	Session(session_id).archive()
	return redirect('/chat')

@app.route('/api/<session_id>/unarchive', methods=['POST'])
def unarchive_session_route(session_id):
	Session(session_id).unarchive()
	return redirect(f'/chat/{session_id}')

@app.route('/api/markdown', methods=['POST'])
def api_markdown():
	text = request.form.get('text', '')
	return Turn.render_markdown(text)

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
	return jsonify(chat.list())

@app.route('/api/<session_id>')
def api_get_session(session_id):
	return jsonify(Session(session_id).blocks)

@app.route('/api/message', methods=['POST'])
@app.route('/api/<session_id>/message', methods=['POST'])
def api_message(session_id=None):
	prompt = request.form.get('prompt')
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	mode = request.form.get('mode', 'auto')
	session = session_id or request.form.get('session')
	for record in chat.message(prompt, model, reasoning, session, tools, mode):
		session = record["session"]
	return redirect(f'/chat/{session}')

@app.route('/api/<session_id>/resume', methods=['POST'])
def api_resume(session_id):
	action = request.form.get('action')
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	mode = request.form.get('mode', 'auto')
	for record in chat.resume(session_id, action, model, reasoning, tools, mode):
		pass
	return redirect(f'/chat/{session_id}')

@app.route('/api/<session_id>/resume-blocks', methods=['POST'])
def api_resume_blocks(session_id):
	action = request.form.get('action')
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	mode = request.form.get('mode', 'auto')
	def generate():
		for record in chat.resume(session_id, action, model, reasoning, tools, mode):
			yield f"data: {json.dumps(record)}\n\n"
	return Response(generate(), mimetype='text/event-stream')

@app.route('/api/<session_id>/hide/<uuid>', methods=['POST'])
def api_hide_message(session_id, uuid):
	session = Session(session_id)
	message = next((m for m in session.messages if m.uuid == uuid), None)
	if message:
		message.unhide() if message.hidden else message.hide()
	return ('', 204)

@app.route('/api/blocks', methods=['POST'])
@app.route('/api/<session_id>/blocks', methods=['POST'])
def api_blocks(session_id=None):
	prompt = request.form.get('prompt')
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	mode = request.form.get('mode', 'auto')
	session = session_id or request.form.get('session')
	def generate():
		for record in chat.message(prompt, model, reasoning, session, tools, mode):
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
	chat.local.load_models()
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
		chat.local.load_models()
	# Disable reloader to prevent restart on file changes
	# Set FLASK_DEBUG=1 to enable debug mode without reloader, or FLASK_RUN_RELOAD=1 to enable reloader
	use_reloader = os.environ.get("FLASK_RUN_RELOAD", "0") == "1"
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True, use_reloader=use_reloader)
