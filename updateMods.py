import sys
import requests
import os
import json
import urllib.parse
import copy
import re

SUPPORTED_SITES = []

def modSite(url: str) -> str:
    domain = url.split("//")[-1].replace("www.", "").split("/")[0].split(".")[0]
    if domain in SUPPORTED_SITES:
        return domain
    else:
        raise ValueError(f"{domain} is not yet supported")



# Import config file
with open(sys.argv[1]) as config_file:
    configs = json.loads(config_file.read())

for config in configs:
    print(config["mod_urls"])
    for mod, url in config["mod_urls"].items():
        try:
            print(modSite(url))
        except ValueError as e:
            print(e.args)


version = input("Version Number: ")
strDeepSearch = input("Poll older releases if mods are not found in first page of API results? [y/n]: ").lower()
deepSearch = (strDeepSearch == "y")

print("Updating to Minecraft Version " + version)

print("Updating Fabric Loader...")
fabricInstallerAPIinfo = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/maven-metadata.xml").text
fabricInstallerVersion = [x.strip().strip("</latest>") for x in fabricInstallerAPIinfo.split("\n") if "latest" in x][0]
fabricInstaller = requests.get("https://maven.fabricmc.net/net/fabricmc/fabric-installer/{0}/fabric-installer-{0}.jar".format(fabricInstallerVersion))
with open(fabric_installer_name, 'wb') as file:
    file.write(fabricInstaller.content)
os.system("java -jar {0} client -mcversion {1}".format(fabric_installer_name, version))
os.remove(fabric_installer_name)
print()
            