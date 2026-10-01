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
import time
import ast
import math
import operator
import requests
import markdown
from diff_match_patch import diff_match_patch

from openrouter import OpenRouter
from deepseek import DeepSeek
from local import Qwen

MARKDOWN_EXTENSIONS = ['tables', 'fenced_code', 'codehilite', 'nl2br']

APP_DIR = os.path.dirname(os.path.abspath(__file__))
SESSIONS_FOLDER = os.path.join(APP_DIR, "sessions")
ARCHIVE_FOLDER = os.path.join(APP_DIR, "archive")
SESSION_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12}$')
TURN_PATTERN = re.compile(r'^([0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[0-9a-f]{4}-[0-9a-f]{12})\.json$')

MAX_STEPS = 50
PATCH_INTERVAL = 0.08

SYSTEM_DIR = os.getcwd()
COMMAND_TIMEOUT = 30
TODO_FILE = "todo.md"

# tools whose result carries no content, so their block stays collapsed and
# has nothing to expand to
NO_CONTENT_TOOLS = {"rename_file", "copy_file", "delete_file", "make_folder", "remove_folder"}

CALC_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow}
CALC_NAMES = {"pi": math.pi, "e": math.e}
CALC_FUNCS = {n: getattr(math, n) for n in ("sqrt", "sin", "cos", "tan", "log", "log10", "exp", "floor", "ceil")}
CALC_FUNCS.update({"abs": abs, "round": round, "min": min, "max": max})


class ToolError(Exception):
	pass


class Chat:
	def __init__(self):
		self.openrouter = OpenRouter()
		self.deepseek = DeepSeek()
		self.local = Qwen()
		self.toolbox = Toolbox()

	@property
	def models(self):
		return self.openrouter.models + self.deepseek.models + self.local.models

	@property
	def free_models(self):
		return self.openrouter.free_models + self.deepseek.free_models + self.local.free_models

	def list(self, archived=False):
		root = ARCHIVE_FOLDER if archived else SESSIONS_FOLDER
		sessions = []
		if not os.path.isdir(root):
			return sessions
		seen = set()
		for name in os.listdir(root):
			if name.endswith(".tar.bz2"):
				session_id = name[:-len(".tar.bz2")]
			elif SESSION_PATTERN.match(name) and os.path.isdir(os.path.join(root, name)):
				session_id = name
			else:
				continue
			if not SESSION_PATTERN.match(session_id) or session_id in seen:
				continue
			seen.add(session_id)
			session = Session(uuid=session_id)
			prompt = next((b["content"] for m in session.messages for b in m.blocks if b["type"] == "prompt"), "")
			title = "(empty)"
			if prompt:
				title = prompt[:30] + ("..." if len(prompt) > 30 else "")
			sessions.append((session_id, session.timestamp, title))
		sessions.sort(key=lambda x: x[1], reverse=True)
		return sessions

	def group_by_day(self, archived=False):
		groups = []
		for session in self.list(archived=archived):
			day = session[1][:8]
			if groups and groups[-1][0] == day:
				groups[-1][1].append(session)
			else:
				groups.append((day, [session]))
		return groups

	def message(self, prompt, model, reasoning=True, session=None, tools=None, mode="auto"):
		if session is None:
			session = str(uuid7.create(datetime.now(timezone.utc)))
		session_obj = Session(uuid=session)
		model_obj = next((m for m in self.models if m.id == model), None)
		if model_obj is None:
			raise ValueError(f"unknown model: {model}")
		active_tools = [t.schema for t in self.toolbox.tools if tools is not None and t.name in tools]

		msg = Message(session=session_obj)
		msg.uuid = msg.next_uuid()
		turn = MessageTurn(message=msg, uuid=msg.uuid, model=model_obj.id, think=reasoning, prompt=prompt)
		msg.turns.append(turn)
		yield {"type": "prompt", "content": prompt, "model": model_obj.id, "uuid": turn.uuid,
				"timestamp": turn.timestamp, "session": session}
		turn.save()

		yield from msg.run(model_obj, reasoning, active_tools, tools, mode, self.toolbox)

	def resume(self, session_id, action, model, reasoning=True, tools=None, mode="auto"):
		session_obj = Session(uuid=session_id)
		model_obj = next((m for m in self.models if m.id == model), None)
		active_tools = [t.schema for t in self.toolbox.tools if tools is not None and t.name in tools]

		messages = session_obj.messages
		if not messages:
			return
		msg = messages[-1]
		pending = msg.pending
		if not pending:
			return

		if action == "stop":
			for tool_turn in pending:
				tool_turn.error = {"message": "Stopped by user."}
				tool_turn.save()
			yield {"type": "tool_stopped", "session": session_id}
			return

		for tool_turn in pending:
			if action == "deny":
				tool_turn.response = "User denied this tool call."
			else:
				output, tool_error = self.toolbox.run(tool_turn.tool, tool_turn.arguments, tools or [])
				tool_turn.response = output
				if tool_error:
					tool_turn.error = {"message": tool_error}
			tool_turn.save()
			yield {"type": "tool_result", "tool_call_id": tool_turn.uuid, "name": tool_turn.tool,
					"content": tool_turn.response, "error": tool_turn.error,
					"uuid": tool_turn.uuid, "timestamp": tool_turn.timestamp, "session": session_id}

		if model_obj is None:
			return
		yield from msg.run(model_obj, reasoning, active_tools, tools, mode, self.toolbox)


