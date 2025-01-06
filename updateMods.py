import argparse
import requests
import os
import json
import hashlib
from enum import Enum
from datetime import datetime
import urllib.parse
import copy
import re

class DownloadError(BaseException):
    pass

class PrintType(Enum):
    INFO = {"prefix": "INFO: ", "color": "", "level": 0}
    INFO_WARN = {"prefix": "INFO-WARN: ", "color": "\033[96m", "level": 1}
    WARNING = {"prefix": "WARNING: ", "color": "\033[93m", "level": 2}
    ERROR = {"prefix": "ERROR: ", "color": "\033[91m", "level": 3}

def log_print(msg_type: PrintType, msg: str) -> None:
    global errors_count
    global warnings_count
    match msg_type:
        case PrintType.INFO:
            pass
        case PrintType.INFO_WARN:
            pass
        case PrintType.WARNING:
            warnings_count += 1
        case PrintType.ERROR:
            errors_count += 1
    if msg_type.value["level"] + print_verbosity >= (levels := len(set([x.value["level"] for x in PrintType]))):
        print(f"{msg_type.value["color"]}{msg_type.value["prefix"]}{msg}\033[0m")
    if logfile != "None" and msg_type.value["level"] + log_verbosity >= levels:
        with open(logfile, "a") as log:
            log.write(f"[{datetime.now()}] {msg_type.value["prefix"]}{msg}\n")

def matches_hashes(filepath: str, sha1: str = None, sha512: str = None, size: int = None) -> bool:
    if not (sha1 or sha512 or size):
        # No identifying information has been given
        raise ValueError("No file identifiers provided")
    
    # Check that file size matches, if provided
    if size and os.path.getsize(filepath) != size:
        return False
    # Size matches (or was unknown), so check hashes
    sha1alg = hashlib.sha1()
    sha512alg = hashlib.sha512()

    with open(filepath, "rb") as file:
        while data := file.read(BUFFER_SIZE):
            sha1alg.update(data)
            sha512alg.update(data)
    # Calculate and check simpler hash first
    if sha1 and (sha1 != sha1alg.hexdigest()):
        return False
    if sha512:
        return (sha512 == sha512alg.hexdigest())
    return True

def english_list_join(stringList: list[str]) -> str:
    length = len(stringList)
    if length:
        if length == 1:
            return stringList[0]
        if length == 2:
            return " and ".join(stringList)
        return f"{", ".join(stringList[:-1])}, and {stringList[-1]}"
    else:
        raise ValueError("List must not be empty")

def latest_mc_version(snapshot = False) -> str:
    log_print(PrintType.INFO, f"Getting latest Minecraft version ({"including" * snapshot}{"excluding" * (not snapshot)} snapshots)...")
    version_manifest_response = requests.get("https://launchermeta.mojang.com/mc/game/version_manifest.json")
    try:
        version_manifest_response.raise_for_status()
        version_manifest_json = json.loads(version_manifest_response.text)
        if snapshot:
            version = version_manifest_json["latest"]["snapshot"]
        else:
            version = version_manifest_json["latest"]["release"]
        log_print(PrintType.INFO, f"Latest version is {version}.")
    except requests.HTTPError as e:
        log_print(PrintType.ERROR, f"{e.args[0]}. Could not retrieve Minecraft versions.")
        version = input("Please enter the desired version: ")
    finally:
        return version

def downstep_version(version: str) -> str:
    version_parts = version.split(".")
    if not all([x.isnumeric() for x in version_parts]):
        raise ValueError(
            f"{version} is a snapshot, prerelease, release candidate, or April Fool's update, and cannot be decremented.",
            version
        )
    match len(version_parts):
        case 2:
            # Base version, so can't downstep
            raise ValueError(f"{version} is a base version and cannot be decremented", f"{version}.x")
        case 3:
            if version_parts[2] == "0":
                # Not sure how this would happen but good to check for it
                base_version = f"{version_parts[0]}.{version_parts[1]}"
                raise ValueError(f"{base_version} is a base version and cannot be decremented", f"{base_version}.x")
            new_minor = int(version_parts[2]) - 1
            if not new_minor:
                return f"{version_parts[0]}.{version_parts[1]}"
            return f"{version_parts[0]}.{version_parts[1]}.{str(new_minor)}"

