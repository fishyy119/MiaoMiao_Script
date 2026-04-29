from pathlib import Path
import sys


SCRAPER_DIR = Path(__file__).resolve().parent
scraper_dir_str = str(SCRAPER_DIR)

if scraper_dir_str not in sys.path:
    sys.path.insert(0, scraper_dir_str)
