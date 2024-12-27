import sys
import requests
import os
import json
import hashlib
import urllib.parse
import copy
import re

# Arbitrary buffer size for reading files into hash function
BUFFER_SIZE = 65536 # Bytes (64KB)

class DownloadError(BaseException):
    pass

def matches_hashes(filepath: str, sha1: str, sha512: str) -> bool:
    sha1alg = hashlib.sha1()
    sha512alg = hashlib.sha512()

    with open(filepath, "rb") as file:
        while True:
            data = file.read(BUFFER_SIZE)
            # True when EOF reached
            if not data:
                break
            sha1alg.update(data)
            sha512alg.update(data)
    # Calculate and check simpler hash first
    if not sha1 == sha1alg.hexdigest():
        return False
    if sha512 == sha512alg.hexdigest():
        return True
    return False

def english_list_join(stringList: list[str]) -> str:
    length = len(stringList)
    if length:
        if length == 1:
            return stringList[0]
        if length == 2:
            return " and ".join(stringList)
        return ", ".join(stringList[:-1]) + f", and {stringList[-1]}"
    else:
        raise ValueError("List must not be empty")

def latest_mc_version(snapshot = False) -> str:
    global errors_count
    print("INFO: Getting latest Minecraft version (" + "including" * snapshot + "excluding" * (not snapshot) + " snapshots)...")
    version_manifest_response = requests.get("https://launchermeta.mojang.com/mc/game/version_manifest.json")
    try:
        version_manifest_response.raise_for_status()
        version_manifest_json = json.loads(version_manifest_response.text)
        if snapshot:
            version = version_manifest_json["latest"]["snapshot"]
        else:
            version = version_manifest_json["latest"]["release"]
        print(f"INFO: Latest version is {version}.")
    except requests.HTTPError as e:
        print(f"ERROR: {e.args[0]}. Could not retrieve Minecraft versions.")
        errors_count += 1
        version = input("Please enter the desired version: ")
    finally:
        return version

def download_modrinth_mod(id: str, display_name: str, version: str, loader: str, mods_folder_path: str, enforce_release = True) -> None:
    global errors_count
    global warnings_count
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
            f"Cannot find {display_name} for {version}" + enforce_release * " among full releases" + (not enforce_release) * ", including alpha/beta/prereleases",
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
    if os.path.isfile(file_path) and matches_hashes(file_path, primary_file["hashes"]["sha1"], primary_file["hashes"]["sha512"]):
        print(f"INFO: The latest version of {display_name} compatible with {version} is already present.  Skipping download.")
    else:
        # Make sure there isn't a non-mod file of the same name
        if os.path.isfile(file_path):
            print(f"WARNING: A file with the same name as the desired mod already exists. Removing {primary_file["filename"]}.")
            warnings_count += 1
            oldversions.remove(primary_file["filename"])
            os.remove(file_path)
        # Download file
        with open(file_path, "wb") as file:
            print(f"INFO: Downloading {primary_file["filename"]} for {version} from Modrinth...")
            file_response = requests.get(primary_file["url"])
            file_response.raise_for_status()
            file.write(file_response.content)

        # Check that the download was successful (i. e. we got the file we wanted)
        if matches_hashes(file_path, primary_file["hashes"]["sha1"], primary_file["hashes"]["sha512"]):
            print("INFO: Download complete.")
            # Remove old versions of this mod
            if oldversions:
                print("INFO: Removing old version" + "s" * bool(len(oldversions) - 1) + f" of {display_name}: " + english_list_join(oldversions) + ".")
                for file in oldversions:
                    os.remove(os.path.join(mods_folder_path, file))
        else:
            # Remove partially/incorrectly downloaded file
            os.remove(file_path)
            raise DownloadError("Download failed.")

# For reporting total errors/warnings at end of script
warnings_count: int = 0
errors_count: int = 0

# Parse arguments
version = "1.19.4"
mode = "client"
config_file_name = "config.json"
latest_version = None


# Import config file
with open(config_file_name) as config_file:
    configs = json.loads(config_file.read())

for config in configs:
    # Skip if this config is disabled or set to auto and doesn't match the specified mode
    # (e. g. config is for server, script is in client mode)
    enable_mode = config["enabled"].lower()
    if enable_mode == "false" or (enable_mode == "auto" and config["type"] != mode):
        continue

    print(f"INFO: Updating {mode} {config["name"]}...")

    # Get mods folder path
    mods_folder = os.path.join(config["directory"], config["mods_folder"])

    # Get version
    try:
        match config["version"].lower():
            case "auto":
                config_specified_version = version
            case "latest":
                if not latest_version:
                    config_specified_version = latest_mc_version(False)
                else:
                    config_specified_version = latest_version
            case "latest_snapshot":
                config_specified_version = latest_mc_version(True)
            case _:
                config_specified_version = config["version"]
    except KeyError:
        # No version specified in config, so assume auto (whatever the script was given)
        config_specified_version = version

    for mod in config["mods"]:
        match mod["site"]:
            case "modrinth":
                try:
                    download_modrinth_mod(mod["id"], mod["displayName"], config_specified_version, config["loader"], mods_folder)
                except ValueError as e:
                    print(f"WARNING: {e.args[0]}")
                    warnings_count += 1
                except (requests.HTTPError, DownloadError) as e:
                    print(f"ERROR: {e.args[0]}")
                    errors_count += 1
                except OSError as e:
                    # this will do something different
                    print(f"WARNING: {e.args[0]}.  Removing old versions of {mod["displayName"]} failed.  Inspecting the mods folder is recommended.")
                    warnings_count += 1
            case _:
                print(f"ERROR: {mod["site"].title()} is not currently supported.  Skipping {mod["displayName"]}")
                errors_count += 1
                continue
    
if (warnings_count + errors_count):
    warnings = f"{warnings_count} warning" + "s" * (warnings_count == 0 or warnings_count > 1)
    errors = f"{errors_count} error" + "s" * (errors_count == 0 or errors_count > 1)
    print(f"INFO: Script completed with {errors} and {warnings}.")
else:
    print("INFO: Script completed with no errors or warnings.")



#version = input("Version Number: ")
#strDeepSearch = input("Poll older releases if mods are not found in first page of API results? [y/n]: ").lower()
#deepSearch = (strDeepSearch == "y")
#
#print("Updating to Minecraft Version " + version)
#
#print("Updating Fabric Loader...")
#fabricInstallerAPIinfo = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/maven-metadata.xml").text
#fabricInstallerVersion = [x.strip().strip("</latest>") for x in fabricInstallerAPIinfo.split("\n") if "latest" in x][0]
#fabricInstaller = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/{0}/fabric-installer-{0}.jar".format(fabricInstallerVersion))
#with open(fabric_installer_name, 'wb') as file:
#    file.write(fabricInstaller.content)
#os.system("java -jar {0} client -mcversion {1}".format(fabric_installer_name, version))
#os.remove(fabric_installer_name)
#print()
            