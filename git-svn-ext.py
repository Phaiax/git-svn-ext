#!/d/bin/python2/python-2.7.12.amd64/python.exe

import sys
import os
import posixpath
import re
import subprocess
import argparse
import shutil

DEBUG = False
__CSL = None

# monkey patch os to include symlink for windows
if not hasattr(os, "symlink"):
    def symlink_nt(source, link_name):
        '''symlink(source, link_name)
           Creates a symbolic link pointing to source named link_name'''
        # source ist bei junctions nicht mehr relativ zum linkdir, sondern zu aktuellem verzeichnis
        # goto_root() wurde aufgerufen, d.h. wir sind auf jeden fall im git root
        #   Verbindung erstellt fuer linkname:tools\svnShellScripts <<===>> src:..\.git_externals\tools\svnShellScripts

        (link_dir, link) = os.path.split(link_name)
        source_from_gitroot = os.path.join(link_dir, source)
        
        run_command('mklink /D /J {0} {1}'.format(link_name, source_from_gitroot))
        return
        
        global __CSL
        if __CSL is None:
            import ctypes
            csl = ctypes.windll.kernel32.CreateSymbolicLinkW
            csl.argtypes = (ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint32)
            csl.restype = ctypes.c_ubyte
            __CSL = csl
        flags = 1
        if __CSL(link_name, source, flags) == 0:
            raise ctypes.WinError()

    if os.name == 'nt':
        os.symlink = symlink_nt

def get_output(command, include_stderr=True):
    """Get the output of a command, optionally ignoring stderr"""
    if include_stderr:
        stderr=subprocess.STDOUT
    else:
        # Pipe stderr, but we ignore it
        stderr=subprocess.PIPE

    proc = subprocess.Popen(command, shell=True, stderr=stderr, stdout=subprocess.PIPE)

    output = proc.communicate()[0].rstrip('\n')
    return output

def get_output_lines(command, include_stderr=True):
    return get_output(command, include_stderr).split('\n')

def file_contains_line(filename, line):
    with open(filename, 'r') as file:
        return line in file.readlines()
    return False

def append_line_if_not_included(filename, line):
    if not file_contains_line(filename, line):
        with open(filename, 'a') as file:
            file.write(line + '\n')

def remove_line_if_included(filename, line):
    data = []
    with open(filename, 'r') as file:
        data = file.readlines()

    included = any(map(lambda l: line in l, data))
    if included:
        data = [l for l in data if not line in l]
        with open(filename, 'w') as file:
            file.write(''.join(data))

def create_dir_if_not_exist(dir):
    """helper to create a directory if it doesn't exist"""
    if not os.path.exists(dir):
        os.makedirs(dir)

def run_command(command, echo=True):
    if echo:
        print command
    os.system(command)

def info(msg, *args):
    print(msg.format(*args))

def debug(msg, *args):
    if DEBUG: print("debug: " + msg.format(*args))

def error(msg, *args):
    print(red("error: ") + msg.format(*args))

def fail(msg, *args):
    error(msg, *args)
    sys.exit(1)

def red(msg, *args):
    return Color.colorize(Color.RED, msg, *args)

def green(msg, *args):
    return Color.colorize(Color.GREEN, msg, *args)

def yellow(msg, *args):
    return Color.colorize(Color.YELLOW, msg, *args)

def blue(msg, *args):
    return Color.colorize(Color.BLUE, msg, *args)

def purple(msg, *args):
    return Color.colorize(Color.PURPLE, msg, *args)

def white(msg, *args):
    return Color.colorize(Color.WHITE, msg, *args)

class Color:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    WHITE = '\033[97m'
    END = '\033[0m'

    @classmethod
    def disable(cls):
        cls.RED = ''
        cls.GREEN = ''
        cls.YELLOW = ''
        cls.BLUE = ''
        cls.PURPLE = ''
        cls.WHITE = ''
        cls.END = ''

    @classmethod
    def colorize(cls, color, msg, *args):
        return "{0}{1}{2}".format(color, msg.format(*args), cls.END)

