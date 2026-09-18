import os
import sys
import shutil
import pathlib

import requests
import config
import zipfile
import tarfile

from colorama import Fore, init, just_fix_windows_console

init(autoreset=True)

if sys.platform == 'win32':
    just_fix_windows_console()

session = requests.Session()

REQUEST_TIMEOUT = 60  # seconds


# --- stopgap fix for the character-creator "difficulty" crash -----------------
# The ImGui character creator draws a difficulty rating by measuring the starting
# weapon's DPS against mon_zombie_soldier_no_weakpoints /
# mon_zombie_survivor_no_weakpoints.  Those monsters only exist in the TEST_DATA
# mod (not loaded in normal play), so the lookup fails, realDebugmsg fires every
# frame and the creator becomes unresponsive (red error box).
# Define them in the base data until upstream ships a proper fix.
NO_WEAKPOINTS_FIX_PATH = "./game/data/json/monsters/no_weakpoints_dps_fix.json"
NO_WEAKPOINTS_FIX_CONTENT = """[
  {
    "id": "mon_zombie_soldier_no_weakpoints",
    "type": "MONSTER",
    "copy-from": "mon_zombie_soldier",
    "delete": {
      "weakpoint_sets": [ "wps_humanoid_body", "wps_vital_organs", "wps_eyes", "wps_humanoid_body_armor", "wps_humanoid_open_helmet" ]
    }
  },
  {
    "id": "mon_zombie_survivor_no_weakpoints",
    "type": "MONSTER",
    "copy-from": "mon_zombie_survivor",
    "delete": {
      "weakpoint_sets": [ "wps_humanoid_body", "wps_vital_organs", "wps_eyes", "wps_humanoid_light_armor", "wps_humanoid_open_helmet" ]
    }
  },
  {
    "id": "mon_zombie_smoker_no_weakpoints",
    "type": "MONSTER",
    "copy-from": "mon_zombie_smoker",
    "delete": {
      "weakpoint_sets": [ "wps_humanoid_body", "wps_vital_organs", "wps_eyes" ]
    }
  }
]
"""


def info(msg):
    print(str(msg))


def success(msg):
    print(Fore.GREEN + str(msg))


def error(msg):
    print(Fore.RED + str(msg))


def _upstream_already_defines_no_weakpoints():
    """True once upstream defines the monster itself (avoid a duplicate id)."""
    data_dir = pathlib.Path("./game/data/json")
    if not data_dir.exists():
        return False
    needle = '"id": "mon_zombie_soldier_no_weakpoints"'
    for candidate in data_dir.rglob("*.json"):
        try:
            if needle in candidate.read_text(encoding="utf-8", errors="ignore"):
                return True
        except OSError:
            continue
    return False