def parse_version(version: str) -> str:
    global latest_version
    global latest_snapshot

    match version:
        case None | "":
            # No version specified, so get the latest version.  This is for the 
            # case where both the script and the config have no specified version.
            log_print(PrintType.INFO, "No version specified.")
            # Check to make sure we haven't already gotten the latest version earlier
            if not latest_version:
                latest_version = latest_mc_version(False)
            return latest_version
        case "latest":
            if not latest_version:
                latest_version = latest_mc_version(False)
            return latest_version
        case "latest_snapshot":
            if not latest_snapshot:
                latest_snapshot = latest_mc_version(True)
            return latest_snapshot
        case _:
            return version

def download_server_jar(version: str, directory: str, name: str, namepattern = "minecraft_server\\..*\\.jar") -> str:
    """
    Downloads the minecraft server jar for the specified version and places it in the given directory.
    Returns the filename of the downloaded jar.
    """
    # Get the version maifest with urls to version-specific json
    log_print(PrintType.INFO, "Getting server jar information...")
    version_manifest_response = requests.get("https://launchermeta.mojang.com/mc/game/version_manifest.json")
    version_manifest_response.raise_for_status()
    
    # Extract the url
    version_json_url = [x for x in json.loads(version_manifest_response.text)["versions"] if x["id"] == version][0]["url"]
    
    # Get the version-specific json
    version_json_response = requests.get(version_json_url)
    version_json_response.raise_for_status()
    server_json = json.loads(version_json_response.text)["downloads"]["server"]
    server_jar_path = os.path.join(directory, name)

    # Check if the jar is already present
    log_print(PrintType.INFO, f"Checking directory for existing {name}...")
    if os.path.isfile(server_jar_path) and matches_hashes(server_jar_path, server_json["sha1"], size = server_json["size"]):
        log_print(PrintType.INFO, "Found matching server jar, skipping download.")
    else:
        # Filename exists, but is not jar
        if os.path.isfile(server_jar_path):
            log_print(PrintType.WARNING, f"{name} already exists, but is not a valid server jar and will be overwritten.")
        
        # Jar is not present; download
        log_print(PrintType.INFO, "No matching server jar found.  Downloading server jar...")
        server_jar_response = requests.get(server_json["url"])
        server_jar_response.raise_for_status()
        with open(server_jar_path, "wb") as file:
            file.write(server_jar_response.content)

        # Check that the download succeded
        if not matches_hashes(server_jar_path, server_json["sha1"], size = server_json["size"]):
            # Remove incorrectly downloaded file
            os.remove(server_jar_path)
            raise DownloadError("Failed to download server jar")
        
        # Download was successful
        log_print(PrintType.INFO, f"Successfully downloaded server jar as {name}.")

    # Remove old server jars
    old_jars = [x for x in os.listdir(directory) if x != name and re.match(namepattern)]
    if old_jars:
        log_print(PrintType.INFO, f"Removing old server jar{"s" * bool(len(old_jars) - 1)} {english_list_join(old_jars)}.")
        for old_jar in old_jars:
            os.remove(os.path.join(directory, old_jar))
    
    return server_jar_filename


