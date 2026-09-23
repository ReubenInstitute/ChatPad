import datetime
from datetime import datetime, timezone, timedelta
import os
import re
import uuid
import uuid7
import json
import tarfile
import shutil
import signal
import subprocess
import sys
import tempfile
import ast
import math
import operator
import socket
import ipaddress
from urllib.parse import urlparse, urljoin
import requests
import io

from openrouter import OpenRouter

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_FOLDER = os.path.join(APP_DIR, "sessions")
ARCHIVE_FOLDER = os.path.join(APP_DIR, "archive")
SESSION_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$')
MESSAGE_PATTERN = re.compile(r'^([0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12})\.json$')

class Chat:
	@property
	def sessions(self):
		if not os.path.exists(SESSIONS_FOLDER):
			return []
		sessions = []
		folders = [f for f in os.listdir(SESSIONS_FOLDER) if SESSION_PATTERN.match(f) and os.path.isdir(os.path.join(SESSIONS_FOLDER, f))]
		folders.sort()
		for folder in folders:
			session = Session(uuid=folder)
			sessions.append(session)
		return sessions

class Session:
	def __init__(self, uuid=None):
		self.uuid = uuid

	@property
	def timestamp(self):
		u = uuid.UUID(self.uuid)
		dt = uuid7.time(u)
		ms = dt.microsecond // 1000
		return dt.strftime("%Y%m%d%H%M%S") + f"{ms:03d}"

	def __repr__(self):
		return self.timestamp

	@property
	def folder(self):
		return os.path.join(SESSIONS_FOLDER, f"{self.uuid}")

	def save(self):
			os.makedirs(self.folder)

	@property
	def messages(self):
		filenames = [f for f in os.listdir(self.folder) if MESSAGE_PATTERN.match(f)]
		filenames.sort()
		messages = []
		for filename in filenames:
			match = MESSAGE_PATTERN.match(filename)
			uuid_str = match.group(1)
			msg = Message(uuid=uuid_str)
			msg.session = self
			msg.load()
			messages.append(msg)
		return messages

class Message:
	def __init__(self, uuid=None):
		self.uuid = uuid
		self.session = None
		self.prompt = None
		self.model = None
		self.think = False
		self.response = None
		self.reasoning = None
		self.error = None
		self.raw = None

	@property
	def timestamp(self):
		u = uuid.UUID(self.uuid)
		dt = uuid7.time(u)
		ms = dt.microsecond // 1000
		return dt.strftime("%Y%m%d%H%M%S") + f"{ms:03d}"


	def load(self):
		if self.uuid is None and self.session is None:
			return
		with open(self.path, "r") as f:
			data = json.load(f)
		self.uuid = data.get("uuid")
		self.session = Session(data.get("session"))
		self.prompt = data.get("prompt")
		self.model = data.get("model")
		self.response = data.get("response")
		self.reasoning = data.get("reasoning")
		self.error = data.get("error")
		self.raw = data.get("raw")

	@property
	def path(self):
		return os.path.join(self.session.folder, f"{self.uuid}.json")

	def save(self):
		if self.uuid is None:
			self.uuid = str(uuid.uuid4())
			self.timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
			self.session = Session()
			self.session.save()
		data = {
			"uuid": self.uuid,
			"session": self.session.uuid,
			"prompt": self.prompt,
			"model": self.model,
			"response": self.response,
			"reasoning": self.reasoning,
			"error": self.error,
			"raw": self.raw,
		}
		with open(self.path, "w") as f:
			json.dump(data, f, indent=2)

	@staticmethod
	def create(prompt, model=None, think=False):
		message = Message()
		message.model = model
		message.think = think
		message.prompt = prompt
		return message

	def send(self):
		result = OpenRouter.message(self.prompt, self.model, self.think, history=self.history)
		if "error" in result:
			self.error = result["error"]
		else:
			self.response = result["choices"][0]["message"]["content"]
			self.reasoning = result["choices"][0]["message"].get("reasoning", "")
		if "model" in result:
				self.model = result["model"]
		self.raw = result

	@property
	def history(self):
		if self.session is None or self.uuid is None:
			return []
		history = []
		for msg in self.session.messages:
			if msg.uuid == self.uuid:
				break
			history.append([msg.prompt or "", msg.response or ""])
		return history












