import os
import sys
import argparse
import time
from  argparse import ArgumentParser
import textwrap as _textwrap
import tempfile
import signal
from docker import Client

DOCKER_SOCKET = "unix://var/run/docker.sock"

import inspect
import stimela
from stimela import utils, cargo
from recipe import Recipe

from stimela.utils import stimela_logger

LOG_HOME = os.path.expanduser("~/.stimela")
LOG_IMAGES = LOG_HOME + "/stimela_images.log"
LOG_CONTAINERS = LOG_HOME + "/stimela_containers.log"
LOG_PROCESS = LOG_HOME + "/stimela_process.log"
LOG_CABS = LOG_HOME + "/stimela_cab.log"

BASE = "base simms casa meqtrees lwimager wsclean aoflagger owlcat sourcery".split()
CAB = os.listdir(cargo.CAB_PATH)

USER = os.environ["USER"]

__version__ = "0.1.4"

GLOBALS = {}

class MultilineFormatter(argparse.HelpFormatter):
    def _fill_text(self, text, width, indent):
        text = self._whitespace_matcher.sub(' ', text).strip()
        paragraphs = text.split('|n ')
        multiline_text = ''
        for paragraph in paragraphs:
            formatted_paragraph = _textwrap.fill(paragraph, width, initial_indent=indent, subsequent_indent=indent) + '\n\n'
            multiline_text = multiline_text + formatted_paragraph
        return multiline_text


def register_globals():
    frame = inspect.currentframe().f_back
    frame.f_globals.update(GLOBALS)
    

def build():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg

    parser = ArgumentParser(description='Build executor (a.k.a cab) images')
    args = parser.parse_args()

    # clear old cabs
    img = stimela_logger.Image(LOG_CABS)
    img.clear()

    with Client(base_url=DOCKER_SOCKET) as docker:
    
        for image in CAB:
            path = "{:s}/{:s}".format(cargo.CAB_PATH, image)
            image = "{:s}_cab/{:s}".format(USER, image)
            
            print "Building image", image
            docker.build(dockerfile="Dockerfile", 
                         path=path,
                         rm=False,
                         tag=image)

            img.add(dict(name=image))

    img.write()

        
def cabs():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg

    parser = ArgumentParser(description='List executor (a.k.a cab) images')
    args = parser.parse_args()

    img = stimela_logger.Image(LOG_CABS)
    img.display()


def run():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg

    parser = ArgumentParser(description='Dockerized Radio Interferometric Scripting Framework.\n' 
                                        'Sphesihle Makhathini <sphemakh@gmail.com>')

    add = parser.add_argument

    add("-in", "--input",
            help="Input folder")

    add("-out", "--output", default="output",
            help="Output folder")

    add("-ms", "--msdir",
            help="MS folder. MSs should be placed here. Also, empty MSs will be placed here")

    add("-j", "--ncores", type=int,
            help="Number of cores to when stimela parallesization (stimea.utils.pper function) ")

    add("-L", "--load-from-log", dest="from_log",  metavar="LOG:TAG[:DIR]",
            help="Load base images from stimela log file. The resulting executor images will be tagged 'TAG', and the build contexts will be stored at 'DIR'")

    add("script",
            help="Penthesilea script")

    add("-g", "--globals", metavar="KEY=VALUE[:TYPE]", action="append", default=[],
            help="Global variables to pass to script. The type is assumed to string unless specified")

    args = parser.parse_args()

    tag =  None

    if args.from_log:
        
        destdir = "."

        tmp = args.from_log.split(":")
        if len(tmp) == 2:
            log, tag = tmp
        elif len(tmp) == 3:
            log, tag, destdir = tmp
            if not os.path.exists(destdir):
                os.mkdir(destdir)

        images = set(utils.get_base_images(log))

        for image in images:

            image_, base = image
            path = "{:s}/{:s}".format(STIMELA_CAB_PATH, image_.split("/")[-1])
            dirname, dockerfile = utils.change_Dockerfile_base_image(path, base, image_.split("/")[-1], destdir=destdir)

            # Build executor image
            docker.build("cab/{:s}:{:s}".format(image_.split("/")[-1], tag), 
                       dirname)

    _globals = dict(STIMELA_INPUT=args.input, STIMELA_OUTPUT=args.output, 
                    STIMELA_DATA=cargo.DATA_PATH, STIMELA_MSDIR=args.msdir,
                    CAB_TAG=tag)

    nargs = len(args.globals)

    global GLOBALS 

    if nargs:
        for arg in args.globals:
            if arg.find("=") > 1:
                key, value = arg.split("=")

                try:
                    value, _type = value.split(":")
                except ValueError:
                    _type = "str"
                
                GLOBALS[key] = eval("{:s}('{:s}')".format(_type, value))

    if args.ncores:
        utils.CPUS = args.ncores

    execfile(args.script, _globals)


