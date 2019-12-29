import logging
import json
import dateutil.parser as dut_parser
from threading import Lock

logger = logging.getLogger("Curse")


def parse_json(data):
    try:
        return json.loads(data)
    except json.JSONDecodeError as e:
        logger.critical(f"Failed to parse json: {e}")
        exit(1)


def get(http, url, **kwargs):
    response = http.request("GET", url + "?" + "&".join([f"{key}={kwargs[key]}" for key in kwargs]))
    if response.status != 200:
        logger.critical(f"HTTP get failed, got status code {response.status}")
        exit(1)
    return response.data


def post(http, url, body):
    response = http.request("POST", url, body=body, headers={
        "Content-Type": "application/json"
    })
    if response.status != 200:
        logger.critical(f"HTTP post failed, got status code {response.status}")
        exit(1)
    return response.data


class ModIterator:
    def __init__(self, http, game_id, category_id, game_version, batch_size, limit):
        self.current_index = 0
        self.http = http
        self.game_id = game_id
        self.category_id = category_id
        self.game_version = game_version
        self.batch_size = batch_size
        self.limit = limit
        self.lock = Lock()

    def __iter__(self):
        return self

    def __next__(self):
        with self.lock:
            index = self.current_index
            self.current_index += self.batch_size

        if 0 < self.limit <= index:
            logger.debug("Iterator reached limit")
            raise StopIteration

        logger.debug(f"Filling cache with {self.batch_size} mods")
        cache = parse_json(get(self.http, "https://addons-ecs.forgesvc.net/api/v2/addon/search",
                               categoryID=0,
                               # Apparently always 0... the category id we got earlier is the sectionId here
                               gameID=self.game_id,
                               gameVersion=self.game_version,
                               pageSize=self.batch_size,
                               index=index,
                               sectionId=self.category_id))
        if len(cache) == 0:
            logger.debug("All mods drained from iterator")
            raise StopIteration

        if 0 < self.limit < len(cache) + index:
            logger.debug("Cache contains too many mods to respect limit, truncating...")
            cache = cache[:-(len(cache) + index - self.limit)]

        return cache


class CurseModDownloader:
    def __init__(self, http):
        self.http = http

        logger.info("Requesting games from curse")
        games = parse_json(get(self.http, "https://addons-ecs.forgesvc.net/api/v2/game"))

        for game in games:
            logger.debug(f"Found game {game['name']} (slug {game['slug']}) with id {game['id']}")
            if game['slug'] == "minecraft":
                self.game_id = game['id']
                logger.info(f"Found Minecraft with id {self.game_id}")
                break

        logger.info("Requesting categories from curse")
        categories = parse_json(get(self.http, "https://addons-ecs.forgesvc.net/api/v2/category"))
        for category in categories:
            logger.debug(
                f"Found category {category['name']} (slug {category['slug']} with id {category['id']} for "
                f"game {category['gameId']}")
            if category['slug'] == "mc-mods":
                self.mods_category_id = category['id']
                logger.info(f"Found Mods category with id {category['id']}")
                break

    def get_all_mods(self, game_version, batch_size, limit):
        return ModIterator(self.http, self.game_id, self.mods_category_id, game_version, batch_size, limit)

    def get_mods_info(self, mods):
        return parse_json(post(self.http, "https://addons-ecs.forgesvc.net/api/v2/addon",
                               json.dumps([mod['id'] for mod in mods])))

    def get_latest_file(self, game_version, mod):
        all_files = filter(lambda file: game_version in file["gameVersion"], parse_json(
            get(self.http, f"https://addons-ecs.forgesvc.net/api/v2/addon/{mod['id']}/files")))

        latest_date = None
        latest_file = None
        for f in all_files:

            current_date = dut_parser.parse(f['fileDate'])
            if latest_date is None or current_date > latest_date:
                latest_date = current_date
                latest_file = f

        return latest_file
