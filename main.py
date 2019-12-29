import argparse
import curse
import logging
import worker
import urllib3
from multiprocessing import cpu_count


def main():
    http = urllib3.PoolManager(num_pools=512, maxsize=512, block=True)

    cmd_line_parser = argparse.ArgumentParser(description="Batch downloads minecraft mods from curseforge")
    cmd_line_parser.add_argument("game_version", type=str, help="Minecraft version")
    cmd_line_parser.add_argument("--debug", dest="debug", action="store_true", help="Set log level to DEBUG")
    cmd_line_parser.add_argument("--workers", dest="workers", type=int,
                                 help="Number of workers to use for file download", default=int(cpu_count() / 2))
    cmd_line_parser.add_argument("--output", dest="output", type=str,
                                 help="Output directory to store downloaded mods in", default="mods")
    cmd_line_parser.add_argument("--limit", dest="limit", type=int,
                                 help="Maximum amount of mods to download (not equal to files!), defaults to no limit",
                                 default=-1)
    cmd_line_parser.add_argument("--batch-size", dest="batch_size", type=int,
                                 help="Amount of mods to request from curse at once", default=200)

    args = cmd_line_parser.parse_args()
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    curse_dl = curse.CurseModDownloader(http)

    settings = {
        "workers": args.workers,
        "mod_iterator": curse_dl.get_all_mods("1.12.2", args.batch_size, args.limit),
        "downloader": curse_dl,
        "output": args.output,
        "http": http,
        "game_version": args.game_version
    }

    stats = worker.start_workers(settings)
    print("Processing finished:")
    print(f"\tSucceeded: {stats['succeeded']}")
    print(f"\tFailed: {stats['failed']}")
    exit(0 if stats['failed'] == 0 else 1)


if __name__ == "__main__":
    main()
