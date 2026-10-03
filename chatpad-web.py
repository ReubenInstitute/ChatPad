import os
import json
import threading
import queue
import uuid7
from collections import defaultdict
from datetime import datetime, timezone
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify, abort, Response
from chatpad import ChatPad, Session, Turn, ToolTurn, NO_CONTENT_TOOLS, tool_summary
import re
from rotate_keys import rotate

app = Flask(__name__, template_folder='.', static_folder='.')
chatpad = ChatPad()
stop_requested = set()
pause_requested = set()
subscribers = defaultdict(list)

def broadcast(session_id, record):
	for q in list(subscribers.get(session_id, [])):
		q.put(record)


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

def model_name(model_id):
	# Display string for a model: its human-readable name, falling back to the
	# raw id when the model is unknown (e.g. a session saved by another install).
	if not model_id:
		return ""
	for m in chatpad.models:
		if m.id == model_id:
			return m.name or model_id
	return model_id

def model_icon_slug(model_id):
	# Provider icon filename (without extension) for a model id. OpenRouter and
	# DeepSeek ids embed the vendor as the second path segment, but local ids are
	# just "local/<name>" with no vendor, and the local models are all Qwen.
	if not model_id or "/" not in model_id:
		return None
	provider, _, rest = model_id.partition("/")
	if provider == "local":
		return "qwen"
	return rest.split("/")[0].lstrip("~")

def model_icon_url(icons, model_id):
	slug = model_icon_slug(model_id)
	return icons.get(slug) if slug else None

app.jinja_env.globals['tool_summary'] = tool_summary
app.jinja_env.globals['find_tool_result'] = find_tool_result
app.jinja_env.globals['NO_CONTENT_TOOLS'] = NO_CONTENT_TOOLS
app.jinja_env.globals['model_name'] = model_name
app.jinja_env.globals['model_icon_url'] = model_icon_url

@app.context_processor
def inject_globals():
	return {"TOOLS": [t.schema for t in chatpad.toolbox.tools], "MODELS": chatpad.free_models}

@app.template_filter('markdown')
def markdown_filter(text):
	return Turn.render_markdown(text)


@app.route("/api/sessions/<session_id>/raw")
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


def sse(records, icons):
	names = model_names()
	context_lengths = model_context_lengths()
	for record in records:
		model = record.get("model")
		record["icon"] = model_icon_url(icons, model)
		record["model_name"] = names.get(model) if model else None
		record["context_length"] = context_lengths.get(model) if model else None
		yield f"data: {json.dumps(record)}\n\n"


def model_names():
	# id -> display name, built once per stream so the client can label a turn
	# with the model's name instead of its raw id.
	return {m.id: (m.name or m.id) for m in chatpad.models}


def model_context_lengths():
	# id -> context window, built once per stream so the client can render the
	# same "Max" figure the server-side template shows.
	return {m.id: getattr(m, "context_length", None) for m in chatpad.models}


@app.route('/models')
def models_view():
	return render_template('models.html', models=chatpad.models, icons=model_icons())

@app.route('/')
def main():
	return render_template('main.html', icons=model_icons())

@app.route('/archive')
def archive():
	sessions = chatpad.group_by_day(archived=True)
	return render_template('archive.html', sessions=sessions)

@app.route('/session/<session_id>')
@app.route('/archive/<session_id>')
def view_session_redirect(session_id):
	return redirect(f'/chat/{session_id}')

@app.route('/chat')
@app.route('/chat/<session_id>')
def chat_view(session_id=None):
	sessions = chatpad.group_by_day() if session_id is None else None
	session = Session(session_id) if session_id else None
	messages = session.messages if session else []
	blocks = [b for m in messages for b in m.blocks]
	model_list = chatpad.free_models
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

@app.route('/api/markdown', methods=['POST'])
def api_markdown():
	text = request.form.get('text', '')
	return Turn.render_markdown(text)

@app.route('/api/models')
def api_models():
	chatpad.openrouter.load_models()
	chatpad.deepseek.load_models()
	chatpad.local.load_models()
	result = []
	for m in chatpad.free_models:
		fields = dict(vars(m))
		fields["provider"] = type(fields["provider"]).__name__
		result.append(fields)
	return jsonify(result)

@app.route('/api/sessions/<session_id>/stop', methods=['POST'])
def api_stop_session(session_id):
	stop_requested.add(session_id)
	return jsonify({"uuid": session_id, "stopped": True})

@app.route('/api/sessions/<session_id>/settings/model', methods=['POST'])
def api_session_setting_model(session_id):
	settings = Session(session_id).settings
	settings.model = request.get_json()['value']
	settings.save()
	return jsonify({"uuid": session_id})

@app.route('/api/sessions/<session_id>/settings/system_model', methods=['POST'])
def api_session_setting_system_model(session_id):
	settings = Session(session_id).settings
	settings.system_model = request.get_json()['value']
	settings.save()
	return jsonify({"uuid": session_id})

@app.route('/api/sessions/<session_id>/settings/tools', methods=['POST'])
def api_session_setting_tools(session_id):
	settings = Session(session_id).settings
	settings.tools = request.get_json()['value']
	settings.save()
	return jsonify({"uuid": session_id})

@app.route('/api/sessions/<session_id>/settings/mode', methods=['POST'])
def api_session_setting_mode(session_id):
	settings = Session(session_id).settings
	settings.mode = request.get_json()['value']
	settings.save()
	return jsonify({"uuid": session_id})

@app.route('/api/sessions/<session_id>/settings/max_steps', methods=['POST'])
def api_session_setting_max_steps(session_id):
	settings = Session(session_id).settings
	settings.max_steps = request.get_json()['value']
	settings.save()
	return jsonify({"uuid": session_id})

