## Dockerized reduction srcipt framework for radio astronomy
# Sphesihle Makhathini <sphemakh@gmail.com>

import os
import sys
import stimela
import stimela.utils as utils
import stimela.cargo as cargo
import tempfile
import time
import inspect
import platform
from docker import Client
from stimela.utils import stimela_logger

USER = os.environ["USER"]


ekhaya = cargo.__path__[0]

CONFIGS_ = {
    "cab/simms" : "{:s}/configs/simms_params.json".format(ekhaya),
    "cab/simulator" : "{:s}/configs/simulator_params.json".format(ekhaya),
    "cab/lwimager" : "{:s}/configs/imager_params.json".format(ekhaya),
    "cab/wsclean" : "{:s}/configs/imager_params.json".format(ekhaya),
    "cab/casa" : "{:s}/configs/imager_params.json".format(ekhaya),
    "cab/predict" : "{:s}/configs/simulator_params.json".format(ekhaya),
    "cab/calibrator" : "{:s}/configs/calibrator_params.json".format(ekhaya),
    "cab/sourcery" : "{:s}/configs/sourcery_params.json".format(ekhaya),
    "cab/flagms" : "{:s}/configs/flagms_params.json".format(ekhaya),
    "cab/autoflagger" : "{:s}/configs/autoflagger_params.json".format(ekhaya),
    "cab/subtract" : "{:s}/configs/subtract_params.json".format(ekhaya)
}


# docker-py not so good with starting containers
# I use subprocess till they sort their shit out
class DockerError(Exception):
    pass

def start_container(image, name, volumes, environs,log=None, message=None, args=[]):

    volumes = " ".join( ["-v %s"%v for v in volumes] )
    environs = " ".join(["-e %s"%env for env in environs])
    args = " ".join(args)

    cmd = "--name %(name)s %(volumes)s %(environs)s -t %(image)s"%locals()

    try:
        if log:
            log.info("docker run %s"%cmd)
        utils.xrun("docker run", ["-d", cmd], log=log, message=message)
    except SystemError:
        raise DockerError("Failed to start conatiner [%s] from image [%s]"%(name, image))
    return 0


class Recipe(object):

    def __init__(self, name, data=None, configs=None,
                 ms_dir=None, cab_tag=None, mac_os=False,
                 container_logfile=None, shared_memory=1024, verbose=True):

        # LOG recipe
        procs = stimela_logger.Process(stimela.LOG_PROCESS)
        self.verbose = verbose

        date = "{:d}/{:d}/{:d}-{:d}:{:d}:{:d}".format(*time.localtime()[:6])
        procs.add( dict(name=name.replace(" ", "_"), date=date, pid=os.getpid()) )
        procs.write()

        self.stimela_context = inspect.currentframe().f_back.f_globals

        self.name = name
        self.log = utils.logger(0,
                   logfile="log-%s.txt"%name.replace(" ","_").lower())

        self.containers = []
        self.active = None
        self.configs_path = configs
        self.data_path = data or self.stimela_context.get("STIMELA_DATA", None)
        self.docker = Client(stimela.DOCKER_SOCKET)

        if self.data_path:
            pass
        else:
            raise TypeError("'data' option has to be specified")

        self.configs_path_container = "/configs"
        self.stimela_path = os.path.dirname(stimela.__file__)
        self.MAC_OS = platform.system() == "Darwin"
        self.CAB_TAG = cab_tag

        self.ms_dir = ms_dir or self.stimela_context.get("STIMELA_MSDIR", None)
        self.ms_dir = os.path.abspath(self.ms_dir)
        if self.ms_dir:
            if not os.path.exists(self.ms_dir):
                os.mkdir(self.ms_dir)

        home = os.environ["HOME"] + "/.stimela/stimela_containers.log"
        self.CONTAINER_LOGFILE = container_logfile or home


        self.shared_memory = shared_memory


    def add(self, image, name, config,
            input=None, output=None, label="", 
            build_first=False, build_dest=None,
            saveconf=None, add_time_stamp=True, tag=None,
            shared_memory="1gb"):

        input = input or self.stimela_context.get("STIMELA_INPUT", None)
        output = output or self.stimela_context.get("STIMELA_OUTPUT", None)

        input, output = map(os.path.abspath, (input,output))

        cab_tag = self.CAB_TAG or self.stimela_context.get("CAB_TAG", None)
        cab_tag = tag if tag!=None else cab_tag


        if build_first and build_dest:
            self.docker.build(dockerfile="Dockerfile", path=build_dest, tag=image)

        if add_time_stamp:
            name = "%s-%s"%(name, str(time.time()).replace(".", ""))

        # Add tag if its specified
        if cab_tag:
            image = image.split(":")[0]
            image = "{:s}:{:s}".format(image, cab_tag)


        # add standard volumes
        environs = []
        environs.append("MAC_OS=%s"%self.MAC_OS)
        volumes = ["/input", "/output", "/data", "/utils"]

        host_config = {

            self.data_path     :   {
                "bind"     :   "/data",
                "mode"      :   "ro",
            },

            self.stimela_path    :   {
                "bind"      :   "/utils",
                "mode"      :   "ro",
            },
        }

        if self.ms_dir:
            volumes.append(self.ms_dir)
            host_config[self.ms_dir] = {
                "bind" :   "/msdir",
                "mode"  :   "rw",
            }
            environs.append("MSDIR=/msdir")

        if input:
            environs.append("INPUT=/input")

            host_config[input] = {
                "bind"     :   "/input",
                "mode"      :   "ro",
            }

        if output:
            if not os.path.exists(output):
                os.mkdir(output)

            host_config[output] = {
                "bind"     :  "/output",
                "mode"      :   "rw",
            }

            environs.append("OUTPUT=/output")

        # Check if imager image was selected. React accordingly
        if image == "cab/imager":
            if isinstance(config, dict):
                imager = config.get("imager", None)
            else:
                config_ = self.readJson(config)
                imager = config_.get("imager", None)

            imager = imager or "lwimager"

            image = "cab/" + imager
            cont.image = image

        if isinstance(config, dict):
            if not os.path.exists("stimela_configs"):
                os.mkdir("stimela_configs")
            
            config_path = os.path.abspath("stimela_configs")

            if not saveconf:
                saveconf = "%s/%s-%s.json"%(config_path, self.name.replace(" ", "_").lower(), name)

            confname_container = "%s/%s"%(self.configs_path_container, 
                        os.path.basename(saveconf))

            if image.split(":")[0] in CONFIGS_:
                template = utils.readJson(CONFIGS_[image.split(":")[0]])
                template.update(config)
                config = template
            utils.writeJson(saveconf, config)
            config = confname_container
            volumes.append(config_path)

            host_config[config_path] = {
                "bind" :   self.configs_path_container,
                "mode"  :   "ro",
            }
        else:
            volumes.append(config_path)
            host_config[self.configs_path] = {
                "bind" :   self.configs_path_container,
                "mode"  :   "ro",
            }
            config = self.configs_path_container+"/"+config 

        environs.append("CONFIG=%s"%config)

        host_config = self.docker.create_host_config(binds=host_config)
        cont = {
            "name"      :   name,
            "image"     :   "{:s}_{:s}".format(USER, image),
            "volumes"   :   [volumes, host_config],
            "environs"  :   environs,
            "label"     :   label,
            "shm"       :   shared_memory,
        }
        self.containers.append(cont)

        # Record base image info
        dockerfile = cargo.CAB_PATH +"/"+ image.split("/")[-1]
        base_image = utils.get_Dockerfile_base_image(dockerfile)
        self.log.info("<=BASE_IMAGE=> {:s}={:s}".format(image, base_image))


    def run(self, steps=None, log=True):
        """
            Run pipeline
        """

        if isinstance(steps, (list, tuple, set)):
            if isinstance(steps[0], str):
                labels = [ cont.label.split("::")[0] for cont in self.containers]
                containers = []

                for step in steps:
                    try:
                        idx = labels.index(step)
                    except ValueError:
                        raise ValueError("Recipe label ID [{:s}] doesn't exist".format(step))
                    containers.append( self.containers[idx] )
            else:
                containers = [ self.containers[i-1] for i in steps[:len(self.containers)] ]
        else:
            containers = self.containers

        for i, container in enumerate(containers):
            name = container["name"]
            self.active = container
            volumes, host_config = container["volumes"]
