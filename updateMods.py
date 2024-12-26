import requests
import os
import json
import urllib.parse
import copy
import re

MINECRAFT_DIRECTORY = "C:\\Users\\johnsw9\\AppData\\Roaming\\.minecraft"

fabric_installer_name = os.path.join(MINECRAFT_DIRECTORY, "fabricInstaller.jar")
mods_folder = os.path.join( MINECRAFT_DIRECTORY, "mods2")

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

print("Removing old mods")
try:
    oldMods = os.listdir(mods_folder)
    for oldMod in oldMods:
        path = os.path.join(mods_folder, oldMod)
        if os.path.isfile(path):
            os.remove(path)
        else:
            print("WARNING: {0} in {1} (specified as mods folder) is not a file and was not removed!".format(oldMod, mods_folder))
    print("Successfully removed old mods")
except OSError:
    print("ERROR: Old mod deletion failed")
finally:
    print()

apiUrls = {
    "Carpet" : "https://api.github.com/repos/gnembon/fabric-carpet/releases",
    "Carpet-Extra" : "https://api.github.com/repos/gnembon/carpet-extra/releases",
    #"Carpet-Autocrafter" : "https://api.github.com/repos/gnembon/carpet-autoCraftingTable/releases",
    "Lithium" : "https://api.github.com/repos/CaffeineMC/lithium-fabric/releases",
    "FabricAPI" : "https://api.github.com/repos/FabricMC/fabric/releases",
    # Client-side only
    "MiniHUD" : "https://api.github.com/repos/sakura-ryoko/minihud/releases",
    "MaLiLib" : "https://api.github.com/repos/sakura-ryoko/malilib/releases",
    "Tweakeroo" : "https://api.github.com/repos/sakura-ryoko/tweakeroo/releases",
    "Litematica" : "https://api.github.com/repos/sakura-ryoko/litematica/releases",
    "Itemscroller" : "https://api.github.com/repos/sakura-ryoko/Itemscroller/releases",
    "Sodium" : "https://api.github.com/repos/CaffeineMC/sodium-fabric/releases",
}

failedMods = []

for mod in apiUrls:
    print("Updating {} ...".format(mod))
    pagesLeft = True
    url = apiUrls[mod]
    downloadUrl = None
    while pagesLeft and not downloadUrl:
        print("Getting versions from {}...".format(url))
        result = requests.get(url)
        data = json.loads(result.text)
        if deepSearch:
            try:
                linkHeaders = result.headers["link"]
                nextPage = [x.split(";")[0].strip().strip("<>") for x in linkHeaders.split(",") if "next" in x][0]
            except (KeyError, IndexError):
                pagesLeft = False
        else:
            pagesLeft = False
        testVersion = copy.deepcopy(version)
        while not downloadUrl:
            elements = testVersion.split(".")
            try:
                print("Getting {0} for Minecraft version {1}...".format(mod, testVersion))
                regex = re.compile(elements[0] + r"\." + elements[1] + r"(?!\.\d)" if len(elements) == 2 else elements[0] + r"\." + elements[1] + r"\." + elements[2])
                matchingVersion = [x for x in data if re.search(regex, x["name"])]
                latestId = max([x["id"] for x in matchingVersion])
                latestRelease = [x for x in matchingVersion if x["id"] == latestId][0]
                downloadUrl: str = [x for x in latestRelease["assets"] if re.search(regex, x["name"])][0]["browser_download_url"]
                fileName = urllib.parse.unquote(downloadUrl.split("/")[-1])
                print("Downloading {0} for MC version {1} from {2}...".format(mod, testVersion, downloadUrl))
                with open(os.path.join(mods_folder, fileName), "wb") as file:
                    file.write(requests.get(downloadUrl).content)
                print("Download complete.")
                print()
            except (IndexError, ValueError):
                print("WARNING: {0} for Minecraft version {1} not found.".format(mod, testVersion))
                if len(elements) < 3:
                    if deepSearch and pagesLeft:
                        print("Trying again with next API page...")
                        url = nextPage
                    else:
                        print("ERROR: Unable to find {0} for {1}".format(mod, ".".join(elements) + ".x"))
                        print()
                        failedMods.append(mod)
                    break
                else:
                    newSubVer = str(int(elements[2]) - 1)
                    if newSubVer == "0":
                        elements.pop(2)
                        testVersion = ".".join(elements)
                    else:
                        elements[2] = newSubVer
                        testVersion = ".".join(elements)
                    print("Trying again with {}...".format(testVersion))

stringList = None
if len(failedMods) == 1:
    stringList = failedMods[0]
elif len(failedMods) == 2:
    stringList = failedMods[0] + " and " + failedMods[1]
elif len(failedMods) > 2:
    stringList = ", ".join(failedMods[:-1]) + ", and " + failedMods[-1]
if stringList:
    print("ERROR: Failed to find {}!".format(stringList))
            