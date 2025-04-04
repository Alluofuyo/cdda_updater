import os
import sys
import time
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


def info(msg):
    print(msg)


def success(msg):
    print(Fore.GREEN + msg)


def error(msg):
    print(Fore.RED + msg)


def get_latest_release():
    info("getting latest release ...")
    release_url = f"https://api.github.com/repos/{config.OWNER}/{config.REPO}/releases"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    try:
        response = session.get(release_url, headers=headers)
        result = response.json()
        return list(filter(lambda x: x["prerelease"], result[:10]))
    except Exception as e:
        error(e)


def construct_search_str():
    is_64bits = sys.maxsize > 2 ** 32
    platform = sys.platform
    if platform == "win32":
        platform = "windows"
    elif platform == "darwin":
        platform = "osx"
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
    if not os.path.exists("./download"):
        os.mkdir("./download")
    if os.path.exists(f"./download/{file_name}"):
        info("detect a release file exists, try to unzip it!")
        return
    info(f"try to download {url}")
    req = None
    try:
        req = session.get(url, stream=True)
        total_length = int(req.headers['Content-Length'])
        downloaded = 0
        with open(f"./download/{file_name}", "wb") as f:
            for chunk in req.iter_content(chunk_size=4096):
                f.write(chunk)
                downloaded += len(chunk)
                print('\r', end='')
                print(
                    f"downloaded: {downloaded / 1024 / 1024:.2f} MB / {total_length / 1024 / 1024:.2f} MB",
                    end='')
        print()
        success(f"download {file_name} finished!")
    finally:
        req.close()


def download_release(release):
    assets = release["assets"]
    search_str = construct_search_str()
    for asset in assets:
        if asset["name"].startswith(search_str):
            download(asset["browser_download_url"], asset["name"])
            return asset["name"]
    return ""


def unzipfile(file_name):
    if not os.path.exists("./game"):
        os.makedirs("./game")
    info(f"try to extract {file_name}!")
    extension = file_name.split(".")[-1]
    if extension == "zip":
        with zipfile.ZipFile(f"./download/{file_name}", "r", allowZip64=True) as zfile:
            zfile.debug = 3
            zfile.extractall("./game")
    elif extension == "gz":
        with tarfile.open(f"./download/{file_name}", "r:gz") as gzfile:
            gzfile.extractall("./game")
    success("extract all success!")


def get_build_number():
    if not os.path.exists("./game/VERSION.txt"):
        return ""
    else:
        with open("./game/VERSION.txt", "r") as f:
            build_number = list(filter(lambda l: l.startswith("build number"), f.readlines()))[0].split(":")[-1].strip()
            return build_number


def remove_cache():
    cache_path = pathlib.Path("./game/cache")
    data_path = pathlib.Path("./game/data")
    gfx_path = pathlib.Path("./game/gfx")
    if cache_path.exists():
        shutil.rmtree(cache_path.absolute())
    if data_path.exists():
        shutil.rmtree(data_path.absolute())
    if gfx_path.exists():
        shutil.rmtree(gfx_path.absolute())


def download_latest_version(releases=None):
    if releases is None:
        releases = get_latest_release()
        success(f"the latest release is released at {releases[0]['published_at']}")
    for release in releases:
        file_name = download_release(release)
        if file_name != "":
            remove_cache()
            unzipfile(file_name)
            success("all done!")
            return
    error("did not find a suitable version to download!")


def check_for_asset(release):
    assets = release["assets"]
    search_str = construct_search_str()
    for asset in assets:
        if asset["name"].startswith(search_str):
            return True
    return False


def check_updates():
    build_number = get_build_number()
    if build_number == "":
        info("did not find VERSION.txt, download the latest release instead.")
        download_latest_version()
        return
    print(f"current build number: {build_number}")
    releases = get_latest_release()
    for release in releases:
        if release["name"].split(" ")[-1] != build_number:
            has_asset = check_for_asset(release)
            if has_asset:
                success(f"get new build version {release['name']}")
                download_latest_version(releases)
                return
        else:
            info("there are no new versions!")
            return


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
