# Import of necessary modules {{{

# For parsing command line arguments
import argparse

# For data containers
import collections

# For reading configuration files (Note: Configuration files
# will be written in Microsoft's INI format)
import configparser

# For using SHA-1 function
import hashlib

# For filesystem abstractions
import os

# For Regular Expressions
import re

# For accessing the command line arguments
import sys

# For compression
import zlib

# }}}

# Initialization of Argument Parser {{{

argparser = argparse.ArgumentParser(
    description="The Comment Tracker"
)
# Add subparsers to parse commands
argsubparsers = argparser.add_subparsers(
    title="Commands", dest="command"
)
argsubparsers.required = True

# Add init command argument {{

argsp = argsubparsers.add_parser(
    "init", help="Initialize a new, empty repository."
)
argsp.add_argument("path",
                   metavar="directory",
                   nargs="?",
                   default=".",
                   help="Where to create the repository.")

# }}

# Add cat-file command argument {{

argsp = argsubparsers.add_parser("cat-file",
    help="Provide content of repository objects")

argsp.add_argument("type",
    metavar="type",
    choices=["blob", "commit", "tag", "tree"],
    help="Specify the type")

argsp.add_argument("object",
    metavar="object",
    help="The object to display")

# }}

# Add hash-object command argument {{

argsp = argsubparsers.add_parser(
    "hash-object",
    help="Compute object ID and optionally creates\
        a blob from a file")

argsp.add_argument("-t",
    metavar="type",
    dest="type",
    choices=["blob", "commit", "tag", "tree"],
    default="blob",
    help="Specify the type")

argsp.add_argument("-w",
    dest="write",
    action="store_true",
    help="Actually write the object into the database")

argsp.add_argument("path",
    help="Read object from <file>")

# }}

# Add log command argument {{

argsp = argsubparsers.add_parser("log", 
    help="Display history of a given commit.")
argsp.add_argument("commit",
    default="HEAD",
    nargs="?",
    help="Commit to start at.")

# }}

# Add ls-tree command argument {{

argsp = argsubparsers.add_parser("ls-tree", 
    help="Pretty-print a tree object.")
argsp.add_argument("object",
    help="The object to show.")

def cmd_ls_tree(args):
    repo = repo_find()
    obj = object_read(repo, object_find(repo, args.object, 
        fmt=b'tree'))

    for item in obj.items:
        print("{0} {1} {2}\t{3}".format(
            "0" * (6 - len(item.mode)) 
            + item.mode.decode("ascii"),

            # Git's ls-tree displays the type
            # of the object pointed to. 
            # We can do that too :)
            object_read(repo, item.sha).fmt.decode("ascii"),
            item.sha,
            item.path.decode("ascii")))

# }}

# Add checkout command functionality {{

'''
    We’re going to oversimplify the actual git command to 
    make our implementation clear and understandable. 
    We’re also going to add a few safeguards. 
    Here’s how our version of checkout will work:

    1) It will take two arguments: a commit, and a 
    directory. Git checkout only needs a commit.
    2) It will then instantiate the tree in the directory,
    if and only if the directory is empty. Git is full of 
    safeguards to avoid deleting data, which would be too 
    complicated and unsafe to try to reproduce in pvc. 
    Since the point of pvc is to demonstrate git,
    not to produce a working implementation, 
    this limitation is acceptable.
'''

argsp = argsubparsers.add_parser("checkout", 
    help="Checkout a commit inside of a directory.")

argsp.add_argument("commit",
    help="The commit or tree to checkout.")

argsp.add_argument("path",
    help="The EMPTY directory to checkout on.")

# }}

# Add show-ref command argument
argsp = argsubparsers.add_parser("show-ref", 
    help="List references.")

# }}}

# Git Objects {{{

# Stand-in for a Git Repository
class GitRepository(object):
    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False):
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception("Not a git repository %s"%path)

        # Read configuration file in .git/config
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing")

        if not force:
            vers = int(self.conf.get(
                "core", "repositoryformatversion"
            ))
            if vers != 0:
                raise Exception(
                    "Unsupported repositoryformatversion %s"
                    % vers
                )

# Abstract class for a generic Git Object
class GitObject(object):
    repo = None

    def __init__(self, repo, data=None):
        self.repo = repo

        if data != None:
            self.deserialize(data)

    def serialize(self):
        # This function MUST be implemented by subclasses.
        # It must read the object's contents from 
        # self.data, a byte string, and do whatever it 
        # takes to convert it into a meaningful 
        # representation. What exactly that means 
        # depend on each subclass.
        raise Exception("Unimplemented!")

    def deserialize(self, data):
        # This function MUST be implemented by subclasses.
        raise Exception("Unimplemented!")

