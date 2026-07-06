from config.settings import load_config
from utils.logger import logger


def main():

    config = load_config()

    logger.info("=" * 60)
    logger.info("MarketHunter started")
    logger.info("=" * 60)

    logger.info(config)


if __name__ == "__main__":
    main()