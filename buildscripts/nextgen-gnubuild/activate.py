#!/usr/bin/env python3

# Script for activation of next-generation GNU autotools build scripts.
#
# The new versions will be backward incompatible, so keep the existing scripts
# intact until the new version is stable. Users of existing build scripts are
# not affected.
#
# All modifications and replacements are in *.nextgen, which are copied into
# their final location by this script. MD5 sums of legacy scripts are included
# in *.nextgen, so that chagnes made to legacy scripts do not get missed.
#
#
# Usage:
#
# activate.py --activate
# -> scan all *.nextgen files and copy them to final location, removing the
#    corresponding legacy files
#
# activate.py --reactivate
# -> scan all *.nextgen files and copy them to final location, without
#    performing removal of legacy files (and without checking MD5)
#
# activate.py --deactivate
# -> scan all *.nextgen files and revert the effect of --activate, using 'git
#    checkout' to reinstate deleted legacy files.
#
# activate.py --sum FILE1 FILE2 ...
# -> compute MD5 sums of files and print in *.nextgen header format
#
# activate.py --ngize FILE... [--header HEADER_FILE]
# -> create a .nextgen shadow for FILEs, optionally prepending HEADER_FILE
#
#
# Header format for *.nextgen:
#
# %nextgen_build_filename FINAL_FILENAME
# %nextgen_build_filemode OCTAL_DIGIT
# %nextgen_build_replaces LEGACY_FILENAME MD5SUM
#
# All directives are optional (but at least one is required). The filemode is a
# single octal digit, usually 6 or 7. The default is 6. (Recall that git only
# stores a single executable bit. The current umask is applied to the given
# mode.)
#
# Author: Mark Tsuchida, March 2014

import argparse
import collections
import hashlib
import os, os.path
import re
import shutil
import subprocess
import sys


def activate(initial=True):
    all_deletes, all_renames = [], []
    for nextgen_filename in iterate_nextgen_files():
        print("reading " + nextgen_filename)
        hdr = get_nextgen_header(nextgen_filename)
        deletes, renames = process_nextgen(hdr, initial)
        all_deletes.extend(deletes)
        all_renames.extend(renames)

    dupnames = list(x for x, y in collections.Counter(all_deletes).items() if y > 1)
    if dupnames:
        print("duplicate %nextgen_build_replaces")
        print("duplicated old filenames = ", ", ".join(dupnames))
        sys.exit(1)

    print("finished reading info; now execute")

    if all_deletes:
        print("delete files: " + " ".join(all_deletes))
        for filename in all_deletes:
            os.unlink(filename)

    umask = os.umask(0o777); os.umask(umask)
    for src, dst, mode in all_renames:
        if dst is not None:
            if (initial or
                not os.path.exists(dst) or
                os.stat(src).st_mtime > os.stat(dst).st_mtime):
                masked_mode = mode & ~umask
                print("copy", src, "->", dst, "(0{:03o})".format(masked_mode))
                shutil.copyfile(src, dst)
                os.chmod(dst, masked_mode)
            else:
                print("up to date: " + dst + " (from " + src + ")")
        else:
            print("no new file from " + src)


def deactivate(no_git=False):
    all_deleted, all_renamed = [], []
    for nextgen_filename in iterate_nextgen_files():
        print("reading " + nextgen_filename)
        hdr = get_nextgen_header(nextgen_filename)
        deleted, renamed = process_nextgen(hdr, True, False)
        all_deleted.extend(deleted)
        all_renamed.extend(renamed)

    print("finished reading info; now execute")

    for src, dst, mode in all_renamed:
        if dst is not None:
            print("remove " + dst + " (from " + src + ")")
            try:
                os.unlink(dst)
            except:
                pass

    is_git_svn = not os.path.exists(".svn")
    if is_git_svn:
        for deleted in all_deleted:
            print("reinstate " + deleted)
            # Change to the containing directory so that split repository for
            # SecretDeviceAdapters works.
            subprocess.call("cd '{}'; git checkout '{}'".
                            format(*os.path.split(deleted)),
                            shell=True)
    else:
        # One-by-one 'svn revert' is way too slow.
        main, secrets = [], []
        for deleted in all_deleted:
            if "SecretDeviceAdapters/" in deleted:
                secrets.append(os.path.relpath(deleted, "./SecretDeviceAdapters"))
            else:
                main.append(deleted)
        subprocess.call(["svn", "revert"] + main)
        oldcwd = os.getcwd()
        os.chdir("./SecretDeviceAdapters")
        subprocess.call(["svn", "revert"] + secrets)
        os.chdir(oldcwd)