class Git:
    LocalExclude = '.git/info/exclude'

    @staticmethod
    def get_root_relative():
        """Get relative directory to the base of the checkout"""
        return get_output('git rev-parse --show-cdup')

    @staticmethod
    def get_root_ext_relative():
        current_dir = os.getcwd()
        rel_path = ""
        max_depth = 10
        while max_depth > 0:
            if os.path.exists(GitSvnExternal.ExternalsDir):
                os.chdir(current_dir)
                return rel_path
            rel_path += "../"
            os.chdir("..")
            max_depth -= 1
        os.chdir(current_dir)
        return ""

    @classmethod
    def goto_root(cls):
        git_root = cls.get_root_relative()
        if git_root:
            info("changing to git root: {0}", git_root)
            os.chdir(git_root)

    @classmethod
    def goto_root_ext(cls):
        git_root = cls.get_root_ext_relative()
        if git_root:
            info("changing to git root: {0}", git_root)
            os.chdir(git_root)

    @staticmethod
    def has_svn_ref():
        return get_output('git show-ref git-svn') != ""

    @classmethod
    def find_uncommitted(cls):
        if not cls.has_svn_ref():
            return []
        """Given the name of the remote branch, show log of the commits."""
        commits = get_output_lines('git log --pretty="format:%h %s" git-svn..HEAD')
        return filter(lambda c: len(c) > 0, commits)

    @staticmethod
    def _format_revision_arg(revision):
        return "--revision BASE:{0}".format(revision) if revision else ""

    @classmethod
    def update_from_svn(cls, revision=""):
        run_command('git svn fetch {0}'.format(cls._format_revision_arg(revision)))
        if revision:
            commit_id = get_output('git svn find-rev --before r{0}'.format(revision))
            run_command('git checkout {0}'.format(commit_id))
        else:	
            run_command('git svn rebase --local')

    @classmethod
    def clone_from_svn(cls, remote_url, local_url, revision):
        run_command('git svn clone {0} {1} {2}'.format(cls._format_revision_arg(revision), remote_url, local_url))

    @classmethod
    def ignore_path(cls, path):
        append_line_if_not_included(cls.LocalExclude, path)

    @classmethod
    def not_ignore_path(cls, path):
        remove_line_if_included(cls.LocalExclude, path)

    @staticmethod
    def is_dirty():
        return get_output('git status --porcelain') != ""

    @staticmethod
    def status():
        run_command('git status')

    @staticmethod
    def _get_svn_externals():
        """returns a hash of string->array where the key is the location
        in the source of the external property, and the array is the list
        of externals"""

        results = {}

        checkout_dir = ""
        external_dir = ""
        output = get_output_lines('git svn show-externals', include_stderr=False)
        # /MavSimulation/src/mav/src/-r 227 /MAV_MC_nc_stm32/trunk/source microcontroller
        # Pathinmasterrepository     rev    pathtoexternalrep             shouldbelinkedtothisfolderinthe<Pathinmasterrepository>
        for line in output:

            match = re.search(r"^# (.*)", line)
            if match:
                # the checkout dir is a relative dir, but starts with a slash
                checkout_dir = match.group(1)
                external_dir = checkout_dir[1:]
                continue

            if not match and line:
                # start array
                if not results.has_key(external_dir):
                    results[external_dir] = []

                # NOTE: git-svn prepends the external with checkout_dir -> undo that
                line = re.sub("^" + checkout_dir, "", line).strip()
                if line:
                    results[external_dir].append(line)



        debug("externals: {0}", str(results))
        return results


    @staticmethod
    def svn_info():
        return GitSvnInfo(get_output_lines('git svn info'))

    @classmethod
    def get_externals(cls, pre14=False):
        result = []
        git_svn_info = cls.svn_info()

        for src_dir, externals in cls._get_svn_externals().items():
            for external in externals:
                debug("source dir: {0}, external: {1}", src_dir, external)

                svn_ext = SvnExternal(src_dir, external, git_svn_info, pre14)
                git_svn_ext = GitSvnExternal.fromSvnExternal(svn_ext)

                # Allow exclusion of externals
                if not git_svn_ext.is_excluded():
                    result.append(git_svn_ext)
                else:
                    info("excluding svn external: {0}", git_svn_ext.name())

        return result

    @staticmethod
    def get_cloned_externals():
        cloned_externals_dir = GitSvnExternal.ExternalsDir

        externals = []
        for root, dirnames, _ in os.walk(cloned_externals_dir):
            if '.git' in dirnames:
                dirnames[:] = [] # Don't recurse any further
                externals.append(GitSvnExternal.fromClonedDirectory(root))

        return externals

class GitSvnInfo:
    def __init__(self, svn_info):
        """Parse 'git svn info'"""
        self.info = {}
        for line in svn_info:
            match = re.search("(.+): (.+)", line)
            if match:
                self.info[match.group(1)] = match.group(2)

    def path(self):
        return self.info["Path"]

    def url(self):
        return self.info["URL"]

    def repository_root(self):
        return self.info["Repository Root"]

    def repository_uuid(self):
        return self.info["Repository UUID"]

    def revision(self):
        return self.info["Revision"]

