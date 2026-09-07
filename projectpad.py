import json
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, send_from_directory, jsonify, abort, Response
import markdown
from openrouter import OpenRouter
from chat import session_message, list_sessions, get_session, stream_session_message
import re

app = Flask(__name__, template_folder='.', static_folder='.')

BASE_DIR = "/sdcard"



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


@app.route('/stream/<session_id>', methods=['POST'])
def stream_route(session_id):
	prompt = request.form['prompt']
	model = request.form['model']
	reasoning = 'reasoning' in request.form
	def generate():
		for chunk in stream_session_message(prompt, model, reasoning, session_id):
			yield f"data: {json.dumps(chunk)}\n\n"
	return Response(generate(), mimetype='text/event-stream')




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












TEXT_EXTENSIONS = {
	'.txt', '.md', '.markdown', '.html', '.htm', '.css', '.js', '.mjs',
	'.jsx', '.ts', '.tsx', '.py', '.java', '.c', '.cpp', '.h', '.hpp',
	'.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
	'.log', '.sh', '.bash', '.zsh', '.bat', '.ps1', '.rb', '.go', '.rs',
	'.swift', '.kt', '.scala', '.pl', '.lua', '.r', '.m', '.mm', '.php',
	'.sql', '.vue', '.svelte', '.astro'}
AUDIO_EXTENSIONS = {'mp3', 'm4a', 'wav'}
VIDEO_EXTENSIONS = {'mp4'}
IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'bmp'}
SKIP_FOLDERS = {'__pycache__', '.git'}
SKIP_FILENAMES = {'.gitignore', 'gradlew'}



def resolve_file(path):
	if not path:
		return None
	if path.startswith('/'):
		path = path[1:]
	full = os.path.join(BASE_DIR, path)
	if os.path.isfile(full):
		return full
	full_md = full + '.md'
	if os.path.isfile(full_md):
		return full_md
	return None



def list_files(path, skip_folders=[], skip_extensions=[], skip_files=[]):
	start_dir = os.path.join(BASE_DIR, path) if path else BASE_DIR
	if not os.path.isdir(start_dir):
		return []
	all_skip_folders = SKIP_FOLDERS | set(skip_folders)
	all_skip_extensions = set(skip_extensions)
	all_skip_files = SKIP_FILENAMES | set(skip_files)
	result = []
	for dirpath, dirnames, filenames in os.walk(start_dir):
		dirnames[:] = [d for d in dirnames if d not in all_skip_folders]
		for fname in filenames:
			if fname in all_skip_files:
				continue
			ext = os.path.splitext(fname)[1].lower()
			if ext[1:] in all_skip_extensions:
				continue
			if ext not in TEXT_EXTENSIONS:
				continue
			full = os.path.join(dirpath, fname)
			rel = os.path.relpath(full, BASE_DIR).replace(os.sep, '/')
			result.append(rel)
	return sorted(result)








@app.route('/files/<path:file_path>/edit')
def files_edit(file_path):
	abs_path = resolve_file(file_path)
	if not abs_path:
		abort(404)
	ext = os.path.splitext(abs_path)[1].lower()
	if ext not in TEXT_EXTENSIONS:
		abort(404)
	try:
		with open(abs_path, 'r', encoding='utf-8') as f:
			raw = f.read()
	except Exception:
		abort(500)
	lang = 'en'
	dir_ = 'ltr'
	if ext == '.md':
		hebrew_chars = sum(1 for c in raw if '\u0590' <= c <= '\u05FF')
		if hebrew_chars > len(raw.split()) * 0.3:
			dir_ = 'rtl'
			lang = 'he'
	return render_template('edit.html', content=raw, dir=dir_, lang=lang)

@app.route('/files/<path:file_path>/save', methods=['POST'])
def files_save(file_path):
	abs_path = resolve_file(file_path)
	if not abs_path:
		abort(404)
	ext = os.path.splitext(abs_path)[1].lower()
	if ext not in TEXT_EXTENSIONS:
		abort(404)
	new_content = request.form.get('content', '').replace('\r\n', '\n')
	try:
		with open(abs_path, 'w', encoding='utf-8') as f:
			f.write(new_content)
	except Exception:
		abort(500)
	display_path = file_path
	if display_path.endswith('.md'):
		display_path = display_path[:-3]
	return redirect(f'/files/{display_path}')





