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

# Add init command argument
argsp = argsubparsers.add_parser(
    "init", help="Initialize a new, empty repository."
)
argsp.add_argument("path",
                   metavar="directory",
                   nargs="?",
                   default=".",
                   help="Where to create the repository.")

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

def GitBlob(GitObject):
    fmt = b'blob'

    def serialize(self):
        return self.blobdata

    def deserialize(self, data):
        self.blobdata = data

# }}}

# Helper Functions {{{

# For file Paths {{

def repo_path(repo, *path):
    # Compute the path under repo's gitdir
    return os.path.join(repo.gitdir, *path)

def repo_file(repo, *path, mkdir=False):
    # Same as repo path but can create dirname(*path) if
    # absent
    if repo_dir(repo, *path, mkdir=mkdir):
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
    result = obj.fmt + b' ' + str(len(data)).encode()
        + b'\x00' + data
    
    # Compute Hash
    sha = hashlib.sha1(result).hexdigest()

    if actually_write:
        path = repo_file(obj.repo, "objects", sha[0:2],
            sha[2:], mkdir=actually_write)

        with open(path, "wb") as f:
            f.write(zlib.compress(result))

    return sha

# }}

# }}}

# Bridge functions (used in main()) {{{

def cmd_init(args):
    repo_create(args.path)

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
