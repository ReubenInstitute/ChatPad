import glob
import os

FOLDER = os.path.dirname(os.path.abspath(__file__))


def path(name):
	return os.path.join(FOLDER, name)


def keys():
	names = [os.path.basename(p) for p in glob.glob(path("key*.txt"))]
	return sorted(n for n in names if n != "key.txt")


def rotate():
	names = keys()
	if not names:
		raise SystemExit("no keys found")
	link = path("key.txt")
	current = os.readlink(link) if os.path.islink(link) else None
	index = names.index(current) if current in names else -1
	next_key = names[(index + 1) % len(names)]
	if os.path.islink(link):
		os.remove(link)
	os.symlink(next_key, link)
	return next_key


if __name__ == "__main__":
	print("rotated to:", rotate())
