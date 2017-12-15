#!/usr/local/bin/python3

"""A lightweight Javascript concatenator.

Lightning is an fast and efficient Javascript concatenator that
supports live builds.
"""

import watchdog.events
import watchdog.observers
import os
import glob
import time


INDEX = os.path.join(os.getcwd(), ".lightning.conf")
HEAD = "@head"
REQUIRE = "@require"
PROVIDE = "@provide"

        
class Source:
    """Javascript source file container."""

    def __init__(self, path: str):
        """Create a source file container."""

        self.path = os.path.abspath(path)
        self.code = None
        self.head = False
        self.require = []
        self.provide = []
        self.search()

    def __getitem__(self, target: str):
        """Get the require or provide lists."""

        return {REQUIRE: self.require, PROVIDE: self.provide}[target]

    def __repr__(self):
        """Represent the source file as a string."""

        return "Source[" + os.path.basename(self.path) + "]"

    def search(self, cache=True):
        """Search for require and provide statements."""

        # Read the file
        self.read(cache=cache)

        # Check if this is the head
        if self.code.find(HEAD) > -1:
            self.head = True
            return

        # Iterate search items
        for target in (REQUIRE, PROVIDE):
            start = 0
            out = set()
            length = len(target)
            
            while True:
                index = self.code.find(target, start)
                if index < 0:
                    break
                newline = self.code.find("\n", index)
                separated = self.code[index+length+1:newline].split(",")
                out |= set(map(lambda x: x.strip(), separated))
                start = newline + 1

            # Clear and set the search
            self[target].clear()
            self[target].extend(out)

    def read(self, cache=False):
        """Read the contents of the file."""

        # Read if not cached
        if self.code is None:
            with open(self.path) as file:
                code = file.read()
            self.code = code
            return code
        return self.code


def common(paths: [str]) -> str:
    """Return the common path of a list with wildcard."""

    path = os.path.abspath(os.path.commonpath(paths))
    parts = path.split(os.sep)
    for i in range(len(parts)):
        if "*" in parts[i]:
            return os.path.sep.join(parts[:i])
    return path


def find(require, sources):
    """Find a source that provides a requirement from a list."""

    for source in sources:
        if require in source.provide:
            return source
    return None


class Target:
    """A set of sources defined by an index file."""

    def __init__(self, target: str, include: [str], exclude: [str]):
        """Initialize a build with its target and source paths."""

        self.target = target
        self.include = include
        self.exclude = exclude
        self.sources = []
        self.common = common(include)

    def __repr__(self):
        """Represent the build as a string."""

        return "Target[{}:{}]".format(
            self.target, os.path.basename(self.common))

    def index(self):
        """Index the files defined by paths."""

        self.sources.clear()
        files = set()
        for path in self.include:
            files |= set(glob.glob(path, recursive=True))
        for path in self.exclude:
            files -= set(glob.glob(path, recursive=True))
        self.sources.extend(map(Source, files))

    def includes(self, path: str) -> bool:
        """Check if a source file is in the build include."""

        path = os.path.abspath(path)
        for source in self.sources:
            if source.path == path:
                return True
        return False

    def sort(self):
        """Sort the sources topologically."""

        correct = []

        # Put head in the front of the correct list
        for source in self.sources:
            if source.head:
                self.sources.remove(source)
                correct.append(source)

        # Do the algorithm
        while self.sources:
            cyclic = True
            for source in self.sources:
                for require in source.require:
                    if find(require, self.sources):
                        break
                else:
                    cyclic = False
                    self.sources.remove(source)
                    correct.append(source)

            # Break if there are cyclic dependencies
            if cyclic:
                raise RuntimeError(
                    "Circular dependencies found in {}.".format(
                    os.path.basename(source.path)))

        # Save correct ordering
        self.sources = correct

    def build(self):
        """Build and write the concatenated source files."""

        self.index()
        self.sort()
        print(self.sources)
        with open(self.target, "w") as file:
            for source in self.sources:
                file.write(source.read().rstrip() + "\n\n\n")
        print("Built {}".format(repr(self)))
                    

def sep(path: str) -> str:
    """Fix a path according to the operating system."""

    return path.replace("/", os.sep)
        

def index(path: str=INDEX) -> [Target]:
    """Get the build sources from the index file."""

    out = []
    with open(path) as file:
        target = None
        include = None
        exclude = None

        # Iterate the file
        for line in file:
            line = line.lstrip()
            first = line[0]

            # Check command
            if line == "" or first in "#;":
                continue
            elif first in "+-" and target is None:
                raise SyntaxWarning("Ignoring files not under build target.")
            elif first == "+":
                include.append(sep(line[1:].strip()))
            elif first == "-":
                exclude.append(sep(line[1:].strip()))

            # Add as a new target
            else:
                if include or exclude:
                    out.append(Target(target, include, exclude))
                target = line.strip()
                include = []
                exclude = []

        # Add the last target since this is like do while
        out.append(Target(target, include, exclude))

    # Return
    return out


class NaiveDeltaHandler(watchdog.events.FileSystemEventHandler):
    """Calls a full sort and concatenate when the filesystem changes."""

    def __init__(self, target: [Target]):
        """Initialize the file handler with its config path."""

        self.target = target
        self.cache = {}
        self.build()

    def build(self):
        """Concatenate the source files."""

        self.target.index()
        self.target.build()
            
    def on_any_event(self, event: watchdog.events.FileSystemMovedEvent):
        """Called when any event is fired."""

        path = os.path.realpath(event.src_path)
        self.target.index()
        if not self.target.includes(path):
            return
        try:
            mtime = os.path.getmtime(path)
        except FileNotFoundError:
            mtime = -1
        if self.cache.get(path, 0) >= mtime:
            return
        self.cache[path] = mtime
        target.build()


if __name__ == "__main__":
    """This is run if someone calls lightning from the command line."""

    import sys
    path = INDEX
    if len(sys.argv) > 1:
        path = sys.argv[1]

    # Create the observer
    observer = watchdog.observers.Observer()
    for target in index(path=path):
        handler = NaiveDeltaHandler(target)
        observer.schedule(handler, target.common, recursive=True)
    observer.start()

    # Wait for kill command
    while True:
        try:
            time.sleep(0.5)
        except KeyboardInterrupt:
            observer.stop()
            break