def download_modrinth_mod(id: str, display_name: str, version: str, loader: str, mods_folder_path: str, enforce_release = True) -> None:
    # Get api data
    api_url = f"https://api.modrinth.com/v2/project/{id}/version"
    api_response = requests.get(api_url)
    # Ensure api response was successful
    api_response.raise_for_status()
    mod_json = json.loads(api_response.text)

    # Get all primary file names to check if we already have one (mark old version for removal)
    filenames = []
    for mod_version in mod_json:
       # Get jar file json
        primary_file_list = [x for x in mod_version["files"] if x["primary"] == True]
        if primary_file_list:
            primary_file = primary_file_list[0]
        else:
            primary_file = mod_version["files"][0]
        filenames.append(primary_file["filename"])
    # Find any existing files that whose names are versions of this mod
    mods = os.listdir(mods_folder_path)
    oldversions = [x for x in mods if x in filenames]

    # Filter for:  Matches game version, matches loader, and (if specified) is a full release
    matching_game_version = [x for x in mod_json if version in x["game_versions"] and loader in x["loaders"]]
    any_available = bool(matching_game_version)
    if enforce_release:
        matching_game_version = [x for x in matching_game_version if x["version_type"] == "release"]
    
    # Get latest matching mod version
    try:
        latest_release_time = max([x["date_published"] for x in matching_game_version])
    except ValueError as e:
        raise ValueError(
            f"Cannot find {display_name} for {version}{enforce_release * " among full releases"}{(not enforce_release) * ", including alpha/beta/prereleases"}",
            any_available
        )
    latest_release_json = [x for x in matching_game_version if x["date_published"] == latest_release_time][0]
    
    # Get jar file json
    primary_file_list = [x for x in latest_release_json["files"] if x["primary"] == True]
    if primary_file_list:
        primary_file = primary_file_list[0]
    else:
        primary_file = latest_release_json["files"][0]
    
    # Full file path
    file_path = os.path.join(mods_folder_path, primary_file["filename"])
    
    # Check if we already have the desired file
    # Utilizing short-circuit logic to only calculate hashes if the filename exists
    if os.path.isfile(file_path) and matches_hashes(file_path, primary_file["hashes"]["sha1"], primary_file["hashes"]["sha512"], primary_file["size"]):
        log_print(PrintType.INFO, f"The latest version of {display_name} compatible with {version} is already present.  Skipping download.")
    else:
        # Make sure there isn't a non-mod file of the same name
        if os.path.isfile(file_path):
            log_print(PrintType.WARNING, f"{primary_file["filename"]} already exists, but is not a valid mod and will be overwritten.")
            oldversions.remove(primary_file["filename"])
        # Download file
        with open(file_path, "wb") as file:
            log_print(PrintType.INFO, f"Downloading {primary_file["filename"]} for {version} from Modrinth...")
            file_response = requests.get(primary_file["url"])
            file_response.raise_for_status()
            file.write(file_response.content)

        # Check that the download was successful (i. e. we got the file we wanted)
        if matches_hashes(file_path, primary_file["hashes"]["sha1"], primary_file["hashes"]["sha512"], primary_file["size"]):
            log_print(PrintType.INFO, "Download complete.")
        else:
            # Remove partially/incorrectly downloaded file
            os.remove(file_path)
            raise DownloadError("Download failed.")
    
    # Remove old versions of this mod - at this point we know we have a good copy
    if oldversions:
        log_print(PrintType.INFO, f"Removing old version{"s" * bool(len(oldversions) - 1)} of {display_name}: {english_list_join(oldversions)}.")
        for file in oldversions:
            os.remove(os.path.join(mods_folder_path, file))



# Arbitrary buffer size for reading files into hash function
BUFFER_SIZE = 65536 # Bytes (64KB)

# For reporting total errors/warnings at end of script
warnings_count: int = 0
errors_count: int = 0
# Keep track of latest version/snapshot so we don't have to fetch them twice
latest_version: str = None
latest_snapshot: str = None



# Set up argparser
parser = argparse.ArgumentParser(formatter_class = argparse.RawDescriptionHelpFormatter)
parser.add_argument("config_file", help = "path to config file; relative to script's directory or absolute")
parser.add_argument("mode", choices = ["client", "server"], help = "whether the script should install client or server profiles")
parser.add_argument("-l", "--logfile", default = "log.txt", help = "path to log file; relative to script's directory or absolute; default is log.txt in the script's directory; use None to disable logging")
parser.add_argument("-m", "--mcversion", help = "Override config-specified game versions with MCVERSION.  Use \"latest\" for latest release or \"latest_snapshot\" for latest snapshot/prerelease/release candidate.")
parser.add_argument("-n", "--noloader", action = "store_true", help = "disables installing modloader")
parser.add_argument("-V", "--log-verbosity", type = int, choices = range(5), default = 4, help = "Sets the log file verbosity level.  Default is 4.")
parser.add_argument("-v", "--print-verbosity", type = int, choices = range(5), default = 4, help = "Sets the stdout verbosity level.  Default is 4.")
parser.epilog = "Verbosity levels:\n\t0: Silent\n\t1: ERROR messages only\n\t2: ERRORs and WARNINGs\n\t3: ERRORs, WARNINGs, and INFO_WARNs\n\t4: All messages (including INFO)"

# Parse arguments (replace with sys.argv)
parsed_args = vars(parser.parse_args("config.json server".split()))

input_version = parsed_args["mcversion"]
mode = parsed_args["mode"]
config_file_name = parsed_args["config_file"]
install_loader = not parsed_args["noloader"]
log_verbosity = parsed_args["log_verbosity"]
print_verbosity = parsed_args["print_verbosity"]
logfile = parsed_args["logfile"]