def uuid7_timestamp(uuid_str):
	u = uuid.UUID(uuid_str)
	dt = uuid7.time(u)
	ms = dt.microsecond // 1000
	return dt.strftime("%Y%m%d%H%M%S") + f"{ms:03d}"


def _session_path(session_id, archived):
	folder = ARCHIVE_FOLDER if archived else SESSIONS_FOLDER
	return os.path.join(folder, f"{session_id}.tar.bz2")


def archive_session(session_id):
	os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
	src = _session_path(session_id, False)
	if os.path.isfile(src):
		os.replace(src, _session_path(session_id, True))


def unarchive_session(session_id):
	src = _session_path(session_id, True)
	if os.path.isfile(src):
		os.replace(src, _session_path(session_id, False))


def is_archived(session_id):
	return os.path.isfile(_session_path(session_id, True))


def read_session_messages(session_id):
	path = _session_path(session_id, False)
	if not os.path.isfile(path):
		path = _session_path(session_id, True)
	if not os.path.isfile(path):
		return []
	messages = []
	with tarfile.open(path, "r:bz2") as tar:
		names = [n for n in tar.getnames() if MESSAGE_PATTERN.match(n)]
		names.sort()
		for name in names:
			data = json.load(tar.extractfile(name))
			messages.append((name, data))
	return messages


def write_session_messages(session_id, messages):
	os.makedirs(SESSIONS_FOLDER, exist_ok=True)
	archive_path = _session_path(session_id, False)
	tmp_path = archive_path + ".tmp"
	messages = sorted(messages, key=lambda m: m[0])
	with tarfile.open(tmp_path, "w:bz2") as tar:
		for name, data in messages:
			raw = json.dumps(data, indent=2).encode("utf-8")
			info = tarfile.TarInfo(name=name)
			info.size = len(raw)
			tar.addfile(info, io.BytesIO(raw))
	os.replace(tmp_path, archive_path)


def list_sessions(archived=False):
	folder = ARCHIVE_FOLDER if archived else SESSIONS_FOLDER
	sessions = []
	if not os.path.isdir(folder):
		return sessions
	for name in os.listdir(folder):
		if not name.endswith(".tar.bz2"):
			continue
		session_id = name[:-len(".tar.bz2")]
		if not SESSION_PATTERN.match(session_id):
			continue
		timestamp_str = uuid7_timestamp(session_id)
		messages = read_session_messages(session_id)
		title = "(empty)"
		prompt = next((r["content"] for _, d in messages for r in normalize(d) if r["type"] == "prompt"), "")
		if prompt:
			title = prompt[:30]
			if len(prompt) > 30:
				title += "..."
		sessions.append((session_id, timestamp_str, title))
	sessions.sort(key=lambda x: x[1], reverse=True)
	return sessions


def group_sessions_by_day(sessions):
	groups = []
	for session in sessions:
		day = session[1][:8]
		if groups and groups[-1][0] == day:
			groups[-1][1].append(session)
		else:
			groups.append((day, [session]))
	return groups

MAX_STEPS = 20

# started in the app folder: the workspace is its system/ folder; started anywhere else: that folder is the workspace
SYSTEM_DIR = os.path.join(APP_DIR, "system") if os.path.realpath(os.getcwd()) == os.path.realpath(APP_DIR) else os.getcwd()
MAX_READ = 100000
MAX_SAVE = 10 * 1024 * 1024
COMMAND_TIMEOUT = 30

def _tool(name, description, properties, required=None):
	return {
		"type": "function",
		"function": {
			"name": name,
			"description": description,
			"parameters": {"type": "object", "properties": properties, "required": list(properties) if required is None else required},
		},
	}