def pull():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg
    
    parser = ArgumentParser(description='Pull docker stimela base images')

    add = parser.add_argument

    add("-image", action="append", metavar="IMAGE[:TAG]",
            help="Pull base image along with its tag (or version). Can be called multiple times")

    add("-t", "--tag",
            help="Tag")

    args = parser.parse_args()

    if args.image:
        with Client(DOCKER_SOCKET) as docker:
            for image in args.image:
                img = stimela_logger.Image(LOG_IMAGES)

                if not img.find(image):
                    docker.pull(image, stream=True)
                    img.add(dict(name=image, tag=args.tag))
    else:

        base = []
        for cab in CAB:
            image = "{:s}/{:s}".format(cargo.CAB_PATH, cab)
            base.append( utils.get_Dockerfile_base_image(image).split()[-1] )

        base = set(base)

        
        with Client(DOCKER_SOCKET) as docker:

            for image in base:
                img = stimela_logger.Image(LOG_IMAGES)
                
                if not img.find(image) and image!="radioastro/ddfacet":
                    docker.pull(image, stream=True)
                    img.add(dict(name=image, tag=args.tag))

def images():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg
    
    parser = ArgumentParser(description='List all stimela related images.')

    add = parser.add_argument

    add("-c", "--clear", action="store_true",
            help="Clear images log file")

    args = parser.parse_args()

    img = stimela_logger.Image(stimela.LOG_IMAGES)
    img.display()

    if args.clear:
        img.clear()


def containers():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg
    
    parser = ArgumentParser(description='List all active stimela containers.')

    add = parser.add_argument

    add("-c", "--clear", action="store_true",
            help="Clear containers log file")

    args = parser.parse_args()

    conts = stimela_logger.Container(stimela.LOG_CONTAINERS)
    conts.display()
    if args.clear:
        conts.clear()


def ps():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg
    
    parser = ArgumentParser(description='List all running stimela processes')

    add = parser.add_argument
    
    add("-c", "--clear", action="store_true",
            help="Clear Log file")

    args = parser.parse_args()

    procs = stimela_logger.Process(stimela.LOG_PROCESS)
    procs.display()
    if args.clear:
        procs.clear()



def kill():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg
    
    parser = ArgumentParser(description='Gracefully kill stimela process(s).')

    add = parser.add_argument

    add("pid", nargs="*",
            help="Process ID")

    args = parser.parse_args()

    procs = stimela_logger.Process(LOG_PROCESS)

    for pid in map(int, args.pid):

        found = procs.find(pid)
        
        if not found:
            print "Could not find process {0}".format(pid)
            continue

        conts = stimela_logger.Container(LOG_CONTAINERS)
        lines = []

        procs.rm(found)
        procs.write()

        for cont in conts.lines:
            if cont.find(str(pid)) > 0:
                lines.append(cont)
        
        for line in lines:
            cont, _id, utime, _pid, status = line.split()
            if status.find("removed")<0:
                cont_ = docker.Load(None, cont, None, None)
                cont_.started = True
                cont_.stop()
                cont_.rm()

                conts.rm(line)

        conts.write()

        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
                

def main():
    for i, arg in enumerate(sys.argv):
        if (arg[0] == '-') and arg[1].isdigit(): sys.argv[i] = ' ' + arg


    parser = ArgumentParser(description='Stimela: Dockerized Radio Interferometric Scripting Framework. ' 
                                        '|n version {:s} |n Sphesihle Makhathini <sphemakh@gmail.com>'.format(__version__),
                            formatter_class=MultilineFormatter, add_help=False)

    add = parser.add_argument

    add("-h", "--help",  action="store_true",
            help="Print help message and exit")

    add("-v","--version", action='version',
            version='{:s} version {:s}'.format(parser.prog, __version__))

    add("command", nargs="*", metavar="command [options]",
            help="Stimela command to execute. For example, 'stimela help run'")

    options = []
    commands = dict(pull=pull, build=build, run=run, 
                    images=images, cabs=cabs, ps=ps,
                    containers=containers, kill=kill)

    command = "failed"

    for cmd in commands:
       if cmd in sys.argv:
           command = cmd

           index = sys.argv.index(cmd)
           options = sys.argv[index:]
           sys.argv = sys.argv[: index + 1]

    args = parser.parse_args()

    main_help = lambda : args.command and (args.command[0]=="help") and (len(sys.argv)==2)

    if args.help or len(sys.argv)==1 or main_help():
        parser.print_help()

        print ("""
Run a command. These can be:

help    : Prints out a help message about other commands
build   : Build a set of stimela images
pull    : pull a stimela base images
run     : Run a stimela script
images  : List stimela images
cabs    : List active stimela containers
ps      : List running stimela scripts
kill    : Gracefully kill runing stimela process

""")

        sys.exit(0)

    if args.command:
        if args.command[0] == "help":
            sys.argv = sys.argv[1:] + ["-h"]
        else:
            sys.argv = options
        try:
            _cmd = commands[command]
        except KeyError:
            raise KeyError("Command '{:s}' not recognized\n "
                             "Run : 'stimela help' for help".format(args.command))
        _cmd()
