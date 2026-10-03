import os
import io
import json
import tarfile
from chatpad import SESSIONS_FOLDER, ARCHIVE_FOLDER, SESSION_PATTERN, read_session_messages

def _write_tar(path, messages):
	tmp_path = path + ".tmp"
	messages = sorted(messages, key=lambda m: m[0])
	with tarfile.open(tmp_path, "w:bz2") as tar:
		for name, data in messages:
			raw = json.dumps(data, indent=2).encode("utf-8")
			info = tarfile.TarInfo(name=name)
			info.size = len(raw)
			tar.addfile(info, io.BytesIO(raw))
	os.replace(tmp_path, path)

def migrate_folder(folder):
	if not os.path.isdir(folder):
		return
	for name in os.listdir(folder):
		if not name.endswith(".tar.bz2"):
			continue
		session_id = name[:-len(".tar.bz2")]
		if not SESSION_PATTERN.match(session_id):
			continue
		messages = read_session_messages(session_id)
		changed = False
		for _, data in messages:
			model = data.get("model")
			if model and not model.startswith("openrouter/"):
				data["model"] = f"openrouter/{model}"
				changed = True
		if changed:
			_write_tar(os.path.join(folder, name), messages)
			print(f"migrated {session_id}")

if __name__ == "__main__":
	migrate_folder(SESSIONS_FOLDER)
	migrate_folder(ARCHIVE_FOLDER)