TOOLS = [
	_tool("read_file", "Read a file, or list a folder (read_file(\".\") lists the top level). Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
	_tool("write_file", "Create a file, or replace it if it exists. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "content": {"type": "string"}}),
	_tool("edit_file", "Replace one piece of text in a file. `old` must appear exactly once; include enough surrounding text to make it unique. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}),
	_tool("append_file", "Add text to the end of a file, creating it if needed. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "content": {"type": "string"}}),
	_tool("rename_file", "Rename a file. Fails if the new name already exists. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "new_path": {"type": "string"}}),
	_tool("copy_file", "Copy a file. Fails if the new name already exists. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "new_path": {"type": "string"}}),
	_tool("fetch_url", "Download from an http or https URL. With path, the file is saved there exactly as downloaded and only a short confirmation is returned (use this to download files). Without path, the content is returned as text.", {"url": {"type": "string"}, "path": {"type": "string"}}, required=["url"]),
	_tool("delete_file", "Delete a file. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
	_tool("current_time", "Get the current date and time on the server.", {}),
	_tool("calculator", "Evaluate an arithmetic expression exactly. Supports + - * / // % **, parentheses, pi, e, and sqrt sin cos tan log log10 exp floor ceil abs round min max.", {"expression": {"type": "string"}}),
	_tool("todo", "Keep a todo list (stored in todo.md in the workspace). Actions: add (item is the text), done (item is the number), remove (item is the number), list. Returns the updated list.", {"action": {"type": "string", "enum": ["add", "done", "remove", "list"]}, "item": {"type": "string"}}, required=["action"]),
	_tool("run_python", "Run Python 3 code in the workspace folder and return what it prints, including errors. Each call is a fresh process, so print anything you want to see.", {"code": {"type": "string"}}),
	_tool("run_command", "Run a shell command in the workspace folder and return its output, including errors. Each call is a fresh shell, so cd does not carry over; pipes and && work.", {"command": {"type": "string"}}),
	_tool("make_folder", "Create a folder, including any missing parent folders. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
	_tool("remove_folder", "Remove an empty folder. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
]


class ToolError(Exception):
	pass


def _resolve(name):
	# a relative path inside system/; no "..", no absolute paths, no symlinks
	if name.strip("/") in ("", "."):
		return SYSTEM_DIR
	if "\\" in name or name.startswith("/"):
		raise ToolError(f"invalid path: {name}")
	full = SYSTEM_DIR
	for part in name.rstrip("/").split("/"):
		if part in ("", ".", ".."):
			raise ToolError(f"invalid path: {name}")
		full = os.path.join(full, part)
		if os.path.islink(full):
			raise ToolError(f"invalid path: {name}")
	return full


def read_file(path):
	full = _resolve(path)
	if not os.path.exists(full):
		if full == SYSTEM_DIR:
			return "(empty)"
		raise ToolError(f"not found: {path}")
	if os.path.isdir(full):
		lines = []
		for n in sorted(os.listdir(full)):
			p = os.path.join(full, n)
			lines.append(f"{n}/" if os.path.isdir(p) else f"{n}  {os.path.getsize(p)} bytes")
		return "\n".join(lines) or "(empty)"
	try:
		with open(full, "r", encoding="utf-8") as f:
			text = f.read(MAX_READ + 1)
	except UnicodeDecodeError:
		return f"binary file, {os.path.getsize(full)} bytes"
	if len(text) > MAX_READ:
		text = text[:MAX_READ] + f"\n[truncated at {MAX_READ} characters]"
	return text


def write_file(path, content):
	full = _resolve(path)
	if full == SYSTEM_DIR or os.path.isdir(full):
		raise ToolError(f"invalid name: {path}")
	os.makedirs(SYSTEM_DIR, exist_ok=True)
	if not os.path.isdir(os.path.dirname(full)):
		raise ToolError(f"folder does not exist: {os.path.dirname(path)} (create it with make_folder)")
	with open(full, "w", encoding="utf-8") as f:
		f.write(content)
	return f"wrote {len(content)} characters to {path}"


def _existing_file(path):
	full = _resolve(path)
	if full == SYSTEM_DIR or os.path.isdir(full):
		raise ToolError(f"invalid name: {path}")
	if not os.path.exists(full):
		raise ToolError(f"not found: {path}")
	return full


def edit_file(path, old, new):
	full = _existing_file(path)
	if not old:
		raise ToolError("old must not be empty")
	with open(full, "r", encoding="utf-8") as f:
		text = f.read()
	count = text.count(old)
	if count == 0:
		raise ToolError(f"text not found in {path}")
	if count > 1:
		raise ToolError(f"text found {count} times in {path}; add more surrounding text to make it unique")
	with open(full, "w", encoding="utf-8") as f:
		f.write(text.replace(old, new))
	return f"edited {path}"


def append_file(path, content):
	full = _resolve(path)
	if full == SYSTEM_DIR or os.path.isdir(full):
		raise ToolError(f"invalid name: {path}")
	os.makedirs(SYSTEM_DIR, exist_ok=True)
	if not os.path.isdir(os.path.dirname(full)):
		raise ToolError(f"folder does not exist: {os.path.dirname(path)} (create it with make_folder)")
	with open(full, "a", encoding="utf-8") as f:
		f.write(content)
	return f"appended {len(content)} characters to {path}"


def _move_or_copy(path, new_path, action):
	source = _existing_file(path)
	target = _resolve(new_path)
	if target == SYSTEM_DIR or os.path.isdir(target):
		raise ToolError(f"invalid name: {new_path}")
	if os.path.lexists(target):
		raise ToolError(f"already exists: {new_path}")
	if not os.path.isdir(os.path.dirname(target)):
		raise ToolError(f"folder does not exist: {os.path.dirname(new_path)} (create it with make_folder)")
	if action == "rename":
		os.rename(source, target)
	else:
		shutil.copyfile(source, target)
	return f"{'renamed' if action == 'rename' else 'copied'} {path} to {new_path}"


def rename_file(path, new_path):
	return _move_or_copy(path, new_path, "rename")


def copy_file(path, new_path):
	return _move_or_copy(path, new_path, "copy")


def _check_url(url):
	parts = urlparse(url)
	if parts.scheme not in ("http", "https") or not parts.hostname:
		raise ValueError(f"invalid url: {url} (http or https only)")
	for info in socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80)):
		ip = ipaddress.ip_address(info[4][0])
		if not ip.is_global:
			raise ValueError(f"blocked: {parts.hostname} is not a public address")


def _get(url):
	for _ in range(6):
		_check_url(url)
		response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 ChatPad"}, timeout=20, stream=True, allow_redirects=False)
		if response.is_redirect:
			url = urljoin(url, response.headers["Location"])
			continue
		return response
	raise ToolError("too many redirects")


def fetch_url(url, path=None):
	target = None
	if path:
		target = _resolve(path)
		if target == SYSTEM_DIR or os.path.isdir(target):
			raise ToolError(f"invalid name: {path}")
		os.makedirs(SYSTEM_DIR, exist_ok=True)
		if not os.path.isdir(os.path.dirname(target)):
			raise ToolError(f"folder does not exist: {os.path.dirname(path)} (create it with make_folder)")
	response = _get(url)
	if response.status_code != 200:
		raise ToolError(f"HTTP {response.status_code}")
	limit = MAX_SAVE if target else MAX_READ * 4
	data = b""
	for chunk in response.iter_content(65536):
		data += chunk
		if len(data) > limit:
			break
	truncated = len(data) > limit
	if target:
		if truncated:
			raise ToolError(f"too large: over {MAX_SAVE} bytes, not saved")
		with open(target, "wb") as f:
			f.write(data)
		return f"saved {len(data)} bytes to {path}"
	try:
		text = data.decode("utf-8")
	except UnicodeDecodeError:
		if not truncated:
			return f"binary file, {len(data)} bytes"
		text = data.decode("utf-8", errors="ignore")
	if len(text) > MAX_READ:
		text = text[:MAX_READ] + f"\n[truncated at {MAX_READ} characters]"
	return text


def delete_file(path):
	full = _resolve(path)
	if full == SYSTEM_DIR:
		raise ToolError(f"invalid name: {path}")
	if os.path.isdir(full):
		raise ToolError(f"{path} is a folder, use remove_folder")
	if not os.path.exists(full):
		raise ToolError(f"not found: {path}")
	os.remove(full)
	return f"deleted {path}"


def make_folder(path):
	full = _resolve(path)
	if full == SYSTEM_DIR:
		raise ToolError(f"invalid name: {path}")
	if os.path.isdir(full):
		raise ToolError(f"already exists: {path}")
	if os.path.exists(full):
		raise ToolError(f"a file with that name exists: {path}")
	os.makedirs(full)
	return f"created folder {path}"


def remove_folder(path):
	full = _resolve(path)
	if full == SYSTEM_DIR:
		raise ToolError(f"invalid name: {path}")
	if not os.path.exists(full):
		raise ToolError(f"not found: {path}")
	if not os.path.isdir(full):
		raise ToolError(f"{path} is a file, use delete_file")
	if os.listdir(full):
		raise ToolError(f"folder is not empty: {path}")
	os.rmdir(full)
	return f"removed folder {path}"


def current_time():
	return datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M:%S %Z (UTC%z)")


CALC_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
CALC_NAMES = {"pi": math.pi, "e": math.e}
CALC_FUNCS = {n: getattr(math, n) for n in ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "floor", "ceil")}
CALC_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})


def _calc(node):
	if isinstance(node, ast.Expression):
		return _calc(node.body)
	if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
		return node.value
	if isinstance(node, ast.Name) and node.id in CALC_NAMES:
		return CALC_NAMES[node.id]
	if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
		value = _calc(node.operand)
		return value if isinstance(node.op, ast.UAdd) else -value
	if isinstance(node, ast.BinOp) and type(node.op) in CALC_OPS:
		left, right = _calc(node.left), _calc(node.right)
		if isinstance(node.op, ast.Pow) and isinstance(left, int) and isinstance(right, int) and right > 0 and left.bit_length() * right > 100000:
			raise ToolError("result too large")
		return CALC_OPS[type(node.op)](left, right)
	if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CALC_FUNCS and not node.keywords:
		return CALC_FUNCS[node.func.id](*[_calc(a) for a in node.args])
	raise ToolError("unsupported expression")


def calculator(expression):
	if len(expression) > 500:
		raise ToolError("expression too long")
	return str(_calc(ast.parse(expression.strip(), mode="eval")))


TODO_FILE = "todo.md"


def _todo_load():
	full = os.path.join(SYSTEM_DIR, TODO_FILE)
	if not os.path.exists(full):
		return []
	items = []
	with open(full, "r", encoding="utf-8") as f:
		for line in f.read().splitlines():
			if line.startswith("- [x] "):
				items.append([True, line[6:]])
			elif line.startswith("- [ ] "):
				items.append([False, line[6:]])
	return items


def _todo_show(items):
	lines = [f"{i}. [{'x' if done else ' '}] {text}" for i, (done, text) in enumerate(items, 1)]
	return "\n".join(lines) or "(empty)"


def todo(action, item=None):
	items = _todo_load()
	if action == "list":
		return _todo_show(items)
	if action == "add":
		if not item:
			raise ToolError("item text required")
		items.append([False, str(item).replace("\n", " ")])
	elif action in ("done", "remove"):
		try:
			number = int(item)
		except (TypeError, ValueError):
			raise ToolError("item must be the number from the list")
		if not 1 <= number <= len(items):
			raise ToolError(f"no item {number}")
		if action == "done":
			items[number - 1][0] = True
		else:
			del items[number - 1]
	else:
		raise ToolError(f"unknown action: {action} (add, done, remove, list)")
	os.makedirs(SYSTEM_DIR, exist_ok=True)
	with open(os.path.join(SYSTEM_DIR, TODO_FILE), "w", encoding="utf-8") as f:
		f.write("".join(f"- [{'x' if done else ' '}] {text}\n" for done, text in items))
	return _todo_show(items)


def _execute(command, shell=False):
	os.makedirs(SYSTEM_DIR, exist_ok=True)
	process = subprocess.Popen(command, shell=shell, cwd=SYSTEM_DIR, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
	try:
		stdout, stderr = process.communicate(timeout=COMMAND_TIMEOUT)
	except subprocess.TimeoutExpired:
		os.killpg(process.pid, signal.SIGKILL)
		process.communicate()
		raise ToolError(f"timed out after {COMMAND_TIMEOUT} seconds")
	output = stdout
	if stderr:
		output += ("\n" if output else "") + "[stderr]\n" + stderr
	if process.returncode != 0:
		output += f"\n[exit code {process.returncode}]"
	if len(output) > MAX_READ:
		output = output[:MAX_READ] + f"\n[truncated at {MAX_READ} characters]"
	return output or "(no output)"


def run_python(code):
	with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
		f.write(code)
	try:
		return _execute([sys.executable, f.name])
	finally:
		os.remove(f.name)


def run_command(command):
	return _execute(command, shell=True)


def run_tool(name, arguments, tools):
	try:
		if name not in tools:
			raise ToolError(f"tool not enabled: {name}")
		args = json.loads(arguments) if isinstance(arguments, str) else arguments
		if name == "read_file":
			content = read_file(args["path"])
		elif name == "write_file":
			content = write_file(args["path"], args["content"])
		elif name == "edit_file":
			content = edit_file(args["path"], args["old"], args["new"])
		elif name == "append_file":
			content = append_file(args["path"], args["content"])
		elif name == "rename_file":
			content = rename_file(args["path"], args["new_path"])
		elif name == "copy_file":
			content = copy_file(args["path"], args["new_path"])
		elif name == "fetch_url":
			content = fetch_url(args["url"], args.get("path"))
		elif name == "delete_file":
			content = delete_file(args["path"])
		elif name == "current_time":
			content = current_time()
		elif name == "calculator":
			content = calculator(args["expression"])
		elif name == "todo":
			content = todo(args["action"], args.get("item"))
		elif name == "run_python":
			content = run_python(args["code"])
		elif name == "run_command":
			content = run_command(args["command"])
		elif name == "make_folder":
			content = make_folder(args["path"])
		elif name == "remove_folder":
			content = remove_folder(args["path"])
		else:
			raise ToolError(f"unknown tool: {name}")
		return content, None
	except ToolError as e:
		return str(e), str(e)
	except Exception as e:
		message = f"error: {type(e).__name__}: {e}"
		return message, message


def find_tool_result(turn, tool_call_id):
	for m in turn:
		if m.get("type") == "tool_result" and m.get("tool_call_id") == tool_call_id:
			return m
	return None


def tool_summary(name, arguments):
	try:
		args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
	except Exception:
		args = {}
	if name == "read_file":
		return f"read {args.get('path', '?')}"
	if name == "write_file":
		return f"save {args.get('path', '?')}"
	if name == "edit_file":
		return f"edit {args.get('path', '?')}"
	if name == "append_file":
		return f"append to {args.get('path', '?')}"
	if name == "rename_file":
		return f"rename {args.get('path', '?')} to {args.get('new_path', '?')}"
	if name == "copy_file":
		return f"copy {args.get('path', '?')} to {args.get('new_path', '?')}"
	if name == "fetch_url":
		if args.get("path"):
			return f"download {args.get('url', '?')} to {args['path']}"
		return f"fetch {args.get('url', '?')}"
	if name == "delete_file":
		return f"delete {args.get('path', '?')}"
	if name == "current_time":
		return "check time"
	if name == "calculator":
		return "calculate"
	if name == "todo":
		action = args.get("action")
		if action == "add":
			return "add todo"
		if action == "done":
			return "complete todo"
		if action == "remove":
			return "remove todo"
		if action == "list":
			return "list todos"
		return "todo"
	if name == "run_python":
		return "run python"
	if name == "run_command":
		command = (args.get("command") or "").strip()
		program = os.path.basename(command.split()[0]) if command.split() else ""
		return f"run {program}" if program else "run a command"
	if name == "make_folder":
		return f"mkdir {args.get('path', '?')}"
	if name == "remove_folder":
		return f"rmdir {args.get('path', '?')}"
	return name


def normalize(data):
	# old records hold a whole exchange; split them into typed messages
	if "type" in data:
		return [data]
	records = []
	if data.get("prompt") is not None:
		records.append({"type": "prompt", "content": data["prompt"]})
	if data.get("reasoning"):
		records.append({"type": "reasoning", "content": data["reasoning"]})
	if data.get("error"):
		records.append({"type": "error", "error": data["error"], "model": data.get("model")})
	if data.get("response"):
		cost = (data.get("usage") or {}).get("cost")
		records.append({"type": "response", "content": data["response"], "model": data.get("model"), "cost": cost})
	return records


def build_messages(existing):
	records = [r for _, d in existing for r in normalize(d)]
	messages = []
	for turn in group_turns(records):
		types = {r["type"] for r in turn}
		if "error" in types and not types & {"response", "tool_call"}:
			continue  # the prompt got no answer, don't send it
		for r in turn:
			t = r["type"]
			if t == "prompt":
				messages.append({"role": "user", "content": r["content"]})
			elif t == "tool_call":
				messages.append({"role": "assistant", "content": r.get("content"), "tool_calls": r["tool_calls"]})
			elif t == "tool_result":
				messages.append({"role": "tool", "tool_call_id": r["tool_call_id"], "content": r["content"]})
			elif t == "response" and r.get("content"):
				messages.append({"role": "assistant", "content": r["content"]})
	return messages


def get_session(session_id):
	messages = []
	for name, data in read_session_messages(session_id):
		timestamp_str = uuid7_timestamp(name[:-5])
		for record in normalize(data):
			record = dict(record)
			record["timestamp"] = timestamp_str
			messages.append(record)
	return messages


def group_turns(messages):
	turns = []
	for m in messages:
		if m["type"] == "prompt" or not turns:
			turns.append([])
		turns[-1].append(m)
	return turns


def next_name(last_name):
	# names sort by time, so each message must be at least 1 ms after the previous one
	dt = datetime.now(timezone.utc)
	if last_name:
		last = uuid7.time(uuid.UUID(last_name[:-5]))
		if dt < last + timedelta(milliseconds=1):
			dt = last + timedelta(milliseconds=1)
	return f"{uuid7.create(dt)}.json"


def session_message(prompt, model, reasoning=True, session=None, tools=None):
	if session is None:
		session = str(uuid7.create(datetime.now(timezone.utc)))

	active_tools = [t for t in TOOLS if t["function"]["name"] in tools] if tools is not None else []

	existing = read_session_messages(session)

	def add(record):
		name = next_name(existing[-1][0] if existing else None)
		record["session"] = session
		record["uuid"] = name[:-5]
		existing.append((name, record))
		write_session_messages(session, existing)
		return record

	yield add({"type": "prompt", "content": prompt, "model": model})
	for step in range(MAX_STEPS):
		result = OpenRouter.message(build_messages(existing), model, reasoning, active_tools)
		if "error" in result:
			yield add({"type": "error", "error": result["error"], "model": model})
			return
		message = result["choices"][0]["message"]
		if message.get("reasoning"):
			yield add({"type": "reasoning", "content": message["reasoning"]})
		calls = message.get("tool_calls")
		if calls:
			for call in calls:
				try:
					json.loads(call["function"]["arguments"])
				except Exception:
					call["function"]["arguments"] = "{}"
			yield add({"type": "tool_call", "content": message.get("content"), "tool_calls": calls})
			for call in calls:
				output, error = run_tool(call["function"]["name"], call["function"]["arguments"], tools or [])
				record = {"type": "tool_result", "tool_call_id": call["id"], "name": call["function"]["name"], "content": output}
				if error:
					record["error"] = {"message": error}
				yield add(record)
			continue
		if not message.get("content"):
			reason = result["choices"][0].get("finish_reason")
			yield add({"type": "error", "error": {"message": f"Empty reply from model (finish_reason: {reason})", "code": None}, "model": model})
			return
		cost = (result.get("usage") or {}).get("cost")
		yield add({"type": "response", "content": message.get("content"), "model": model, "cost": cost})
		return
	yield add({"type": "error", "error": {"message": f"Stopped after {MAX_STEPS} steps", "code": None}, "model": model})



if __name__ == "__main__":
	import json

	print("=== Test 1: No thinking ===")
	msg1 = Message("what can you do?")
	msg1.send()
	if msg1.error:
		print("Error:", msg1.error.get("message") or msg1.error)
	else:
		print("Model:", msg1.model)
		print("Response:", len(msg1.response) if msg1.response else 0)
		print("Reasoning:", len(msg1.reasoning) if msg1.reasoning else 0)
		print("Raw:", len(str(msg1.raw)) if msg1.raw else 0)
	with open("1.json", "w") as f:
		json.dump(msg1.raw, f, indent=2)
	print()

	print("=== Test 2: With thinking ===")
	msg2 = Message("what can you do?", think=True)
	msg2.send()
	if msg2.error:
		print("Error:", msg2.error.get("message") or msg2.error)
	else:
		print("Model:", msg2.model)
		print("Response:", len(msg2.response) if msg2.response else 0)
		print("Reasoning:", len(msg2.reasoning) if msg2.reasoning else 0)
		print("Raw:", len(str(msg2.raw)) if msg2.raw else 0)
	with open("2.json", "w") as f:
		json.dump(msg2.raw, f, indent=2)