@app.route('/api/sessions/<session_id>/settings/think', methods=['POST'])
def api_session_setting_think(session_id):
	settings = Session(session_id).settings
	settings.think = request.get_json()['value']
	settings.save()
	return jsonify({"uuid": session_id})

@app.route('/api/sessions/<session_id>/pause', methods=['POST'])
def api_pause_session(session_id):
	pause_requested.add(session_id)
	return jsonify({"uuid": session_id, "paused": True})

@app.route('/api/sessions/<session_id>/resume', methods=['POST'])
def api_resume_session(session_id):
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	mode = request.form.get('mode', 'auto')
	session_obj = Session(session_id)
	session_obj.status = "busy"
	broadcast(session_id, {"type": "status", "status": "busy", "session": session_id})
	records = chatpad.continue_message(session_id, model, reasoning, tools, mode, pause_requested=pause_requested)
	threading.Thread(target=run_records, args=(records, session_obj), daemon=True).start()
	return jsonify({"session": session_id})

@app.route('/api/sessions/<session_id>/archive', methods=['POST'])
def api_archive_session(session_id):
	Session(session_id).archive()
	return jsonify({"uuid": session_id, "archived": True})

@app.route('/api/sessions/<session_id>/unarchive', methods=['POST'])
def api_unarchive_session(session_id):
	Session(session_id).unarchive()
	return jsonify({"uuid": session_id, "archived": False})

@app.route('/api/sessions/<session_id>/messages/<uuid>/hide', methods=['POST'])
def api_hide_message(session_id, uuid):
	message = next(m for m in Session(session_id).messages if m.uuid == uuid)
	message.hide()
	return jsonify({"uuid": uuid, "hidden": True})

@app.route('/api/sessions/<session_id>/messages/<uuid>/unhide', methods=['POST'])
def api_unhide_message(session_id, uuid):
	message = next(m for m in Session(session_id).messages if m.uuid == uuid)
	message.unhide()
	return jsonify({"uuid": uuid, "hidden": False})

def run_records(records, session_obj):
	paused = False
	try:
		for record in records:
			if record.get("type") == "paused":
				paused = True
			broadcast(session_obj.uuid, record)
			if session_obj.uuid in stop_requested:
				stop_requested.discard(session_obj.uuid)
				records.close()
				break
	finally:
		pause_requested.discard(session_obj.uuid)
		session_obj.status = "paused" if paused else "idle"
		broadcast(session_obj.uuid, {"type": "status", "status": session_obj.status, "session": session_obj.uuid})

@app.route('/api/message', methods=['POST'])
@app.route('/api/sessions/<session_id>/message', methods=['POST'])
def api_message(session_id=None):
	prompt = request.form.get('prompt')
	model = request.form.get('model')
	reasoning = 'reasoning' in request.form
	tools = request.form.getlist('tools')
	mode = request.form.get('mode', 'auto')
	if session_id is None:
		session_id = str(uuid7.create(datetime.now(timezone.utc)))
	session_obj = Session(uuid=session_id)
	session_obj.status = "busy"
	broadcast(session_id, {"type": "status", "status": "busy", "session": session_id})
	records = chatpad.message(prompt, model, reasoning, session_id, tools, mode, pause_requested=pause_requested)
	threading.Thread(target=run_records, args=(records, session_obj), daemon=True).start()
	return jsonify({"session": session_id})

@app.route('/api/sessions/<session_id>/stream')
def api_stream_session(session_id, uuid=None):
	uuid = request.args.get('uuid')
	q = queue.Queue()
	subscribers[session_id].append(q)
	backlog = []
	messages = Session(session_id).messages
	for message in messages:
		for turn in message.turns:
			if uuid is not None and turn.uuid <= uuid:
				continue
			if isinstance(turn, ToolTurn):
				backlog.append({"type": "tool_call", "content": None,
						"tool_calls": [{"id": turn.uuid, "type": "function",
								"function": {"name": turn.tool, "arguments": turn.arguments}}],
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_id})
				backlog.append({"type": "tool_result", "tool_call_id": turn.uuid, "name": turn.tool,
						"content": turn.result, "error": turn.error,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_id})
				continue
			if turn.prompt is not None:
				backlog.append({"type": "prompt", "content": turn.prompt, "model": turn.model,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_id})
			if turn.reasoning:
				backlog.append({"type": "reasoning", "content": turn.reasoning,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_id})
			if turn.error:
				backlog.append({"type": "error", "error": turn.error, "model": turn.model,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_id})
			if turn.response:
				backlog.append({"type": "response", "content": turn.response, "model": turn.model,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_id})
	if messages and messages[-1].pending:
		backlog.append({"type": "await_approval", "session": session_id})
	def gen():
		try:
			for record in backlog:
				yield f"data: {json.dumps(record)}\n\n"
			while True:
				record = q.get()
				yield f"data: {json.dumps(record)}\n\n"
		finally:
			subscribers[session_id].remove(q)
	return Response(gen(), mimetype='text/event-stream')

@app.route('/api/sessions')
def api_sessions():
	return jsonify([{"uuid": uuid, "archived": archived}
			for archived in (False, True) for uuid, _, _ in chatpad.list(archived)])

@app.route('/api/sessions/<session_id>')
def api_session(session_id):
	session = Session(session_id)
	return jsonify({"uuid": session.uuid, "archived": session.archived, "status": session.status,
			"settings": session.settings.to_dict(), "messages": [m.to_dict() for m in session.messages]})

@app.route('/rotate-keys', methods=['POST'])
def rotate_keys():
	try:
		rotate()
	except SystemExit as e:
		return str(e), 500
	return redirect('/chat?rotated=1')





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
		chatpad.openrouter.load_models()
		chatpad.deepseek.load_models()
		chatpad.local.load_models()
	app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True, threaded=True)
