import re
import time
import fc
import click
from scrape import Scrape
from loguru import logger


@click.command()
@click.option('--link', default="", help='Category Url.')
def run(link):
    logger.add("./log/log_{time}.txt", level="WARNING", format='{message}')

    if link:
        scrape_obj = Scrape(link)
        scrape_obj.run()
    else:
        logger.error('Category link and Parent category ID is empty')
        logger.info('--help         Show param help.')
        exit(-1)


if __name__ == '__main__':
    run()