class Session:
	def __init__(self, uuid=None):
		self.uuid = uuid

	def __repr__(self):
		return self.timestamp

	@property
	def timestamp(self):
		u = uuid.UUID(self.uuid)
		dt = uuid7.time(u)
		ms = dt.microsecond // 1000
		return dt.strftime("%Y%m%d%H%M%S") + f"{ms:03d}"

	@property
	def archived(self):
		return (os.path.isfile(os.path.join(ARCHIVE_FOLDER, f"{self.uuid}.tar.bz2"))
				or os.path.isdir(os.path.join(ARCHIVE_FOLDER, self.uuid)))

	@property
	def root(self):
		return ARCHIVE_FOLDER if self.archived else SESSIONS_FOLDER

	@property
	def folder(self):
		return os.path.join(self.root, self.uuid)

	@property
	def archive_path(self):
		return self.folder + ".tar.bz2"

	@property
	def packed(self):
		return os.path.isfile(self.archive_path) and not os.path.isdir(self.folder)

	def unpack(self):
		if not self.packed:
			return
		os.makedirs(self.folder, exist_ok=True)
		with tarfile.open(self.archive_path, "r:bz2") as tar:
			tar.extractall(self.folder)
		os.remove(self.archive_path)

	def pack(self):
		if self.packed or not os.path.isdir(self.folder):
			return
		os.makedirs(self.root, exist_ok=True)
		tmp = self.archive_path + ".tmp"
		with tarfile.open(tmp, "w:bz2") as tar:
			for name in sorted(os.listdir(self.folder)):
				if TURN_PATTERN.match(name):
					tar.add(os.path.join(self.folder, name), arcname=name)
		os.replace(tmp, self.archive_path)
		shutil.rmtree(self.folder)

	def archive(self):
		self.pack()
		os.makedirs(ARCHIVE_FOLDER, exist_ok=True)
		src = os.path.join(SESSIONS_FOLDER, f"{self.uuid}.tar.bz2")
		if os.path.isfile(src):
			os.replace(src, os.path.join(ARCHIVE_FOLDER, f"{self.uuid}.tar.bz2"))

	def unarchive(self):
		self.pack()
		src = os.path.join(ARCHIVE_FOLDER, f"{self.uuid}.tar.bz2")
		if os.path.isfile(src):
			os.makedirs(SESSIONS_FOLDER, exist_ok=True)
			os.replace(src, os.path.join(SESSIONS_FOLDER, f"{self.uuid}.tar.bz2"))

	@property
	def messages(self):
		if self.packed:
			self.unpack()
		if not os.path.isdir(self.folder):
			return []
		filenames = sorted(f for f in os.listdir(self.folder) if TURN_PATTERN.match(f))
		messages = {}
		order = []
		for filename in filenames:
			with open(os.path.join(self.folder, filename)) as f:
				data = json.load(f)
			message_uuid = data["message"]
			if message_uuid not in messages:
				messages[message_uuid] = Message(uuid=message_uuid, session=self)
				order.append(message_uuid)
			messages[message_uuid].turns.append(Turn.load(messages[message_uuid], data))
		return [messages[u] for u in order]

	@property
	def blocks(self):
		return [b for m in self.messages for b in m.blocks]

	@property
	def history(self):
		history = []
		for message in self.messages:
			if message.hidden:
				continue
			blocks = message.blocks
			types = {b["type"] for b in blocks}
			if "error" in types and not types & {"response", "tool_call"}:
				continue  # the prompt got no answer, don't send it
			for b in blocks:
				t = b["type"]
				if t == "prompt":
					history.append({"role": "user", "content": b["content"]})
				elif t == "tool_call":
					history.append({"role": "assistant", "content": b.get("content"), "tool_calls": b["tool_calls"]})
				elif t == "tool_result":
					history.append({"role": "tool", "tool_call_id": b["tool_call_id"], "content": b["content"]})
				elif t == "response" and b.get("content"):
					history.append({"role": "assistant", "content": b["content"]})
		return history


