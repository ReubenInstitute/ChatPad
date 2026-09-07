import datetime
from datetime import datetime, timezone
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
		if messages:
			_, data = messages[0]
			prompt = data.get("prompt", "")
			if prompt:
				title = prompt[:30]
				if len(prompt) > 30:
					title += "..."
		sessions.append((session_id, timestamp_str, title))
	sessions.sort(key=lambda x: x[1], reverse=True)
	return sessions

def get_session(session_id):
	messages = []
	for name, data in read_session_messages(session_id):
		uuid_str = name[:-5]
		timestamp_str = uuid7_timestamp(uuid_str)
		data["timestamp"] = timestamp_str
		messages.append(data)
	return messages


def session_message(prompt, model, reasoning=True, session=None):
	if session is None:
		session = str(uuid7.create(datetime.now(timezone.utc)))

	existing = read_session_messages(session)
	history = [[data.get("prompt", ""), data.get("response", "")] for _, data in existing]

	response = OpenRouter.message(prompt, model, reasoning, history)

	msg_uuid = str(uuid7.create(datetime.now(timezone.utc)))
	response["session"] = session
	response["uuid"] = msg_uuid
	response["prompt"] = prompt
	response["model"] = model
	if "error" not in response:
		response["response"] = response["choices"][0]["message"]["content"]
		response["reasoning"] = response["choices"][0]["message"].get("reasoning", "")

	existing.append((f"{msg_uuid}.json", response))
	write_session_messages(session, existing)

	return response



def stream_session_message(prompt, model, reasoning, session):
	if session is None:
		session = str(uuid7.create(datetime.now(timezone.utc)))

	existing = read_session_messages(session)
	history = [[data.get("prompt", ""), data.get("response", "")] for _, data in existing]

	def save_callback(data):
		msg_uuid = str(uuid7.create(datetime.now(timezone.utc)))
		data["session"] = session
		data["uuid"] = msg_uuid
		data["prompt"] = prompt
		data["model"] = model
		if "error" not in data:
			data["response"] = data["choices"][0]["message"]["content"]
			data["reasoning"] = data["choices"][0]["message"].get("reasoning", "")
		existing.append((f"{msg_uuid}.json", data))
		write_session_messages(session, existing)

	for chunk in OpenRouter.stream_message(prompt, model, reasoning, history, on_complete=save_callback):
		yield chunk



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