def apply_no_weakpoints_fix():
    if _upstream_already_defines_no_weakpoints():
        info("upstream already defines the no_weakpoints monsters; skipping patch")
        return
    target = pathlib.Path(NO_WEAKPOINTS_FIX_PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(NO_WEAKPOINTS_FIX_CONTENT, encoding="utf-8")
    info("applied no_weakpoints DPS fix")


def get_latest_release():
    info("getting latest release ...")
    release_url = f"https://api.github.com/repos/{config.OWNER}/{config.REPO}/releases"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    try:
        response = session.get(release_url, headers=headers, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        result = response.json()
        return list(filter(lambda x: x["prerelease"], result[:10]))
    except Exception as e:
        error(f"failed to get latest release: {e}")
        return []


def construct_search_str():
    is_64bits = sys.maxsize > 2 ** 32
    platform = sys.platform
    if platform == "win32":
        platform = "windows"
    elif platform == "linux":
        platform = "linux"
    search_str = f"cdda-{platform}-"
    if config.USE_TERMINAL:
        search_str += "terminal-only-"
    else:
        search_str += "with-graphics-"
    if config.ENABLE_SOUNDS:
        search_str += "and-sounds-"
    if is_64bits and not platform == "osx":
        search_str += "x64"
    elif platform == "osx":
        search_str += "universal"
    return search_str


def download(url, file_name):
    os.makedirs("./download", exist_ok=True)
    target = f"./download/{file_name}"
    if os.path.exists(target):
        info("detect a release file exists, try to unzip it!")
        return
    info(f"try to download {url}")
    req = None
    try:
        req = session.get(url, stream=True, timeout=REQUEST_TIMEOUT)
        req.raise_for_status()
        total_length = int(req.headers.get('Content-Length', 0))
        downloaded = 0
        with open(target, "wb") as f:
            for chunk in req.iter_content(chunk_size=4096):
                if not chunk:
                    continue
                f.write(chunk)
                downloaded += len(chunk)
                print('\r', end='')
                print(
                    f"downloaded: {downloaded / 1024 / 1024:.2f} MB / {total_length / 1024 / 1024:.2f} MB",
                    end='')
            print()
        success(f"download {file_name} finished!")
    except Exception as e:
        # drop a partial download so the next run doesn't mistake it for a
        # complete archive
        if os.path.exists(target):
            os.remove(target)
        error(f"download failed: {e}")
        raise
    finally:
        if req is not None:
            req.close()


def download_release(release):
    search_str = construct_search_str()
    for asset in release["assets"]:
        name = asset["name"]
        if name.startswith(search_str) and name.endswith(".zip"):
            download(asset["browser_download_url"], name)
            return name
    return ""


def unzipfile(file_name):
    os.makedirs("./game", exist_ok=True)
    info(f"try to extract {file_name}!")
    extension = file_name.split(".")[-1]
    if extension == "zip":
        with zipfile.ZipFile(f"./download/{file_name}", "r", allowZip64=True) as zfile:
            zfile.extractall("./game")
    elif extension == "gz":
        with tarfile.open(f"./download/{file_name}", "r:gz") as gzfile:
            gzfile.extractall("./game")
    success("extract all success!")


def get_build_number():
    if not os.path.exists("./game/VERSION.txt"):
        return ""
    with open("./game/VERSION.txt", "r") as f:
        for line in f:
            if line.startswith("build number"):
                return line.split(":")[-1].strip()
    return ""


def prepare_update():
    # Remove the old per-build content before re-extracting the new zip, so no
    # stale files survive an update (extractall only overwrites, it never
    # deletes files the new build dropped/renamed).
    #   cache/ -> runtime font/tileset cache, regenerated on launch (not in zip)
    #   data/  -> game JSON content (in the zip, re-extracted fresh)
    #   gfx/   -> tilesets (in the zip, re-extracted fresh)
    # config/ and save/ are intentionally left alone (and aren't in the zip).
    for sub in ("cache", "data", "gfx"):
        p = pathlib.Path("./game") / sub
        if p.exists():
            shutil.rmtree(p)


def download_latest_version(releases=None):
    if releases is None:
        releases = get_latest_release()
        if not releases:
            error("could not fetch any releases; aborting")
            return
        success(f"the latest release is released at {releases[0]['published_at']}")
    for release in releases:
        file_name = download_release(release)
        if file_name != "":
            prepare_update()
            unzipfile(file_name)
            apply_no_weakpoints_fix()
            success("all done!")
            return
    error("did not find a suitable version to download!")


def check_for_asset(release):
    search_str = construct_search_str()
    for asset in release["assets"]:
        name = asset["name"]
        if name.startswith(search_str) and name.endswith(".zip"):
            return True
    return False


def _release_matches(release, build_number):
    tag = release.get("tag_name") or ""
    name = release.get("name") or ""
    return tag.endswith(build_number) or name.endswith(build_number)


def check_updates():
    build_number = get_build_number()
    if build_number == "":
        info("did not find VERSION.txt, download the latest release instead.")
        download_latest_version()
        return
    print(f"current build number: {build_number}")
    releases = get_latest_release()
    if not releases:
        error("could not fetch releases; aborting")
        return
    # releases are returned newest-first
    if _release_matches(releases[0], build_number):
        info("there are no new versions!")
        return
    info("a newer build is available, downloading ...")
    download_latest_version(releases)


def main():
    if config.USE_PROXY:
        session.proxies = {
            "http": config.HTTP_PROXY,
            "https": config.HTTPS_PROXY
        }
    try:
        if config.CHECK_UPDATES:
            check_updates()
        else:
            download_latest_version()
    finally:
        session.close()


if __name__ == '__main__':
    main()
