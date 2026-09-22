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
	_tool("read", "Read a file, or list a folder (read(\".\") lists the top level). Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
	_tool("write", "Create a file, or replace it if it exists. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "content": {"type": "string"}}),
	_tool("edit", "Replace one piece of text in a file. `old` must appear exactly once; include enough surrounding text to make it unique. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}),
	_tool("append", "Add text to the end of a file, creating it if needed. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "content": {"type": "string"}}),
	_tool("rename", "Rename a file. Fails if the new name already exists. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "new_path": {"type": "string"}}),
	_tool("copy", "Copy a file. Fails if the new name already exists. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}, "new_path": {"type": "string"}}),
	_tool("fetch", "Download from an http or https URL. With path, the file is saved there exactly as downloaded and only a short confirmation is returned (use this to download files). Without path, the content is returned as text.", {"url": {"type": "string"}, "path": {"type": "string"}}, required=["url"]),
	_tool("delete", "Delete a file. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
	_tool("current_time", "Get the current date and time on the server.", {}),
	_tool("calculator", "Evaluate an arithmetic expression exactly. Supports + - * / // % **, parentheses, pi, e, and sqrt sin cos tan log log10 exp floor ceil abs round min max.", {"expression": {"type": "string"}}),
	_tool("todo", "Keep a todo list (stored in todo.md in the workspace). Actions: add (item is the text), done (item is the number), remove (item is the number), list. Returns the updated list.", {"action": {"type": "string", "enum": ["add", "done", "remove", "list"]}, "item": {"type": "string"}}, required=["action"]),
	_tool("run_python", "Run Python 3 code in the workspace folder and return what it prints, including errors. Each call is a fresh process, so print anything you want to see.", {"code": {"type": "string"}}),
	_tool("run_command", "Run a shell command in the workspace folder and return its output, including errors. Each call is a fresh shell, so cd does not carry over; pipes and && work.", {"command": {"type": "string"}}),
	_tool("mkdir", "Create a folder, including any missing parent folders. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
	_tool("rmdir", "Remove an empty folder. Paths are relative to the workspace, e.g. notes.txt or docs/a.txt.", {"path": {"type": "string"}}),
]


def _resolve(name):
	# a relative path inside system/; no "..", no absolute paths, no symlinks
	if name.strip("/") in ("", "."):
		return SYSTEM_DIR
	if "\\" in name or name.startswith("/"):
		raise ValueError(f"invalid path: {name}")
	full = SYSTEM_DIR
	for part in name.rstrip("/").split("/"):
		if part in ("", ".", ".."):
			raise ValueError(f"invalid path: {name}")
		full = os.path.join(full, part)
		if os.path.islink(full):
			raise ValueError(f"invalid path: {name}")
	return full


def read(path):
	full = _resolve(path)
	if not os.path.exists(full):
		if full == SYSTEM_DIR:
			return "(empty)"
		return f"not found: {path}"
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


def write(path, content):
	full = _resolve(path)
	if full == SYSTEM_DIR or os.path.isdir(full):
		return f"invalid name: {path}"
	os.makedirs(SYSTEM_DIR, exist_ok=True)
	if not os.path.isdir(os.path.dirname(full)):
		return f"folder does not exist: {os.path.dirname(path)} (create it with mkdir)"
	with open(full, "w", encoding="utf-8") as f:
		f.write(content)
	return f"wrote {len(content)} characters to {path}"


def _existing_file(path):
	full = _resolve(path)
	if full == SYSTEM_DIR or os.path.isdir(full):
		raise ValueError(f"invalid name: {path}")
	if not os.path.exists(full):
		raise FileNotFoundError(f"not found: {path}")
	return full


def edit(path, old, new):
	full = _existing_file(path)
	if not old:
		return "old must not be empty"
	with open(full, "r", encoding="utf-8") as f:
		text = f.read()
	count = text.count(old)
	if count == 0:
		return f"text not found in {path}"
	if count > 1:
		return f"text found {count} times in {path}; add more surrounding text to make it unique"
	with open(full, "w", encoding="utf-8") as f:
		f.write(text.replace(old, new))
	return f"edited {path}"


def append(path, content):
	full = _resolve(path)
	if full == SYSTEM_DIR or os.path.isdir(full):
		return f"invalid name: {path}"
	os.makedirs(SYSTEM_DIR, exist_ok=True)
	if not os.path.isdir(os.path.dirname(full)):
		return f"folder does not exist: {os.path.dirname(path)} (create it with mkdir)"
	with open(full, "a", encoding="utf-8") as f:
		f.write(content)
	return f"appended {len(content)} characters to {path}"


def _move_or_copy(path, new_path, action):
	source = _existing_file(path)
	target = _resolve(new_path)
	if target == SYSTEM_DIR or os.path.isdir(target):
		return f"invalid name: {new_path}"
	if os.path.lexists(target):
		return f"already exists: {new_path}"
	if not os.path.isdir(os.path.dirname(target)):
		return f"folder does not exist: {os.path.dirname(new_path)} (create it with mkdir)"
	if action == "rename":
		os.rename(source, target)
	else:
		shutil.copyfile(source, target)
	return f"{'renamed' if action == 'rename' else 'copied'} {path} to {new_path}"


def rename(path, new_path):
	return _move_or_copy(path, new_path, "rename")


def copy(path, new_path):
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
	raise ValueError("too many redirects")


def fetch(url, path=None):
	target = None
	if path:
		target = _resolve(path)
		if target == SYSTEM_DIR or os.path.isdir(target):
			return f"invalid name: {path}"
		os.makedirs(SYSTEM_DIR, exist_ok=True)
		if not os.path.isdir(os.path.dirname(target)):
			return f"folder does not exist: {os.path.dirname(path)} (create it with mkdir)"
	response = _get(url)
	if response.status_code != 200:
		return f"HTTP {response.status_code}"
	limit = MAX_SAVE if target else MAX_READ * 4
	data = b""
	for chunk in response.iter_content(65536):
		data += chunk
		if len(data) > limit:
			break
	truncated = len(data) > limit
	if target:
		if truncated:
			return f"too large: over {MAX_SAVE} bytes, not saved"
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


def delete(path):
	full = _resolve(path)
	if full == SYSTEM_DIR:
		return f"invalid name: {path}"
	if os.path.isdir(full):
		return f"{path} is a folder, use rmdir"
	if not os.path.exists(full):
		return f"not found: {path}"
	os.remove(full)
	return f"deleted {path}"


def mkdir(path):
	full = _resolve(path)
	if full == SYSTEM_DIR:
		return f"invalid name: {path}"
	if os.path.isdir(full):
		return f"already exists: {path}"
	if os.path.exists(full):
		return f"a file with that name exists: {path}"
	os.makedirs(full)
	return f"created folder {path}"


def rmdir(path):
	full = _resolve(path)
	if full == SYSTEM_DIR:
		return f"invalid name: {path}"
	if not os.path.exists(full):
		return f"not found: {path}"
	if not os.path.isdir(full):
		return f"{path} is a file, use delete"
	if os.listdir(full):
		return f"folder is not empty: {path}"
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
			raise ValueError("result too large")
		return CALC_OPS[type(node.op)](left, right)
	if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CALC_FUNCS and not node.keywords:
		return CALC_FUNCS[node.func.id](*[_calc(a) for a in node.args])
	raise ValueError("unsupported expression")


def calculator(expression):
	if len(expression) > 500:
		return "expression too long"
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
			return "item text required"
		items.append([False, str(item).replace("\n", " ")])
	elif action in ("done", "remove"):
		try:
			number = int(item)
		except (TypeError, ValueError):
			return "item must be the number from the list"
		if not 1 <= number <= len(items):
			return f"no item {number}"
		if action == "done":
			items[number - 1][0] = True
		else:
			del items[number - 1]
	else:
		return f"unknown action: {action} (add, done, remove, list)"
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
		return f"timed out after {COMMAND_TIMEOUT} seconds"
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


def run_tool(name, arguments):
	try:
		args = json.loads(arguments) if isinstance(arguments, str) else arguments
		if name == "read":
			return read(args["path"])
		if name == "write":
			return write(args["path"], args["content"])
		if name == "edit":
			return edit(args["path"], args["old"], args["new"])
		if name == "append":
			return append(args["path"], args["content"])
		if name == "rename":
			return rename(args["path"], args["new_path"])
		if name == "copy":
			return copy(args["path"], args["new_path"])
		if name == "fetch":
			return fetch(args["url"], args.get("path"))
		if name == "delete":
			return delete(args["path"])
		if name == "current_time":
			return current_time()
		if name == "calculator":
			return calculator(args["expression"])
		if name == "todo":
			return todo(args["action"], args.get("item"))
		if name == "run_python":
			return run_python(args["code"])
		if name == "run_command":
			return run_command(args["command"])
		if name == "mkdir":
			return mkdir(args["path"])
		if name == "rmdir":
			return rmdir(args["path"])
		return f"unknown tool: {name}"
	except Exception as e:
		return f"error: {type(e).__name__}: {e}"


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


def session_message(prompt, model, reasoning=True, session=None):
	if session is None:
		session = str(uuid7.create(datetime.now(timezone.utc)))

	existing = read_session_messages(session)

	def add(record):
		name = next_name(existing[-1][0] if existing else None)
		record["session"] = session
		record["uuid"] = name[:-5]
		existing.append((name, record))
		write_session_messages(session, existing)

	add({"type": "prompt", "content": prompt, "model": model})
	for step in range(MAX_STEPS):
		result = OpenRouter.message(build_messages(existing), model, reasoning, TOOLS)
		if "error" in result:
			add({"type": "error", "error": result["error"], "model": model})
			return {"session": session}
		message = result["choices"][0]["message"]
		if message.get("reasoning"):
			add({"type": "reasoning", "content": message["reasoning"]})
		calls = message.get("tool_calls")
		if calls:
			add({"type": "tool_call", "content": message.get("content"), "tool_calls": calls})
			for call in calls:
				output = run_tool(call["function"]["name"], call["function"]["arguments"])
				add({"type": "tool_result", "tool_call_id": call["id"], "name": call["function"]["name"], "content": output})
			continue
		if not message.get("content"):
			reason = result["choices"][0].get("finish_reason")
			add({"type": "error", "error": {"message": f"Empty reply from model (finish_reason: {reason})", "code": None}, "model": model})
			return {"session": session}
		cost = (result.get("usage") or {}).get("cost")
		add({"type": "response", "content": message.get("content"), "model": model, "cost": cost})
		return {"session": session}
	add({"type": "error", "error": {"message": f"Stopped after {MAX_STEPS} steps", "code": None}, "model": model})
	return {"session": session}



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