@app.route('/files/', defaults={'path': ''})
@app.route('/files/<path:path>')
def files_view(path):
	if path and not path.endswith('/'):
		return redirect(f'/files/{path}/')
	dir_path = os.path.join(BASE_DIR, path) if path else BASE_DIR
	if not os.path.isdir(dir_path):
		abort(404)
	try:
		entries = os.listdir(dir_path)
	except Exception:
		abort(404)
	folders = []
	files = []
	for name in sorted(entries, key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower())):
		if name.startswith('.'):
			continue
		full = os.path.join(dir_path, name)
		if os.path.isdir(full):
			folders.append(name)
		else:
			files.append(name)
	skip_folders_raw = request.args.get('skip_folders', '')
	skip_extensions_raw = request.args.get('skip_extensions', '')
	skip_files_raw = request.args.get('skip_files', '')
	skip_folders = skip_folders_raw.split(',') if skip_folders_raw else []
	skip_extensions = skip_extensions_raw.split(',') if skip_extensions_raw else []
	skip_files_list = skip_files_raw.split(',') if skip_files_raw else []
	if path == '':
		prompt_files = []
		all_extensions = []
	else:
		prompt_files = list_files(path, skip_folders=skip_folders, skip_extensions=skip_extensions, skip_files=skip_files_list)
		unfiltered = list_files(path)
		all_extensions = set()
		for f in unfiltered:
			ext = f.rsplit('.', 1)[-1].lower()
			all_extensions.add(ext)
		all_extensions = sorted(all_extensions)
	return render_template('files.html',
			folders=folders,
			files=files,
			prompt_files=prompt_files,
			all_extensions=all_extensions,
			skip_folders=skip_folders_raw,
			skip_extensions=skip_extensions_raw,
			skip_files=skip_files_raw)




@app.route('/docs/', defaults={'path': ''})
@app.route('/docs/<path:path>')
def docs_view(path):
	if path.endswith('/') or path == '':
		dir_path = os.path.join(BASE_DIR, path) if path else BASE_DIR
		if not os.path.isdir(dir_path):
			abort(404)
		try:
			entries = os.listdir(dir_path)
		except Exception:
			abort(404)
		folders = []
		files = []
		for name in sorted(entries, key=lambda x: (not os.path.isdir(os.path.join(dir_path, x)), x.lower())):
			if name.startswith('.'):
				continue
			full = os.path.join(dir_path, name)
			if os.path.isdir(full):
				folders.append(name)
			else:
				files.append(name)
		return render_template('docs.html',
							   folders=folders,
							   files=files)
	else:
		abs_path = resolve_file(path)
		if not abs_path:
			abort(404)
		ext = os.path.splitext(abs_path)[1].lower()
		if ext == '.md':
			with open(abs_path, 'r', encoding='utf-8') as f:
				md_text = f.read()
			html = markdown.markdown(md_text, extensions=['extra', 'tables', 'fenced_code', 'toc'])
			hebrew_chars = sum(1 for c in md_text if '\u0590' <= c <= '\u05FF')
			dir_ = 'rtl' if hebrew_chars > len(md_text.split()) * 0.3 else 'ltr'
			lang = 'he' if dir_ == 'rtl' else 'en'
			return render_template('page.html', content=html, dir=dir_, lang=lang, safe=True)
		if ext in TEXT_EXTENSIONS:
			with open(abs_path, 'r', encoding='utf-8') as f:
				raw = f.read()
			return render_template('page.html', content=raw, dir='ltr', lang='en', safe=False)
		return send_from_directory(os.path.dirname(abs_path), os.path.basename(abs_path))










@app.route('/files/generate-prompt', methods=['POST'])
def files_generate_prompt():
	try:
		data = request.get_json()
		selected_files = data.get('files', [])
		if not selected_files:
			return jsonify({'success': False, 'error': 'No files selected'})
		prompt_parts = []
		for relpath in selected_files:
			abs_path = os.path.join(BASE_DIR, relpath)
			parts = relpath.split('/')
			if os.path.isdir(os.path.join(BASE_DIR, parts[0])):
				if len(parts) > 1:
					stripped = '/'.join(parts[1:])
				else:
					stripped = ''
			else:
				stripped = relpath
			if not os.path.isfile(abs_path):
				continue
			try:
				with open(abs_path, 'r', encoding='utf-8') as f:
					content = f.read()
				prompt_parts.append(f"[FILE: {stripped}]")
				prompt_parts.append("[FILE_CONTENT_START]")
				prompt_parts.append(content)
				prompt_parts.append(f"[FILE_CONTENT_END: {stripped}]")
				prompt_parts.append("")
			except Exception:
				continue
		full_prompt = '\n'.join(prompt_parts)
		return jsonify({
			'success': True,
			'prompt': full_prompt,
			'file_count': len(selected_files),
			'character_count': len(full_prompt)
		})
	except Exception as e:
		return jsonify({'success': False, 'error': str(e)})

@app.route('/files/generate-prompt-cleaned', methods=['POST'])
def files_generate_prompt_cleaned():
	return files_generate_prompt()

@app.route('/<path:filename>')
def serve_file(filename):
	return send_from_directory('.', filename)

if __name__ == "__main__":
	app.run(debug=True)