#           cont = self.docker.create_container(container["image"],
#                           name=container["name"],
#                           volumes=volumes,
#                           host_config=host_config,
#                           environment=container["environs"],
#                           shared_memory=container["shm"],
#           )
            try:
                shm = int(container["shm"])
                shm = "%dmb"%shm
            except ValueError:
                shm = container["shm"]

            start_container(container["image"], name,
                    volumes=host_config["Binds"],
                    environs=container["environs"], 
                    log=self.log,
                    message="Starting container [%s], from executor image [%s]. Container ID is displayed bellow"%(name, container["image"]), 
                    args=["--shm-size=%s"%shm])
                    
            self.log.info("STEP %d:: %s"%(i, container["label"]))

            cont = self.docker.inspect_container(name)["Id"]
            #self.docker.start(cont)
            container["cont"] = cont
            status = self.docker.inspect_container(cont)["State"]["Status"]
            error = 0
            while status == "running":
                time.sleep(1)
                if self.verbose:
                    print self.docker.logs(cont)

                status = self.docker.inspect_container(cont)["State"]["Status"]
                error = self.docker.inspect_container(cont)["State"]["ExitCode"]

                if error !=0:
                    break

            if error:
                self.log.error("Docker exited with non-zero error code %d. \n %s\n"%(error, 
                                        self.docker.logs(cont),
                                        ))
               
            self.log.info("Container [%s] has finished succeessfuly"%container["name"])
            self.active = None
            if self.verbose:
                self.log.info(self.docker.logs(cont))

        self.log.info("Pipeline [%s] ran successfully. Will now attempt to clean up dead containers "%(self.name))

        self.rm(containers)
        self.log.info("\n[================================DONE==========================]\n \n")

        # Remove from log
        procs = stimela_logger.Process(stimela.LOG_PROCESS)
        procs.rm(os.getpid())
        procs.write()


    def stop(self, log=True):
        """
            Stop all running containers
        """
        for container in self.containers:
            self.docker.stop(container["cont"])
            #container.stop(logfile=self.CONTAINER_LOGFILE)


    def rm(self, containers=None, log=True):
        """
            Remove all stopped containers
        """
        for container in containers or self.containers:
            self.docker.remove_container(container["cont"])
            #container.rm(logfile=self.CONTAINER_LOGFILE)


    def clear(self):
        """
            Clear container list.
            This does nothing to the container instances themselves
        """
        self.containers = []


    def pause(self):
        """
            Pause current container. This effectively pauses the pipeline
        """
        if self.active:
            self.docker.pause(self.active["cont"])


    def resume(self):
        """
            Resume puased container. This effectively resumes the pipeline
        """
        if self.active:
            self.docker.unpause(self.active["cont"])


    def readJson(self, config):
        return utils.readJson(self.configs_path+"/"+config)
