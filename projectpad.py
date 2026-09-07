from flask import Flask, render_template, abort, send_from_directory, request, redirect, jsonify
import markdown
import os

ROOT = os.path.dirname(os.path.abspath(__file__))
CWD = os.getcwd()

app = Flask(__name__, template_folder=ROOT)

# Editable text extensions (for viewing / editing)
TEXT_EXTENSIONS = {
	'.txt', '.md', '.markdown', '.html', '.htm', '.css', '.js', '.mjs',
	'.jsx', '.ts', '.tsx', '.py', '.java', '.c', '.cpp', '.h', '.hpp',
	'.json', '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
	'.log', '.sh', '.bash', '.zsh', '.bat', '.ps1', '.rb', '.go', '.rs',
	'.swift', '.kt', '.scala', '.pl', '.lua', '.r', '.m', '.mm', '.php',
	'.sql', '.vue', '.svelte', '.astro'
}

# Prompt builder skip lists
SKIP_FOLDERS = {
	'audio', 'assets', 'fonts', '__pycache__',
	'projects', 'TRASH', 'TEMP', '.git'
}
SKIP_EXTENSIONS = {
	'mp3', 'm4a', 'wav', 'mp4',
	'jpg', 'jpeg', 'png', 'gif', 'bmp', #'svg',
	'pdf', 'zip', 'tar', 'gz', 'rar',
	'exe', 'dll', 'so', 'bin', 'dat'
}
SKIP_FILENAMES = {
	'.gitignore', 'gradlew'#, 'Makefile'
}

# ---------- context processor for breadcrumbs ----------
@app.context_processor
def inject_paths():
	raw = request.path
	if raw.endswith('/edit'):
		raw = raw[:-5]
	elif raw.endswith('/save'):
		raw = raw[:-5]
	parts = [p for p in raw.split('/') if p]
	if parts and '.' in parts[-1]:
		parts.pop()
	return {'paths': parts}

# ---------- helpers ----------
def resolve_file(path):
	if not path:
		return None
	if path.startswith('/'):
		path = path[1:]
	full = os.path.join(CWD, path)
	if os.path.isfile(full):
		return full
	full_md = full + '.md'
	if os.path.isfile(full_md):
		return full_md
	return None

def list_files_for_prompt(root_rel):
	"""
	Recursively collect text‑file paths relative to CWD,
	ignoring SKIP_FOLDERS, SKIP_EXTENSIONS, SKIP_FILENAMES.
	"""
	start_dir = os.path.join(CWD, root_rel) if root_rel else CWD
	if not os.path.isdir(start_dir):
		return []
	result = []
	for dirpath, dirnames, filenames in os.walk(start_dir):
		# Prune folders to skip
		dirnames[:] = [d for d in dirnames if d not in SKIP_FOLDERS]
		for fname in filenames:
			if fname in SKIP_FILENAMES:
				continue
			ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
			if ext in SKIP_EXTENSIONS:
				continue
			full = os.path.join(dirpath, fname)
			rel = os.path.relpath(full, CWD).replace(os.sep, '/')
			result.append(rel)
	return sorted(result)

# ---------- routes ----------
@app.route('/styles.css')
def styles_css():
	cwd_css = os.path.join(CWD, 'styles.css')
	if os.path.isfile(cwd_css):
		return send_from_directory(CWD, 'styles.css')
	return send_from_directory(ROOT, 'styles.css')

@app.route('/<path:file_path>/edit')
def edit_file(file_path):
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

@app.route('/<path:file_path>/save', methods=['POST'])
def save_file(file_path):
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
	return redirect(f'/{display_path}')

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def catch_all(path):
	if path.endswith('/') or path == '':
		dir_path = os.path.join(CWD, path) if path else CWD
		if not os.path.isdir(dir_path):
			abort(404)

		# Flat navigation listing
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

		# Recursive prompt‑builder file list
		prompt_files = list_files_for_prompt(path if path else '')

		return render_template('index.html',
							   folders=folders,
							   files=files,
							   prompt_files=prompt_files,
							   dir='ltr', lang='en')

	else:
		# File view
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

# ---------- Prompt builder endpoints ----------
@app.route('/generate-prompt', methods=['POST'])
def generate_prompt():
	try:
		data = request.get_json()
		selected_files = data.get('files', [])
		if not selected_files:
			return jsonify({'success': False, 'error': 'No files selected'})

		prompt_parts = []
		for relpath in selected_files:
			abs_path = os.path.join(CWD, relpath)
			if not os.path.isfile(abs_path):
				continue
			try:
				with open(abs_path, 'r', encoding='utf-8') as f:
					content = f.read()
				prompt_parts.append(f"[FILE: {relpath}]")
				prompt_parts.append("[FILE_CONTENT_START]")
				prompt_parts.append(content)
				prompt_parts.append(f"[FILE_CONTENT_END: {relpath}]")
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

@app.route('/generate-prompt-cleaned', methods=['POST'])
def generate_prompt_cleaned():
	# Same as raw for now (placeholder for future cleaning logic)
	return generate_prompt()

if __name__ == '__main__':
	app.run(debug=True, host='0.0.0.0', port=5000)
