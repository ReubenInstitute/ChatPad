import datetime
from datetime import datetime, timezone, timedelta
import os
import re
import uuid
import uuid7
import json
import tarfile
import io

from openrouter import OpenRouter

SESSIONS_FOLDER = "sessions"
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


def session_archive_path(session_id):
	return os.path.join(SESSIONS_FOLDER, f"{session_id}.tar.bz2")


def read_session_messages(session_id):
	archive_path = session_archive_path(session_id)
	if not os.path.isfile(archive_path):
		return []
	messages = []
	with tarfile.open(archive_path, "r:bz2") as tar:
		names = [n for n in tar.getnames() if MESSAGE_PATTERN.match(n)]
		names.sort()
		for name in names:
			data = json.load(tar.extractfile(name))
			messages.append((name, data))
	return messages


def write_session_messages(session_id, messages):
	os.makedirs(SESSIONS_FOLDER, exist_ok=True)
	archive_path = session_archive_path(session_id)
	tmp_path = archive_path + ".tmp"
	messages = sorted(messages, key=lambda m: m[0])
	with tarfile.open(tmp_path, "w:bz2") as tar:
		for name, data in messages:
			raw = json.dumps(data, indent=2).encode("utf-8")
			info = tarfile.TarInfo(name=name)
			info.size = len(raw)
			tar.addfile(info, io.BytesIO(raw))
	os.replace(tmp_path, archive_path)


def list_sessions():
	sessions = []
	if not os.path.isdir(SESSIONS_FOLDER):
		return sessions
	for name in os.listdir(SESSIONS_FOLDER):
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

MAX_STEPS = 5

SYSTEM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "system")
MAX_READ = 100000

def _tool(name, description, properties):
	return {
		"type": "function",
		"function": {
			"name": name,
			"description": description,
			"parameters": {"type": "object", "properties": properties, "required": list(properties)},
		},
	}

TOOLS = [
	_tool("read", "Read a file, or list all files with read(\".\"). The workspace is one flat folder: file names only, no subfolders.", {"path": {"type": "string"}}),
	_tool("write", "Create a file, or replace it if it exists. The workspace is one flat folder: file names only, no subfolders.", {"path": {"type": "string"}, "content": {"type": "string"}}),
	_tool("delete", "Delete a file. The workspace is one flat folder: file names only, no subfolders.", {"path": {"type": "string"}}),
]


def _resolve(name):
	# flat folder: a plain file name only, nothing that can leave system/
	if name in ("", "."):
		return SYSTEM_DIR
	if name != os.path.basename(name) or name == ".." or "\\" in name:
		raise ValueError(f"invalid name: {name} (file names only, no folders)")
	full = os.path.join(SYSTEM_DIR, name)
	if os.path.islink(full):
		raise ValueError(f"invalid name: {name}")
	return full


def read(path):
	full = _resolve(path)
	if not os.path.exists(full):
		if full == SYSTEM_DIR:
			return "(empty)"
		return f"not found: {path}"
	if os.path.isdir(full):
		lines = [f"{n}  {os.path.getsize(os.path.join(full, n))} bytes" for n in sorted(os.listdir(full))]
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
	with open(full, "w", encoding="utf-8") as f:
		f.write(content)
	return f"wrote {len(content)} characters to {path}"


def delete(path):
	full = _resolve(path)
	if full == SYSTEM_DIR or os.path.isdir(full):
		return f"invalid name: {path}"
	if not os.path.exists(full):
		return f"not found: {path}"
	os.remove(full)
	return f"deleted {path}"


def run_tool(name, arguments):
	try:
		args = json.loads(arguments) if isinstance(arguments, str) else arguments
		if name == "read":
			return read(args["path"])
		if name == "write":
			return write(args["path"], args["content"])
		if name == "delete":
			return delete(args["path"])
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
