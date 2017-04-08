"""A lightweight Javascript concatenator.

Lightning is an fast and efficient Javascript concatenator that
supports live builds.
"""

import watchdog.events
import watchdog.observers
import os
import glob
import time

INDEX = os.path.join(os.getcwd(), "lightning.conf")
HEAD = "@head"
REQUIRE = "@require"
PROVIDE = "@provide"


class Source:
    """Marked portion of a Javascript file that defines something."""

    def __init__(self, path:str):
        """Create a source file container."""

        self.path = path
        self.head = False
        self.require = []
        self.provide = []
        self.code = None
        self.search()

    def __getitem__(self, target:str):
        """Get the require or provide lists."""

        if target == REQUIRE:
            return self.require
        elif target == PROVIDE:
            return self.provide

    def __repr__(self):
        """Represent the source file as a string."""

        return "Source[" + os.path.basename(self.path) + "]"

    def search(self):
        """Search for require and provide statements."""

        with open(self.path) as file:
            code = file.read()
        self.code = code
        if code.find(HEAD) > -1:
            self.head = True
            return
        for target in (REQUIRE, PROVIDE):
            start = 0
            out = set()
            length = len(target)
            while True:
                index = code.find(target, start)
                if index < 0:
                    break
                newline = code.find("\n", index)
                separated = code[index+length+1:newline].split(",")
                out |= set(map(lambda x: x.strip(), separated))
                start = newline + 1
            self[target].clear()
            self[target].extend(out)

    def read(self, cache=True):
        """Read the contents of the file."""

        if self.code is None:
            with open(self.path) as file:
                code = file.read()
            self.code = code
            return code
        return self.code


def sep(path:str) -> str:
    """Fix a path according to the operating system."""

    return path.replace("/", os.sep)


def index(path:str=INDEX) -> [str]:
    """Get the build sources from the index file."""

    files = set()
    with open(path) as file:
        for line in file.readlines():
            if line.startswith("+"):
                files |= set(glob.glob(sep(line[1:].strip()), recursive=True))
            elif line.startswith("-"):
                files -= set(glob.glob(sep(line[1:].strip()), recursive=True))
    return list(map(os.path.abspath, files))


def source(paths:[str]) -> [Source]:
    """Map a list of paths to a list of sources."""

    return list(map(Source, paths))


def find(require, sources):
    """Find a source that provides a requirement from a list."""

    for source in sources:
        if require in source.provide:
            return source
    return None


def sort(sources:[Source]) -> [Source]:
    """Sort the sources topologically."""

    out = []
    sources = sources[:]
    for source in sources:
        if source.head:
            sources.remove(source)
            out.append(source)
    while sources:
        cyclic = True
        for source in sources:
            for require in source.require:
                if find(require, sources):
                    break
            else:
                cyclic = False
                sources.remove(source)
                out.append(source)
        if cyclic:
            raise RuntimeError(
                "Circular dependencies found in {}.".format(
                os.path.basename(source.path)))
    return out
                

def concatenate(sources:[Source], path:str) -> str:
    """Concatenate the source list."""

    with open(path, "w") as file:
        file.write("\n".join(map(lambda s: s.read(), sources)))


def common(paths:[str]) -> str:
    """Return the common path of a list with wildcard."""

    path = os.path.abspath(os.path.commonpath(paths))
    parts = path.split(os.sep)
    for i in range(len(parts)):
        if "*" in parts[i]:
            return os.path.sep.join(parts[:i])
    return path


class NaiveDeltaHandler(watchdog.events.FileSystemEventHandler):
    """Calls a full sort and concatenate when the filesystem changes."""

    def __init__(self, target:str, index:str=INDEX):
        """Initialize the file handler with its config path."""

        self.target = target
        self.index = index
        self.cache = {}
        self.build()

    def build(self):
        """Concatenate the source files."""

        sources = sort(source(index(self.index)))
        concatenate(source, self.target)

    def on_any_event(self, event: watchdog.events.FileSystemMovedEvent):
        """Called when any event is fired."""

        path = os.path.realpath(event.src_path)
        if path not in index(self.index):
            return
        try:
            mtime = os.path.getmtime(path)
        except FileNotFoundError:
            mtime = -1
        if self.cache.get(path, 0) >= mtime:
            return
        self.cache[path] = mtime
        self.build()


if __name__ == "__main__":
    import sys
    observer = watchdog.observers.Observer()
    observer.schedule(NaiveDeltaHandler(sys.argv[1]))

# TODO: make this work for multiple builds
# Implement YAML or something, idek