# GitObject for type Blob
class GitBlob(GitObject):
    fmt = b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data

# GitObject for type Commit
class GitCommit(GitObject):
    fmt=b'commit'

    def deserialize(self, data):
        self.kvlm = kvlm_parse(data)

    def serialize(self):
        return kvlm_serialize(self.kvlm)

# Object for Tree Leaf
# Represents a Tree object in Git
class GitTreeLeaf(object):
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha

# GitObject for type Tree
class GitTree(GitObject):
    fmt=b'tree'

    def deserialize(self, data):
        self.items = tree_parse(data)

    def serialize(self):
        return tree_serialize(self)

# }}}

# Helper Functions {{{

# For file Paths {{

def repo_path(repo, *path):
    # Compute the path under repo's gitdir
    return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
    # Same as repo path but can create dirname(*path) if
    # absent
    if repo_dir(repo, *path[:-1], mkdir=mkdir):
        return repo_path(repo, *path)

def repo_dir(repo, *path, mkdir=False):
    # Same as repo_path, but mkdir *path if absent and if
    # mkdir is true
    path = repo_path(repo, *path)

    if os.path.exists(path):
        if os.path.isdir(path):
            return path
        else:
            raise Exception("Not a directory %s" % path)

    if mkdir:
        os.makedirs(path)
        return path
    else:
        return None

def repo_find(path=".", required=True):
    path = os.path.realpath(path)

    if os.path.isdir(os.path.join(path, ".git")):
        return GitRepository(path)

    # If we haven't returned, recurse in parent, if w
    parent = os.path.realpath(os.path.join(path, ".."))

    if parent == path:
        # Bottom case
        # os.path.join("/", "..") == "/":
        # If parent==path, then path is root.
        if required:
            raise Exception("No git directory.")
        else:
            return None

    # Recursive case
    return repo_find(parent, required)

# }}

# Repository Creation {{

def repo_create(path):
    repo = GitRepository(path, True)

    if os.path.exists(repo.worktree):
        if not os.path.isdir(repo.worktree):
            raise Exception("%s is not a directory!" % path)
        if not os.listdir(repo.worktree):
            raise Exception("%s is not empty!" % path)
    else:
        os.makedirs(repo.worktree)

    assert(repo_dir(repo, "branches", mkdir=True))
    assert(repo_dir(repo, "objects", mkdir=True))
    assert(repo_dir(repo, "refs", "tags", mkdir=True))
    assert(repo_dir(repo, "refs", "heads", mkdir=True))

    # .git/description
    with open(repo_file(repo, "description"), "w") as f:
        f.write(
            "Unnamed repository; edit this file to name \
            repository\n"
        )

    # .git/HEAD
    with open(repo_file(repo, "HEAD"), "w") as f:
        f.write("ref: refs/heads/master\n")

    with open(repo_file(repo, "config"), "w") as f:
        config = repo_default_config()
        config.write(f)

    return repo

def repo_default_config():
    ret = configparser.ConfigParser()

    ret.add_section("core")
    ret.set("core", "repositoryformatversion", "0")
    ret.set("core", "filemode", "false")
    ret.set("core", "bare", "false")

    return ret

# }}

# For reading/writing Objects {{

def object_read(repo, sha):
    # Read object with object_id from Git repository.
    # Return a GitObject whose exact type depends on the
    # object itself.

    path = repo_file(repo, "objects", sha[0:2], sha[2:])

    with open(path, "rb") as f:
        raw = zlib.decompress(f.read())

        # Read object type
        x = raw.find(b' ')
        fmt = raw[0:x]

        # Read and validate object size
        y = raw.find(b'\x00', x)
        size = int(raw[x:y].decode("ascii"))

        if size != len(raw)-y-1:
            raise Exception(
                "Malformed object {0}: bad length".format(
                    sha
                )
            )
        # Pick a constructor
        if   fmt==b'commit' : c=GitCommit
        elif fmt==b'tree'   : c=GitTree
        elif fmt==b'tag'    : c=GitTag
        elif fmt==b'blob'   : c=GitBlob
        else:
            raise Exception(
                "Unknown type %s for object %s".format(
                    fmt.decode("ascii"), sha
                )
            )

        # Call constructor and return object
        return c(repo, raw[y+1:])

def object_find(repo, name, fmt=None, follow=True):
    # TODO: Implement function
    return name

