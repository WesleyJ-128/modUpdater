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
    if len(stringList) == 1:
        return stringList[0]
    if len(stringList) == 2:
        return " and ".join(stringList)
    return ", ".join(stringList[:-1]) + f", and {stringList[-1]}"

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
            oldversions.remove(primary_file["filename"])
            os.remove(file_path)
        # Download file
        with open(file_path, "wb") as file:
            print(f"INFO: Downloading {primary_file["filename"]} for {version} from Modrinth...")
            file_response = requests.get(primary_file["url"])
            file_response.raise_for_status()
            file.write(file_response.content)
        if matches_hashes(file_path, primary_file["hashes"]["sha1"], primary_file["hashes"]["sha512"]):
            print("INFO: Download complete.")
            if oldversions:
                print("INFO: Removing old version" + "s" * bool(len(oldversions) - 1) + f" of {display_name}: " + english_list_join(oldversions) + ".")
                for file in oldversions:
                    os.remove(os.path.join(mods_folder_path, file))
        else:
            os.remove(file_path)
            raise DownloadError("Download failed.")



# Import config file
with open(sys.argv[1]) as config_file:
    configs = json.loads(config_file.read())

for config in configs:
    # Get mods folder path
    mods_folder = os.path.join(config["directory"], config["mods_folder"])

    # Get version
    version = "1.21.3"

    for mod in config["mods"]:
        match mod["site"]:
            case "modrinth":
                try:
                    download_modrinth_mod(mod["id"], mod["displayName"], version, config["loader"], mods_folder)
                except ValueError as e:
                    print(f"WARNING: {e.args[0]}")
                except (requests.HTTPError, DownloadError) as e:
                    print(f"ERROR: {e.args[0]}")
                except OSError as e:
                    # this will do something different
                    print(f"ERROR: {e.args[0]}")
            case "github":
                pass
            case _:
                print(f"ERROR: {mod["site"].title()} is not currently supported.  Skipping {mod["displayName"]}")
                continue



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
            