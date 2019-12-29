import threading
import logging
import pathlib
import json
import os
import traceback


def try_download(http, url, file):
    response = http.request("GET", url)
    if response.status != 200:
        return False, f"got bad status code {response.status}"

    try:
        with open(file, "wb") as file:
            file.write(response.data)
        return True, ""
    except IOError as e:
        return False, f"IO error occurred: {e}"


def try_process(logger, mod_info, settings):
    logger.debug(f"Got mod info for mod {mod_info['id']}")
    mod_dir = pathlib.Path(settings['output'], f"{mod_info['id']}-{mod_info['slug']}")
    if not mod_dir.exists():
        mod_dir.mkdir(parents=True)

    with open(mod_dir.joinpath("mod-info.json"), "w") as f:
        json.dump(mod_info, f, indent=4)

    file = settings['downloader'].get_latest_file(settings['game_version'], mod_info)

    mod_file_dir = mod_dir.joinpath(str(file['id']))

    if not mod_file_dir.exists():
        mod_file_dir.mkdir(parents=True)
    mod_jar_file = mod_file_dir.joinpath(file['fileName'])

    if not mod_jar_file.exists():
        ok, err = try_download(settings['http'], file['downloadUrl'], mod_jar_file)
        if not ok:
            logger.error(f"An error occurred downloading and saving from {file['downloadUrl']}: {err}")
            return False
        else:
            mod_json_file = mod_jar_file.with_suffix(".json")
            if not mod_json_file.exists():
                with open(mod_json_file, "w") as f:
                    json.dump(file, f, indent=4)

    return True


def worker_main(i, settings, stats):
    logger = logging.getLogger(f"DownloadWorker{i}")
    logger.info(f"Starting worker {i}")

    try_again = list()

    for mods in settings['mod_iterator']:
        for mod_info in settings['downloader'].get_mods_info(mods):
            if not try_process(logger, mod_info, settings):
                try_again.append({
                    "tries_left": 3,
                    "mod_info": mod_info
                })
            else:
                stats["succeeded"] += 1
        logger.info(f"Worker {i} processed one file batch")

    if len(try_again) > 0:
        logger.info(f"Trying to process {len(try_again)} failed infos again")

        while len(try_again) > 0:
            completely_failed = list()

            for try_info in try_again:
                mod_info = try_info["mod_info"]
                if not try_process(logger, mod_info, settings):
                    try_info["tries_left"] -= 1
                    if try_info["tries_left"] <= 0:
                        logger.error(f"Failed to process mod {mod_info['name']} even after several tries")
                        completely_failed.append(mod_info)
                    else:
                        logger.warning(f"Failed to process mod {mod_info['name']}, {try_info['tries_left']} tries left")
                else:
                    stats["succeeded"] += 1

            for fail in completely_failed:
                try_again.remove(fail)

            stats["failed"] += len(completely_failed)


def worker_wrapper(i, settings, stats):
    # noinspection PyBroadException
    try:
        worker_main(i, settings, stats)
    except BaseException as e:
        logger = logging.getLogger(f"DownloadWorker{i}")
        logger.critical(f"Unhandled exception in worker {i}:\n{traceback.format_exc()}\n{e}")
        os._exit(1)


def start_workers(settings):
    threads = list()

    stats = {
        "succeeded": 0,
        "failed": 0
    }

    for i in range(settings['workers']):
        thread = threading.Thread(name=f"DownloadWorker{i}", target=worker_wrapper, args=(i, settings, stats))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    return stats