def object_write(obj, actually_write=True):
    data = obj.serialize()

    # Add header
    result = obj.fmt + b' ' + str(len(data)).encode() + b'\x00' + data
    
    # Compute Hash
    sha = hashlib.sha1(result).hexdigest()

    if actually_write:
        path = repo_file(obj.repo, "objects", sha[0:2],
            sha[2:], mkdir=actually_write)

        with open(path, "wb") as f:
            f.write(zlib.compress(result))

    return sha

def object_hash(fd, fmt, repo=None):
    data = fd.read()

    # Choose constructor depending on
    # object type found in header.
    if   fmt==b'commit' : obj=GitCommit(repo, data)
    elif fmt==b'tree'   : obj=GitTree(repo, data)
    elif fmt==b'tag'    : obj=GitTag(repo, data)
    elif fmt==b'blob'   : obj=GitBlob(repo, data)
    else:
        raise Exception("Unknown type %s!" % fmt)

    return object_write(obj, repo)

# }}

# Commit Parsing {{

# A simple commit parser
# KVLM is for Key-Value List with Message
def kvlm_parse(raw, start=0, dct=None):
    if not dct:
        dct = collections.OrderedDict()
        # Note: Do NOT declare it as dct=OrderedDict()
        # or all calls to the functions will endlessly
        # grow the same dict.

    # Search for the next space and next newline
    spc = raw.find(b' ', start)
    nl = raw.find(b'\n', start)

    # If space appears before newline, we have a keyword.

    # Base case
    # =========
    # If newline appears first (or there's no space at all,
    # in which case find returns -1), we assume a 
    # blank line.  A blank line means the remainder of 
    # the data is the message.
    if (spc < 0) or (nl < spc):
        assert(nl == start)
        dct[b''] = raw[start+1:]
        return dct

    # Recursive case
    # ==============
    # we read a key-value pair and recurse for the next.
    key = raw[start:spc]

    # Find the end of the value. Continuation lines 
    # begin with a space, so we loop until we find a "\n" 
    # not followed by a space.
    end = start
    while True:
        end = raw.find(b'\n', end+1)
        if raw[end+1] != ord(' '): break

    # Grab the value
    # Also, drop the leading space on continuation lines
    value = raw[spc+1:end].replace(b'\n ', b'\n')

    # Don't overwrite existing data contents
    if key in dct:
        if type(dct[key]) == list:
            dct[key].append(value)
        else:
            dct[key] = [ dct[key], value ]
    else:
        dct[key]=value

    return kvlm_parse(raw, start=end+1, dct=dct)

# Serialises Commit objects
def kvlm_serialize(kvlm):
    ret = b''

    # Output fields
    for k in kvlm.keys():
        # Skip the message itself
        if k == b'': continue
        val = kvlm[k]
        # Normalize to a list
        if type(val) != list:
            val = [ val ]

        for v in val:
            ret += k + b' ' + (v.replace(b'\n', b'\n ')) + b'\n'

    # Append message
    ret += b'\n' + kvlm[b'']

    return ret

# }}

# Tree Parsing {{

# Parsing a single Tree Node
def tree_parse_one(raw, start=0):
    # Find the space terminator of the mode
    x = raw.find(b' ', start)
    assert(x-start == 5 or x-start==6)

    # Read the mode
    mode = raw[start:x]

    # Find the NULL terminator of the path
    y = raw.find(b'\x00', x)
    # and read the path
    path = raw[x+1:y]

    # Read the SHA and convert to an hex string
    sha = hex(
        int.from_bytes(raw[y+1:y+21], "big"))[2:] 
        # hex() adds 0x in front, we don't want that.

    return y+21, GitTreeLeaf(mode, path, sha)

# Calls the previous parser in a loop for chained trees
def tree_parse(raw):
    pos = 0
    max = len(raw)
    ret = list()
    while pos < max:
        pos, data = tree_parse_one(raw, pos)
        ret.append(data)

    return ret

# Tree Serializer
def tree_serialize(obj):
    ret = b''
    for i in obj.items:
        ret += i.mode
        ret += b' '
        ret += i.path
        ret += b'\x00'
        sha = int(i.sha, 16)
        ret += sha.to_bytes(20, byteorder="big")
    return ret

# }}

# For Resolving References {{

def ref_resolve(repo, ref):
    with open(repo_file(repo, ref), 'r') as fp:
        data = fp.read()[:-1]
        # Drop final \n ^^^^^
    if data.startswith("ref: "):
        return ref_resolve(repo, data[5:])
    else:
        return data

