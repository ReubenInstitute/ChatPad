import os

FOLDER = os.path.dirname(os.path.abspath(__file__))


def path(name):
	return os.path.join(FOLDER, name)


def rotate():
	for name in ("key.txt", "key1.txt", "key2.txt"):
		if not os.path.isfile(path(name)):
			raise SystemExit(f"missing: {name}")
	if os.path.exists(path("key.tmp")):
		raise SystemExit("key.tmp exists, a previous rotation stopped halfway; rename the files back by hand first")
	os.rename(path("key.txt"), path("key.tmp"))
	os.rename(path("key1.txt"), path("key.txt"))
	os.rename(path("key2.txt"), path("key1.txt"))
	os.rename(path("key.tmp"), path("key2.txt"))


if __name__ == "__main__":
	rotate()
	print("rotated: key1 -> key, key2 -> key1, old key -> key2")
