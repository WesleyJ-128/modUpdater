import sys
import requests
import os
import json
import urllib.parse
import copy
import re

SUPPORTED_SITES = []

def download_modrinth_mod(id: str, version: str, loader: str, path: str, enforce_release = True) -> None:
    # Get api data
    api_url = f"https://api.modrinth.com/v2/project/{id}/version"
    api_response = requests.get(api_url)
    # Ensure api response was successful
    api_response.raise_for_status()
    mod_json = json.loads(api_response.text)

    # Filter for:  Matches game version, matches loader, and (if specified) is a full release
    matching_game_version = [x for x in mod_json if version in x["game_versions"] and loader in x["loaders"] and (not enforce_release or x["version_type"] == "release")]
    # Get latest matching mod version
    try:
        latest_release_time = max([x["date_published"] for x in matching_game_version])
    except ValueError as e:
        raise ValueError(f"Cannot find {id} for {version}" + enforce_release * " among full releases" + (not enforce_release) * ", including alpha/beta/prereleases")
    latest_release_json = [x for x in matching_game_version if x["date_published"] == latest_release_time][0]
    
    # Get jar file json
    primary_file_list = [x for x in latest_release_json["files"] if x["primary"] == True]
    if primary_file_list:
        primary_file = primary_file_list[0]
    else:
        primary_file = latest_release_json["files"][0]
    
    # Download file
    with open(os.path.join(path, primary_file["filename"]), "wb") as file:
        file.write(requests.get(primary_file["url"]).content)

# Import config file
with open(sys.argv[1]) as config_file:
    configs = json.loads(config_file.read())

for config in configs:
    # Get mods folder path
    mods_folder = os.path.join(config["directory"], config["mods_folder"])

    # Get version
    version = "1.21.4"

    for mod in config["mods"]:
        match mod["site"]:
            case "modrinth":
                try:
                    download_modrinth_mod(mod["id"], version, config["loader"], mods_folder)
                except ValueError as e:
                    print(f"WARNING: {e.args[0]}")
                except requests.HTTPError as e:
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
            