def ref_list(repo, path=None):
    if not path:
        path = repo_dir(repo, "refs")
    ret = collections.OrderedDict()
    # Git shows refs sorted.  To do the same, we use
    # an OrderedDict and sort the output of listdir
    for f in sorted(os.listdir(path)):
        can = os.path.join(path, f)
        if os.path.isdir(can):
            ret[f] = ref_list(repo, can)
        else:
            ret[f] = ref_resolve(repo, can)

    return ret

# }}

# }}}

# Bridge functions (used in main()) {{{

# Init {{

def cmd_init(args):
    repo_create(args.path)

# }}

# Cat-File {{

def cmd_cat_file(args):
    repo = repo_find()
    cat_file(repo, args.object, fmt=args.type.encode())

def cat_file(repo, obj, fmt=None):
    obj = object_read(repo, object_find(repo, obj, fmt=fmt))
    sys.stdout.buffer.write(obj.serialize())

# }}

# Hash-Object {{

def cmd_hash_object(args):
    if args.write:
        repo = GitRepository(".")
    else:
        repo = None

    with open(args.path, "rb") as fd:
        sha = object_hash(fd, args.type.encode(), repo)
        print(sha)

# }}

# Log {{

def cmd_log(args):
    repo = repo_find()

    print("digraph wyaglog{")
    log_graphviz(repo, object_find(repo, args.commit), set())
    print("}")

def log_graphviz(repo, sha, seen):

    if sha in seen:
        return
    seen.add(sha)

    commit = object_read(repo, sha)
    assert (commit.fmt==b'commit')

    if not b'parent' in commit.kvlm.keys():
        # Base case: the initial commit.
        return

    parents = commit.kvlm[b'parent']

    if type(parents) != list:
        parents = [ parents ]

    for p in parents:
        p = p.decode("ascii")
        print ("c_{0} -> c_{1};".format(sha, p))
        log_graphviz(repo, p, seen)

# }}

# Checkout {{

def cmd_checkout(args):
    repo = repo_find()

    obj = object_read(repo, object_find(repo, args.commit))

    # If the object is a commit, we grab its tree
    if obj.fmt == b'commit':
        obj = object_read(repo, obj.kvlm[b'tree'].decode("ascii"))

    # Verify that path is an empty directory
    if os.path.exists(args.path):
        if not os.path.isdir(args.path):
            raise Exception("Not a directory {0}!".format(args.path))
        if os.listdir(args.path):
            raise Exception("Not empty {0}!".format(args.path))
    else:
        os.makedirs(args.path)

    tree_checkout(repo, obj, os.path.realpath(args.path).encode())

def tree_checkout(repo, tree, path):
    for item in tree.items:
        obj = object_read(repo, item.sha)
        dest = os.path.join(path, item.path)

        if obj.fmt == b'tree':
            os.mkdir(dest)
            tree_checkout(repo, obj, dest)
        elif obj.fmt == b'blob':
            with open(dest, 'wb') as f:
                f.write(obj.blobdata)

# }}

# Show-Ref {{

def cmd_show_ref(args):
    repo = repo_find()
    refs = ref_list(repo)
    show_ref(repo, refs, prefix="refs")

def show_ref(repo, refs, with_hash=True, prefix=""):
    for k, v in refs.items():
        if type(v) == str:
            print ("{0}{1}{2}".format(
                v + " " if with_hash else "",
                prefix + "/" if prefix else "",
                k))
        else:
            show_ref(repo, v, 
                with_hash=with_hash, 
                prefix="{0}{1}{2}".format(
                    prefix, "/" if prefix else "", k)
            )

# }}

# }}}

# Main Function {{{

def main(argv=sys.argv[1:]):
    # Get arguments
    args = argparser.parse_args(argv)

    # Call appropriate function based on command
    if   args.command == "add"        : cmd_add(args)
    elif args.command == "cat-file"   : cmd_cat_file(args)
    elif args.command == "checkout"   : cmd_checkout(args)
    elif args.command == "commit"     : cmd_commit(args)
    elif args.command == "hash-object": cmd_hash_obj(args)
    elif args.command == "init"       : cmd_init(args)
    elif args.command == "log"        : cmd_log(args)
    elif args.command == "ls-tree"    : cmd_ls_tree(args)
    elif args.command == "merge"      : cmd_merge(args)
    elif args.command == "rebase"     : cmd_rebase(args)
    elif args.command == "rev-parse"  : cmd_rev_parse(args)
    elif args.command == "rm"         : cmd_rm(args)
    elif args.command == "show-ref"   : cmd_show_ref(args)
    elif args.command == "tag"        : cmd_tag(args)

# }}}