log_print(PrintType.INFO, f"Mod Updater script starting using config file {config_file_name}.")

# Resolve "latest" or "latest_snapshot"
parsed_version = parse_version(input_version)

# Import config file
with open(config_file_name) as config_file:
    configs = json.loads(config_file.read())



for config in configs:
    # Skip if this config is disabled or set to auto and doesn't match the specified mode
    # (e. g. config is for server, script is in client mode)
    enable_mode = config["enabled"].lower()
    if enable_mode == "false":
        log_print(PrintType.INFO, f"Skipping disabled config {config["name"]}.")
        continue
    if enable_mode == "auto" and config["type"] != mode:
        log_print(PrintType.INFO, f"Script is in {mode} mode, skipping {config["type"]} config {config["name"]}.")
        continue
    if enable_mode == "true" and config["type"] != mode:
        log_print(PrintType.INFO_WARN, f"Enable override is true for {config["name"]}, running despite mode/type mismatch.")

    
    
    log_print(PrintType.INFO, f"Updating {config["type"]} {config["name"]}...")

    # Get mods folder path
    mods_folder = os.path.join(config["directory"], config["mods_folder"])
    # Check that mods folder exists and create if not
    if not os.path.isdir(mods_folder):
        log_print(PrintType.INFO_WARN, f"No mods folder detected.  Creating {mods_folder}")
        os.mkdir(mods_folder)



    # Get version
    try:
        config_version = parse_version(config["version"])
        if not config_version:
            # This means there's something like "version": "" in the config; this should mean "no default",
            # so raise a KeyError to make the try statement think there is no version field in the config.
            raise KeyError()
        if not input_version:
            # Script was run with no version argument, so use config default
            selected_version = config_version
            # Just to make the log statements nicer
            if config["version"] == "latest" or config["version"] == "latest_snapshot":
                log_print(PrintType.INFO, f"No version specified.  Using config default {config["version"]} version {selected_version}.")
            else:
                log_print(PrintType.INFO, f"No version specified.  Using config default version {selected_version}.")
        else:
            # Override the config default with the argument passed from the script
            selected_version = parsed_version
            if input_version == "latest" or input_version == "latest_snapshot":
                log_print(PrintType.INFO_WARN, f"Config version overridden.  Using {input_version} version {selected_version}")
            else:
                log_print(PrintType.INFO_WARN, f"Config version overridden.  Using version {selected_version}.")         
    except KeyError:
        # No version specified in config, so use whatever the script was given
        selected_version = parsed_version
        log_print(PrintType.INFO, f"No default version specified by config.  Using version {selected_version}.")



    # Install modloader
    if install_loader and config["install_loader"]:
        match config["loader"].lower():
            case "fabric":
                log_print(PrintType.INFO, f"Installing Fabric loader for version {selected_version}...")
                log_print(PrintType.INFO, f"Getting Fabric installer...")
                try:
                    # Determine the latest installer version
                    fabric_api_response = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/maven-metadata.xml")
                    fabric_api_response.raise_for_status()
                    installer_version = [x.strip().strip("</latest>") for x in fabric_api_response.text.split("\n") if "latest" in x][0]
                    # Download the installer jar
                    fabric_installer_response = requests.get(f"https://maven.fabricmc.net/net/fabricmc/fabric-installer/{installer_version}/fabric-installer-{installer_version}.jar")
                    fabric_installer_response.raise_for_status()
                    fabric_installer_path = os.path.join(config["directory"], config["fabric_installer_name"])
                    with open(fabric_installer_path, "wb") as file:
                        file.write(fabric_installer_response.content)
                    log_print(PrintType.INFO, f"Successfully downloaded latest Fabric installer as {config["fabric_installer_name"]}; running installer...")
                    # Run the installer
                    os.system(f"java -jar {fabric_installer_path} {config["type"]} -mcversion {selected_version} -snapshot -dir {config["directory"]}")
                    # Remove the installer
                    log_print(PrintType.INFO, f"Removing {config["fabric_installer_name"]}...")
                    os.remove(fabric_installer_path)
                    log_print(PrintType.INFO, f"{config["fabric_installer_name"]} removed successfully.")

                    # Get the minecraft server jar if this is a server config
                    if config["type"] == "server":
                        server_jar_filename = download_server_jar(selected_version, config["directory"])
                        
                        # Update fabric-server-launcher.properties
                        log_print(PrintType.INFO, "Updating fabric-server-launcher.properties.")
                        with open(os.path.join(config["directory"], "fabric-server-launcher.properties"), "w") as file:
                            file.write(f"# {datetime.now().strftime("%a %d %b %Y %H:%M:%S")}\n")
                            file.write(f"serverJar={server_jar_filename}\n")
                            

                except (requests.HTTPError, OSError, DownloadError) as e:
                    log_print(PrintType.ERROR, e.args[0])
            case _:
                log_print(PrintType.ERROR, f"Installing modloader {config["loader"]} is not currently supported.")



    # Install mods
    for mod in config["mods"]:
        match mod["site"]:
            case "modrinth":
                # If we can't find the desired version, we can try to use the previous minor version
                # (e.g can't find 1.19.4 --> try 1.19.3).  Additionally, Modrinth allows for selecting
                # between mod releases and alpha/beta/prerelease versions, so we want to search as follows:
                #   1: Desired version, releases only
                #   2: Desired version, alphas/betas/prereleases, if there are any (determined during 1)
                #   3: Downstep version, releases only
                #   4: Downstep version, alphas/betas/prereleases, if there are any
                #   5: Repeat 3 and 4 until: we find a mod version, or the base version (e.g. 1.19) fails.
                iterator_version = selected_version
                enforce_release = True
                while True:
                    try:
                        download_modrinth_mod(mod["id"], mod["displayName"], iterator_version, config["loader"].lower(), mods_folder, enforce_release)
                        break
                    except ValueError as e:
                        # download_modrinth_mod raises a ValueError if the given mod/version combination cannot be found
                        log_print(PrintType.WARNING, str(e.args[0]))

                        # The ValueError includes whether alpha/beta/prerelease versions were present as the second argument
                        if enforce_release and e.args[1]:
                            # Get the unstable version that we know exists
                            log_print(PrintType.INFO, "Checking alpha/beta/prereleases...")
                            enforce_release = False
                            continue
                        else:
                            # Note that no unstable versions were found during the main check
                            if enforce_release and not e.args[1]:
                                log_print(PrintType.INFO_WARN, f"Did not find alpha/beta/prereleases of {mod["displayName"]} for {iterator_version}.")
                            # Try again with the next version down
                            enforce_release = True
                            try:
                                iterator_version = downstep_version(iterator_version)
                                log_print(PrintType.INFO, f"Checking for {mod["displayName"]} versions compatible with Minecraft {iterator_version}...")
                            # downstep_version raises a ValueError if the version cannot be downstepped further, in which case we report the 
                            # error and give up.
                            except ValueError as e:
                                log_print(PrintType.ERROR, f"Could not find {mod["displayName"]} for {e.args[1]}")
                                break
                    except (requests.HTTPError, DownloadError) as e:
                        # Something went wrong with getting api data or downloading the mod, report the error and give up.
                        log_print(PrintType.ERROR, f"{e.args[0]}.  Could not download {mod["displayName"]}.")
                        break
                    except OSError as e:
                        # Couldn't remove old versions for some reason, but the new version downloaded successfully.
                        log_print(PrintType.WARNING, f"{e.args[0]}.  Removing old versions of {mod["displayName"]} failed.  Inspecting the mods folder is recommended.")
                        break
            case _:
                log_print(PrintType.ERROR, f"{mod["site"].title()} is not currently supported.  Skipping {mod["displayName"]}")
                continue



# Report total number of errors and warnings
if (warnings_count + errors_count):
    warnings = f"{warnings_count} warning{"s" * (warnings_count != 1)}"
    errors = f"{errors_count} error{"s" * (errors_count != 1)}"
    log_print(PrintType.INFO, f"Script completed with {errors} and {warnings}.")
else:
    log_print(PrintType.INFO, "Script completed with no errors or warnings.")




#fabricInstallerAPIinfo = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/maven-metadata.xml").text
#fabricInstallerVersion = [x.strip().strip("</latest>") for x in fabricInstallerAPIinfo.split("\n") if "latest" in x][0]
#fabricInstaller = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/{0}/fabric-installer-{0}.jar".format(fabricInstallerVersion))
#with open(fabric_installer_name, 'wb') as file:
#    file.write(fabricInstaller.content)
#os.system("java -jar {0} client -mcversion {1}".format(fabric_installer_name, version))
#os.remove(fabric_installer_name)
            