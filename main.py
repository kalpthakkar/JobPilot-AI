# main.py
import config.env_config as env_config
from modules.utils.logger_config import setup_logger
from modules.embeddings import set_hash_file, run_embedding
from config.blacklist import exclude_embedding_keys
from modules.core.job_manager import start_scheduler

logger = setup_logger("JobPilotMain", level=env_config.LOG_LEVEL, log_to_file=False)

def main():

    set_hash_file(env_config.HASH_FILE)
    run_embedding(env_config.USER_JSON_FILE, env_config.CHROMA_DB_DIR, env_config.EMBED_MODEL, env_config.EMBED_COLLECTION_NAME, exclude_keys=exclude_embedding_keys)

    start_scheduler()

    print('✅ Done')

if __name__ == "__main__":
    main()