def iterate_nextgen_files():
    for root, dirs, files in os.walk(".", followlinks=True):
        for name in files:
            if name.endswith(".nextgen"):
                yield os.path.join(root, name)


class Header:

    def __init__(self, filename):
        self.filename = filename
        self.replaced = {}
        self.rename_to = None
        # Default mode before applying umask
        self.file_mode = 0o666

    def set_rename_to(self, filename):
        if self.rename_to is not None:
            print("duplicate %nextgen_filename: " + filename)
            sys.exit(1)
        self.rename_to = filename

    def set_file_mode(self, mode_octal_digit):
        p = mode_octal_digit
        self.file_mode = p + 8 * (p + 8 * p)

    def add_replaced(self, old_filename, md5):
        if old_filename in self.replaced:
            print("duplicate %nextgen_build_replaces: " + old_filename)
            sys.exit(1)
        self.replaced[old_filename] = md5


def get_nextgen_header(filename):
    hdr = Header(filename)
    found_directive = False
    with open(filename) as f:
        for line in f:
            m = re.match(r"#\s+%nextgen_build_([a-z]+)\s*=\s*(\S.*)$", line.strip())
            if m:
                found_directive = True
                if m.group(1) == "filename":
                    hdr.set_rename_to(m.group(2).strip())
                    rename_to = m.group(2).strip()
                elif m.group(1) == "filemode":
                    hdr.set_file_mode(int(m.group(2).strip()))
                elif m.group(1) == "replaces":
                    old_filename, md5 = m.group(2).split()
                    hdr.add_replaced(old_filename, md5)
                else:
                    print("Unknown directive:", line.strip())
                    sys.exit(1)
    if not found_directive:
        print("No valid directives in file:", filename)
        sys.exit(1)
    return hdr


def process_nextgen(hdr, do_removal=True, check_removal=None):
    if check_removal is None:
        check_removal = do_removal
    dirname = os.path.dirname(hdr.filename)
    deletes = []
    if do_removal:
        for old_filename, old_md5 in hdr.replaced.items():
            old_path = os.path.join(dirname, old_filename)
            if check_removal and get_md5(old_path) != old_md5:
                print("MD5 does not match: " + old_path +
                    " (to be replaced by: " + hdr.filename + ")")
                sys.exit(1)
            deletes.append(old_path)
    new_path = os.path.join(dirname, hdr.rename_to) if hdr.rename_to else None
    return deletes, [(hdr.filename, new_path, hdr.file_mode)]


def get_md5(filename):
    m = hashlib.md5()
    with open(filename, "rb") as f:
        m.update(f.read())
    return m.hexdigest()


def print_sums(filenames):
    for filename in filenames:
        print("# %nextgen_build_replaces = " + filename + " " +
              get_md5(filename))


def ngize(filename, header=None):
    dirname, basename = os.path.split(filename)
    orig_dir = os.getcwd()
    if dirname:
        os.chdir(dirname)
    try:
        with open(basename + ".nextgen", "w") as f:
            if header is not None:
                with open(header) as h:
                    f.write(h.read())
            print("# %nextgen_build_filename = " + basename, file=f)
            if os.path.exists(basename):
                print("# %nextgen_build_replaces = " + basename + " " +
                      get_md5(basename), file=f)
                print(file=f)
                with  open(basename) as g:
                    f.write(g.read())
    finally:
        os.chdir(orig_dir)


def run():
    p = argparse.ArgumentParser()
    p.add_argument("-a", "--activate", action="store_true")
    p.add_argument("-r", "--reactivate", action="store_true")
    p.add_argument("-d", "--deactivate", action="store_true")
    p.add_argument("-s", "--sum", nargs="+")
    p.add_argument("-n", "--ngize", nargs="+")
    p.add_argument("-H", "--header", nargs=1)
    args = p.parse_args()
    if sum(1 for _ in filter(None, [args.activate, args.reactivate,
                                    args.deactivate, args.sum, args.ngize])) > 1:
        print("multiple verbs not allowed")
        sys.exit(1)
    if args.activate:
        activate()
    elif args.reactivate:
        activate(False)
    elif args.deactivate:
        deactivate()
    elif args.sum:
        print_sums(args.sum)
    elif args.ngize:
        header_filename = args.header[0] if args.header else None
        for filename in args.ngize:
            ngize(filename, header_filename)
    else:
        print("nothing to do")


if __name__ == "__main__":
    run()
