import os
import shutil
import logging
from generators import init_db, DB_PATH

BASE_DIR = os.path.dirname(__file__)

PURGE_DIRS = [
    os.path.join(BASE_DIR, '__pycache__'),
]

def full_reset():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
    # Remove DB
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        logging.info(f'Removed DB: {DB_PATH}')
    else:
        logging.info('DB file not found; nothing to remove.')
    # Remove __pycache__ folders
    for d in PURGE_DIRS:
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            logging.info(f'Removed cache dir: {d}')
    # Re-init fresh schema
    init_db()
    logging.info('Initialized fresh schema (methods whitelist restored).')
    logging.info('Reset complete. Start bot: python3 run.py')

if __name__ == '__main__':
    full_reset()
