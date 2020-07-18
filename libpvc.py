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