# There are a lot of different formats
# http://svnbook.red-bean.com/en/1.7/svn.advanced.externals.html
#
# >=1.6 formats:
#    ^/sounds third-party/sounds
#    /skinproj@148 third-party/skins
#    //svn.example.com/skin-maker@21 third-party/skins/toolkit
#    ../skinproj@148 third-party/skins
#  file format:
#    ^/trunk/bikeshed/blue.html@40 green.html
class SvnExternal:
    """Represent and parse svn externals from a string
    NOTE: must be in the directory where the external is!
    because 'git svn info' is queried as part of this

    svn_info is passed in for ease of testing
    """
    def __init__(self, external_dir, external_string, svn_info, pre14=False):
        self.dir = ""
        self.url = ""
        self.rev = ""

        prefix_revision = r"(-r\s*(?P<rev1>\d+))?"
        url = r"(?P<url>.+)"
        suffix_revision = r"(@(?P<rev2>\d+))?"
        path = r"(?P<dir>.+)"
        external_pattern_aft14 = re.compile(r"{0}\s*{1}{2}\s+{3}".format(prefix_revision, url, suffix_revision, path))
        external_pattern_pre14 = re.compile(r"^{0}\s+{1}\s*{2}$".format(path, prefix_revision, url))
        external_pattern = external_pattern_aft14 if not pre14 else external_pattern_pre14

        matched_pattern = external_pattern.search(external_string)
        if not matched_pattern:
            fail("unable to parse external: {0}", external_string)

        matches = matched_pattern.groupdict()
        debug("matches: {0}", str(matches))

        self.dir = posixpath.join(external_dir, matches["dir"].strip())
        self.url = matches["url"].strip()

        if matches.get('rev1', None):
            self.rev = matches["rev1"].strip()
        elif matches.get('rev2', None):
            self.rev = matches["rev2"].strip()

        self._post_process(svn_info)

    def _post_process(self, svn_info):
        debug("url before post process: {0}", self.url)

        url = self.url
        scheme_pattern = r"(?P<scheme>(http|https|svn|svn\+ssh|file)://)"
        server_pattern = r"(?P<server>{0}[^/]+)?/?".format(scheme_pattern)
        full_url_pattern = r"{0}(?P<path>.+)".format(server_pattern)

        if url.startswith("^/"):
            # Relative to the repository root
            url = posixpath.join(svn_info.repository_root(), url[2:])
        elif url.startswith("//"):
            # Relative to the repository URL scheme
            scheme = re.search(scheme_pattern, svn_info.url()).group("scheme")
            url = scheme + url[2:]
        elif url.startswith("/"):
            # Relative to the repository server
            server = re.search(server_pattern, svn_info.url()).group("server")
            url = server + url
        elif url.startswith("../"):
            # Relative to the repository URL
            url = posixpath.join(svn_info.url(), url)

        debug("url after post process: {0}", url)

        # Normalize the path (since .. can also appear in the middle)
        # split apart because normpath turns "//" into "/"
        matches = re.search(full_url_pattern, url)

        server = matches.group("server")
        if not server:
            server = svn_info.repository_root()
        path = posixpath.normpath(matches.group("path"))

        self.url = posixpath.join(server, path)
        debug("url after normalization and optional scheme change: {0}", self.url)


######## Class to represent git-svn External ##########