class Message:
	def __init__(self, uuid=None, session=None):
		self.uuid = uuid
		self.session = session
		self.turns = []

	def next_uuid(self):
		dt = datetime.now(timezone.utc)
		if self.turns and self.turns[-1].uuid:
			last = uuid7.time(uuid.UUID(self.turns[-1].uuid))
			if dt < last + timedelta(milliseconds=1):
				dt = last + timedelta(milliseconds=1)
		return str(uuid7.create(dt))

	@property
	def hidden(self):
		return bool(self.turns) and self.turns[0].hidden

	def hide(self):
		if self.turns:
			self.turns[0].hidden = True
			self.turns[0].save()

	def unhide(self):
		if self.turns:
			self.turns[0].hidden = False
			self.turns[0].save()

	@property
	def pending(self):
		pending = []
		for turn in reversed(self.turns):
			if isinstance(turn, ToolTurn) and turn.response is None and turn.error is None:
				pending.insert(0, turn)
			else:
				break
		return pending or None

	@property
	def blocks(self):
		blocks = []
		turns = self.turns
		i = 0
		while i < len(turns):
			turn = turns[i]
			i += 1
			if not isinstance(turn, MessageTurn):
				continue
			if turn.prompt is not None:
				blocks.append({"type": "prompt", "content": turn.prompt, "model": turn.model,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "hidden": turn.hidden, "session": self.session.uuid})
			if turn.reasoning:
				blocks.append({"type": "reasoning", "content": turn.reasoning,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": self.session.uuid})
			if turn.error:
				blocks.append({"type": "error", "error": turn.error, "model": turn.model,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": self.session.uuid})
				continue
			run = []
			while i < len(turns) and isinstance(turns[i], ToolTurn):
				run.append(turns[i])
				i += 1
			if run:
				blocks.append({"type": "tool_call", "content": turn.response,
						"tool_calls": [{"id": t.uuid, "function": {"name": t.tool, "arguments": t.arguments}} for t in run],
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": self.session.uuid})
				for t in run:
					blocks.append({"type": "tool_result", "tool_call_id": t.uuid, "name": t.tool,
							"content": t.response, "error": t.error,
							"uuid": t.uuid, "timestamp": t.timestamp, "session": self.session.uuid})
			elif turn.response:
				usage = (turn.raw or {}).get("usage") or {}
				blocks.append({"type": "response", "content": turn.response, "model": turn.model,
						"cost": usage.get("cost"), "usage": usage,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": self.session.uuid})
		return blocks

	def run(self, model, reasoning, active_tools, tool_names, mode, toolbox):
		session_uuid = self.session.uuid
		for step in range(MAX_STEPS):
			turn = MessageTurn(message=self, uuid=self.next_uuid(), model=model.id, think=reasoning)
			self.turns.append(turn)
			reasoning_parts = []
			content_parts = []
			reasoning_html = ""
			content_html = ""
			tool_calls = None
			finish_reason = None
			usage = {}
			error = None
			dmp = diff_match_patch()
			last_flush = time.monotonic()

			def flush(target):
				# Re-rendering the whole accumulated text and diffing it is O(length),
				# so doing it on every token makes a long reply quadratic. Rate-limit
				# it instead; each flush also persists the turn, so a reload loses at
				# most the unflushed tail.
				nonlocal reasoning_html, content_html
				parts = reasoning_parts if target == "reasoning" else content_parts
				old_html = reasoning_html if target == "reasoning" else content_html
				new_html = Turn.render_markdown("".join(parts))
				if new_html == old_html:
					return None
				if target == "reasoning":
					reasoning_html = new_html
					turn.reasoning = "".join(parts)
				else:
					content_html = new_html
					turn.response = "".join(parts)
				turn.save()
				return {"type": "html_patch", "target": target,
						"patch": dmp.patch_toText(dmp.patch_make(old_html, new_html)), "session": session_uuid}

			for event in model.message(self.session.history, reasoning, active_tools):
				if "error" in event:
					error = event["error"]
					break
				kind = event.get("delta")
				if kind == "reasoning":
					reasoning_parts.append(event["text"])
					if time.monotonic() - last_flush >= PATCH_INTERVAL:
						last_flush = time.monotonic()
						patch = flush("reasoning")
						if patch:
							yield patch
				elif kind == "content":
					content_parts.append(event["text"])
					if time.monotonic() - last_flush >= PATCH_INTERVAL:
						last_flush = time.monotonic()
						patch = flush("response")
						if patch:
							yield patch
				elif "result" in event:
					result = event["result"]
					message = result["choices"][0]["message"]
					finish_reason = result["choices"][0].get("finish_reason")
					usage = result.get("usage") or {}
					tool_calls = message.get("tool_calls")

			if error:
				if reasoning_parts:
					yield {"type": "discard_block", "target": "reasoning", "session": session_uuid}
				if content_parts:
					yield {"type": "discard_block", "target": "response", "session": session_uuid}
				turn.reasoning = "".join(reasoning_parts) or None
				turn.error = error
				turn.save()
				yield {"type": "error", "error": error, "model": model.id,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_uuid}
				return

			if reasoning_parts:
				turn.reasoning = "".join(reasoning_parts)
				turn.save()
				yield {"type": "reasoning", "content": turn.reasoning,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_uuid}

			if tool_calls:
				for call in tool_calls:
					try:
						json.loads(call["function"]["arguments"])
					except Exception:
						call["function"]["arguments"] = "{}"
				if content_parts:
					patch = flush("response")
					if patch:
						yield patch
					yield {"type": "finalize_block", "target": "response", "session": session_uuid}
				turn.response = "".join(content_parts) or None
				turn.save()

				run_turns = []
				for call in tool_calls:
					tool_turn = ToolTurn(message=self, uuid=self.next_uuid(), tool=call["function"]["name"], arguments=call["function"]["arguments"])
					self.turns.append(tool_turn)
					run_turns.append(tool_turn)
					tool_turn.save()

				yield {"type": "tool_call", "content": turn.response,
						"tool_calls": [{"id": t.uuid, "function": {"name": t.tool, "arguments": t.arguments}} for t in run_turns],
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_uuid}

				if mode == "manual":
					yield {"type": "await_approval", "session": session_uuid}
					return

				for tool_turn in run_turns:
					output, tool_error = toolbox.run(tool_turn.tool, tool_turn.arguments, tool_names or [])
					tool_turn.response = output
					if tool_error:
						tool_turn.error = {"message": tool_error}
					tool_turn.save()
					yield {"type": "tool_result", "tool_call_id": tool_turn.uuid, "name": tool_turn.tool,
							"content": tool_turn.response, "error": tool_turn.error,
							"uuid": tool_turn.uuid, "timestamp": tool_turn.timestamp, "session": session_uuid}
				continue

			if not content_parts:
				turn.error = {"message": f"Empty reply from model (finish_reason: {finish_reason})", "code": None}
				turn.save()
				yield {"type": "error", "error": turn.error, "model": model.id,
						"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_uuid}
				return

			turn.response = "".join(content_parts)
			turn.raw = {"usage": usage}
			turn.save()
			yield {"type": "response", "content": turn.response, "model": model.id,
					"cost": usage.get("cost"), "usage": usage,
					"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_uuid}
			return

		turn = MessageTurn(message=self, uuid=self.next_uuid(), model=model.id,
				error={"message": f"Stopped after {MAX_STEPS} steps", "code": None})
		self.turns.append(turn)
		turn.save()
		yield {"type": "error", "error": turn.error, "model": model.id,
				"uuid": turn.uuid, "timestamp": turn.timestamp, "session": session_uuid}


class Turn:
	def __init__(self, message=None, uuid=None, response=None, error=None, raw=None, hidden=False):
		self.message = message
		self.uuid = uuid
		self.response = response
		self.error = error
		self.raw = raw
		self.hidden = hidden

	@property
	def timestamp(self):
		u = uuid.UUID(self.uuid)
		dt = uuid7.time(u)
		ms = dt.microsecond // 1000
		return dt.strftime("%Y%m%d%H%M%S") + f"{ms:03d}"

	@property
	def session(self):
		return self.message.session

	@property
	def path(self):
		return os.path.join(self.session.folder, f"{self.uuid}.json")

	def save(self):
		if self.session.packed:
			self.session.unpack()
		if self.uuid is None:
			self.uuid = str(uuid7.create(datetime.now(timezone.utc)))
		os.makedirs(self.session.folder, exist_ok=True)
		tmp = self.path + ".tmp"
		with open(tmp, "w") as f:
			json.dump(self.to_dict(), f, indent=2)
		os.replace(tmp, self.path)

	@staticmethod
	def load(message, data):
		if data.get("kind") == "tool":
			return ToolTurn.from_dict(message, data)
		return MessageTurn.from_dict(message, data)

	@staticmethod
	def render_markdown(text):
		if text is None:
			return ""
		return markdown.markdown(text, extensions=MARKDOWN_EXTENSIONS)


class MessageTurn(Turn):
	def __init__(self, message=None, uuid=None, model=None, think=False, prompt=None, reasoning=None,
			response=None, error=None, raw=None, hidden=False):
		super().__init__(message=message, uuid=uuid, response=response, error=error, raw=raw, hidden=hidden)
		self.model = model
		self.think = think
		self.prompt = prompt
		self.reasoning = reasoning

	def to_dict(self):
		return {"kind": "message", "message": self.message.uuid, "uuid": self.uuid,
				"model": self.model, "think": self.think, "prompt": self.prompt, "reasoning": self.reasoning,
				"response": self.response, "error": self.error, "raw": self.raw, "hidden": self.hidden}

	@staticmethod
	def from_dict(message, data):
		return MessageTurn(message=message, uuid=data.get("uuid"), model=data.get("model"),
				think=data.get("think", False), prompt=data.get("prompt"), reasoning=data.get("reasoning"),
				response=data.get("response"), error=data.get("error"), raw=data.get("raw"), hidden=data.get("hidden", False))


class ToolTurn(Turn):
	def __init__(self, message=None, uuid=None, tool=None, arguments=None,
			response=None, error=None, raw=None, hidden=False):
		super().__init__(message=message, uuid=uuid, response=response, error=error, raw=raw, hidden=hidden)
		self.tool = tool
		self.arguments = arguments

	def to_dict(self):
		return {"kind": "tool", "message": self.message.uuid, "uuid": self.uuid,
				"tool": self.tool, "arguments": self.arguments,
				"response": self.response, "error": self.error, "raw": self.raw, "hidden": self.hidden}

	@staticmethod
	def from_dict(message, data):
		return ToolTurn(message=message, uuid=data.get("uuid"), tool=data.get("tool"), arguments=data.get("arguments"),
				response=data.get("response"), error=data.get("error"), raw=data.get("raw"), hidden=data.get("hidden", False))


class Tool:
	def __init__(self, name, label, description, properties, handler, required=None):
		self.name = name
		self.label = label
		self.description = description
		self.properties = properties
		self.required = list(properties) if required is None else required
		self.handler = handler

	@property
	def schema(self):
		return {"type": "function", "function": {"name": self.name, "description": self.description,
				"parameters": {"type": "object", "properties": self.properties, "required": self.required}}}

	def run(self, arguments):
		try:
			args = json.loads(arguments) if isinstance(arguments, str) else (arguments or {})
			return self.handler(**args), None
		except ToolError as e:
			return str(e), str(e)
		except Exception as e:
			message = f"error: {type(e).__name__}: {e}"
			return message, message


class Toolbox:
	def __init__(self):
		self.tools = [
			Tool("read_file", "Read file", "Read a file, or list a folder.",
					{"path": {"type": "string"}}, self.read_file),
			Tool("write_file", "Write file", "Create a file, or replace it if it exists.",
					{"path": {"type": "string"}, "content": {"type": "string"}}, self.write_file),
			Tool("edit_file", "Edit file", "Replace one piece of text in a file. `old` must appear exactly once; include enough surrounding text to make it unique.",
					{"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, self.edit_file),
			Tool("append_file", "Append file", "Add text to the end of a file, creating it if needed.",
					{"path": {"type": "string"}, "content": {"type": "string"}}, self.append_file),
			Tool("rename_file", "Rename file", "Rename a file. Fails if the new name already exists.",
					{"path": {"type": "string"}, "new_path": {"type": "string"}}, self.rename_file),
			Tool("copy_file", "Copy file", "Copy a file. Fails if the new name already exists.",
					{"path": {"type": "string"}, "new_path": {"type": "string"}}, self.copy_file),
			Tool("get_url", "Get URL", "Fetch an http or https URL and return the content as text.",
					{"url": {"type": "string"}}, self.get_url),
			Tool("download_url", "Download URL", "Download an http or https URL and save it to a path exactly as downloaded.",
					{"url": {"type": "string"}, "path": {"type": "string"}}, self.download_url),
			Tool("delete_file", "Delete file", "Delete a file.",
					{"path": {"type": "string"}}, self.delete_file),
			Tool("current_time", "Current time", "Get the current date and time on the server.",
					{}, self.current_time),
			Tool("calculator", "Calculator", "Evaluate an arithmetic expression exactly. Supports + - * / // % **, parentheses, pi, e, and sqrt sin cos tan log log10 exp floor ceil abs round min max.",
					{"expression": {"type": "string"}}, self.calculator),
			Tool("todo", "Todo", "Keep a todo list (stored in todo.md). Actions: add (item is the text), done (item is the number), remove (item is the number), list. Returns the updated list.",
					{"action": {"type": "string", "enum": ["add", "done", "remove", "list"]}, "item": {"type": "string"}}, self.todo, required=["action"]),
			Tool("run_python", "Run Python", "Run Python 3 code and return what it prints, including errors. Each call is a fresh process, so print anything you want to see.",
					{"code": {"type": "string"}}, self.run_python),
			Tool("run_command", "Run command", "Run a shell command and return its output, including errors. Each call is a fresh shell, so cd does not carry over; pipes and && work.",
					{"command": {"type": "string"}}, self.run_command),
			Tool("make_folder", "Make folder", "Create a folder, including any missing parent folders.",
					{"path": {"type": "string"}}, self.make_folder),
			Tool("remove_folder", "Remove folder", "Remove an empty folder.",
					{"path": {"type": "string"}}, self.remove_folder),
		]

	def find(self, name):
		return next((t for t in self.tools if t.name == name), None)

	def run(self, name, arguments, allowed):
		if name not in allowed:
			message = f"tool not enabled: {name}"
			return message, message
		tool = self.find(name)
		if tool is None:
			message = f"unknown tool: {name}"
			return message, message
		return tool.run(arguments)

	def _resolve(self, path):
		path = path.lstrip("~").lstrip("/")
		if path in ("", "."):
			return SYSTEM_DIR
		return os.path.normpath(os.path.join(SYSTEM_DIR, path))

	def read_file(self, path):
		full = self._resolve(path)
		if os.path.isdir(full):
			return "\n".join(sorted(os.listdir(full)))
		with open(full, "r", encoding="utf-8") as f:
			return f.read()

	def write_file(self, path, content):
		full = self._resolve(path)
		with open(full, "w", encoding="utf-8") as f:
			f.write(content)
		return f"wrote {len(content)} characters to {path}"

	def edit_file(self, path, old, new):
		full = self._resolve(path)
		with open(full, "r", encoding="utf-8") as f:
			text = f.read()
		count = text.count(old)
		if count != 1:
			raise ToolError(f"text found {count} times in {path}; it must appear exactly once")
		with open(full, "w", encoding="utf-8") as f:
			f.write(text.replace(old, new))
		return f"edited {path}"

	def append_file(self, path, content):
		full = self._resolve(path)
		with open(full, "a", encoding="utf-8") as f:
			f.write(content)
		return f"appended {len(content)} characters to {path}"

	def _move_or_copy(self, path, new_path, action):
		source = self._resolve(path)
		target = self._resolve(new_path)
		if os.path.lexists(target):
			raise ToolError(f"already exists: {new_path}")
		if action == "rename":
			os.rename(source, target)
		else:
			shutil.copyfile(source, target)
		return f"{'renamed' if action == 'rename' else 'copied'} {path} to {new_path}"

	def rename_file(self, path, new_path):
		return self._move_or_copy(path, new_path, "rename")

	def copy_file(self, path, new_path):
		return self._move_or_copy(path, new_path, "copy")

	def get_url(self, url):
		response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 ChatPad"}, timeout=20)
		if response.status_code != 200:
			raise ToolError(f"HTTP {response.status_code}")
		return response.content.decode("utf-8")

	def download_url(self, url, path):
		response = requests.get(url, headers={"User-Agent": "Mozilla/5.0 ChatPad"}, timeout=20)
		if response.status_code != 200:
			raise ToolError(f"HTTP {response.status_code}")
		data = response.content
		with open(self._resolve(path), "wb") as f:
			f.write(data)
		return data.decode("utf-8")

	def delete_file(self, path):
		os.remove(self._resolve(path))
		return f"deleted {path}"

	def make_folder(self, path):
		os.makedirs(self._resolve(path), exist_ok=True)
		return f"created folder {path}"

	def remove_folder(self, path):
		os.rmdir(self._resolve(path))
		return f"removed folder {path}"

	def current_time(self):
		return datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M:%S %Z (UTC%z)")

	def _calc(self, node):
		if isinstance(node, ast.Expression):
			return self._calc(node.body)
		if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
			return node.value
		if isinstance(node, ast.Name) and node.id in CALC_NAMES:
			return CALC_NAMES[node.id]
		if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
			value = self._calc(node.operand)
			return value if isinstance(node.op, ast.UAdd) else -value
		if isinstance(node, ast.BinOp) and type(node.op) in CALC_OPS:
			left, right = self._calc(node.left), self._calc(node.right)
			if isinstance(node.op, ast.Pow) and isinstance(left, int) and isinstance(right, int) and right > 0 and left.bit_length() * right > 100000:
				raise ToolError("result too large")
			return CALC_OPS[type(node.op)](left, right)
		if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in CALC_FUNCS and not node.keywords:
			return CALC_FUNCS[node.func.id](*[self._calc(a) for a in node.args])
		raise ToolError("unsupported expression")

	def calculator(self, expression):
		if len(expression) > 500:
			raise ToolError("expression too long")
		return str(self._calc(ast.parse(expression.strip(), mode="eval")))

	def _todo_load(self):
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

	def _todo_show(self, items):
		lines = [f"{i}. [{'x' if done else ' '}] {text}" for i, (done, text) in enumerate(items, 1)]
		return "\n".join(lines) or "(empty)"

	def todo(self, action, item=None):
		items = self._todo_load()
		if action == "list":
			return self._todo_show(items)
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
		return self._todo_show(items)

	def _execute(self, command, shell=False):
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
		return output or "(no output)"

	def run_python(self, code):
		with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
			f.write(code)
		try:
			return self._execute([sys.executable, f.name])
		finally:
			os.remove(f.name)

	def run_command(self, command):
		return self._execute(command, shell=True)