class GitSvnExternal:
    """Class to hold and manipulate data about an svn external

    local_url: directory in the source that contains the svn:external property
    local_dir   : the location relative to local_url where the external source will be
    remote_url  : svn external
    revision    : optional pinned revision
    """

    ExternalsDir = ".git_externals"
    ExcludesFile = ".git_external_excludes"

    def __init__(self, local_url, local_dir, remote_url, revision):
        self.local_url = local_url
        self.local_dir = local_dir
        self.remote_url = remote_url
        self.revision = revision

    @classmethod
    def fromSvnExternal(cls, svn_external):
        local_dir = svn_external.dir
        local_url = posixpath.join(cls.ExternalsDir, local_dir)
        return cls(local_url, local_dir, svn_external.url, svn_external.rev)

    @classmethod
    def fromClonedDirectory(cls, path):
        local_url = path
        local_dir = re.sub(".*{0}\\\\".format(cls.ExternalsDir ), "", path)
        return cls(local_url, local_dir, "", "")

    def name(self):
        return self.local_dir

    def printMessage(self, msg):
        info("{0:<30}{1}", white(">>> {0}: ", self.name()), msg)

    def is_excluded(self):
        """return True if excluding this external"""
        if os.path.exists(self.ExcludesFile):
            return file_contains_line(self.ExcludesFile, self.local_dir)
        return False

    def is_cloned(self):
        local_git_dir = os.path.join(self.local_url, ".git")
        return os.path.isdir(local_git_dir)

    def check_is_cloned(self):
        if not self.is_cloned():
            self.printMessage(red("external is not cloned"))
            return False
        return True

    def _create_link(self):
        """create the link to the external"""
        if os.path.lexists(os.path.normpath(self.local_dir)):
            debug("removing symlink: {0}", os.path.normpath(self.local_dir))
            os.remove(os.path.normpath(self.local_dir))

        # construct relative link
        current_dir = os.getcwd()

        dirname = os.path.dirname(os.path.normpath(self.local_dir))
        if dirname:
            create_dir_if_not_exist(dirname)
            os.chdir(dirname)
        rel = Git.get_root_relative()

        os.chdir(current_dir)

        source = rel + self.local_url
        debug("creating symlink {0} => {1}", os.path.normpath(source), os.path.normpath(self.local_dir))
        os.symlink(os.path.normpath(source), os.path.normpath(self.local_dir))

    def _update_excludes(self):
        """add symlink to the git excludes path"""
        Git.ignore_path(self.ExternalsDir)
        Git.ignore_path(self.local_dir)

    """do the actual cloning"""
    def clone(self):
        if self.is_excluded():
            self.printMessage(blue("skipping excluded external"))
            return

        if self.is_cloned():
            self.printMessage(green("skipping existing external"))
            return

        Git.clone_from_svn(self.remote_url, self.local_url, self.revision)
        self._create_link()
        self._update_excludes()

    def update(self):
        if not self.check_is_cloned():
            return

        current_dir = os.getcwd()
        os.chdir(self.local_url)

        print(white(">>> {0}", self.name()))
        Git.update_from_svn(self.revision)

        os.chdir(current_dir)

    def check(self):
        current_dir = os.getcwd()
        os.chdir(self.local_url)

        dirty = Git.is_dirty()
        commits = Git.find_uncommitted()

        if dirty or commits:
            print(white(">>>>>>>>>>>>>>>> {0} <<<<<<<<<<<<<<<<", self.name()))

            if dirty:
                Git.status()

            if commits:
                print "Possible unpushed commits:"
                print(blue("\n".join(commits)))
        else:
            self.printMessage(green("no changes found"))

        os.chdir(current_dir)

    def execute(self, command):
        if not self.check_is_cloned():
            return

        current_dir = os.getcwd()
        os.chdir(self.local_url)

        self.printMessage(command)
        run_command(command, False)

        os.chdir(current_dir)

    def askRemove(self):
        self.printMessage(yellow("unknown cloned external: {0}", self.name()))

        user_input = "X"
        while not user_input in ["", "y", "n"]:
            user_input = raw_input('delete this cloned external [Yn]: ').lower()

        if user_input == "n":
            return

        shutil.rmtree(self.local_url)
        if os.path.lexists(self.local_dir):
            os.remove(self.local_dir)
        Git.not_ignore_path(self.local_dir)

def clone(args):
    Git.goto_root()
    externals = Git.get_externals(pre14=args.pre14)

    if not externals:
        fail("no svn externals found")

    for external in externals:
        external.clone()

    # search for cloned externals which are not an svn external any more
    local_urls = [os.path.normpath(external.local_url) for external in externals]
    cloned_externals = Git.get_cloned_externals()
    for cloned_external in cloned_externals:
        if not os.path.normpath(cloned_external.local_url) in local_urls:
            cloned_external.askRemove()

def performAction(action, *args, **kw):
    Git.goto_root()

    # We are not in toplevel, perform for single instance
    #if Git.get_root_ext_relative():
    #    external = GitSvnExternal.fromClonedDirectory(os.getcwd())
    #    getattr(external, action)()
    #    return

    externals = Git.get_externals(pre14=kw.get("pre14", False))
    if not externals:
        fail("no cloned svn externals found")

    for external in externals:
        getattr(external, action)(*args)

def update(args):
    performAction('update', **vars(args))

def check(args):
    performAction('check', **vars(args))

def execute(args):
    performAction('execute', args.command, **vars(args))

def main():
    if sys.platform == 'win32':
        Color.disable()

    parser = argparse.ArgumentParser(
        prog='git-svn-ext',
        epilog="Note: externals may be ignored if listed in {0}".format(GitSvnExternal.ExcludesFile)
    )
    parser.add_argument('--version', action='version', version='%(prog)s 1.0.0')
    parser.add_argument('-p', '--pre14', action='store_true', default=False)
    parser.add_argument('-d', '--dbg', action='store_true', default=False)
    subparsers = parser.add_subparsers(help='available commands')

    parser_clone = subparsers.add_parser('clone')
    parser_clone.set_defaults(func=clone)

    parser_update = subparsers.add_parser('update')
    parser_update.set_defaults(func=update)

    parser_check = subparsers.add_parser('check')
    parser_check.set_defaults(func=check)

    parser_for_all = subparsers.add_parser('execute')
    parser_for_all.set_defaults(func=execute)
    parser_for_all.add_argument('command', help='a command to execute for each external')

    args = parser.parse_args()
    global DEBUG
    DEBUG=args.dbg
    args.func(args)

if __name__ == '__main__':
    main()
