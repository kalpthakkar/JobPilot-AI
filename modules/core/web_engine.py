# modules/core/web_engine.py
import time
# Modules Import
from modules.core.browser import Browser
from modules.core.web_interactor import WebPageInteractor, FormState
from modules.utils.logger_config import setup_logger
from config.env_config import LOG_LEVEL

logger = setup_logger(__name__, level=LOG_LEVEL, log_to_file=False)

MAX_DURATION: int = 1 * 1 * 30 * 60  # day(s), hour(s), minute(s), second(s), 
MAX_ITERATIONS: int = 18

def run_job(JOB_URL: str):

    # Capture start time
    start_time = time.time()

    # Set up browser and open job application page
    browser = Browser()
    driver = browser.driver
    browser.open_page(JOB_URL)

    # Initialize modules
    interactor = WebPageInteractor(driver, browser)
    interactor.WebParserUtils.wait_for_stable_dom()

    # Processing
    file_num = 0

    # Controlled loop
    for iteration in range(MAX_ITERATIONS):

        elapsed_time = time.time() - start_time
        if elapsed_time > MAX_DURATION:
            logger.warning(f"⏱️ Max runtime of {MAX_DURATION} seconds exceeded.")
            break

        logger.info(f"🔁 Iteration {iteration + 1} | Elapsed: {time.strftime("%H:%M:%S", time.gmtime(elapsed_time))}")

        # Parse the webpage
        interactor.parse_page()

        # [Only for Development] Save the parsed result to a JSON file - Initial parsing
        interactor.save_parsed_data(file_num)

        # Set form state using FormState(Enum) -> (DESCRIPTION_PAGE, AUTH_PAGE, LOGGED_IN, FORM_SUBMITTED)
        interactor.set_state()
        if interactor.form_state == FormState.FORM_SUBMITTED: # Check if form was submitted
            logger.info("🌟  Form successfully submitted.")
            driver.quit()
            return True

        # Expand relevant sections on webpage
        if interactor.form_state == FormState.LOGGED_IN:
            interactor.expand_sections()

        # Resolve extracted fields/buttons/links
        if not interactor.resolve_parsed_data():    # Resolution response
            logger.warning("⚠️  Could not resolve the job. Aborting.")
            driver.quit()   
            return False
        
        file_num += 1
        # response = input("Press Y to parse N to exit...")
        # if response == 'N': break
        # else: file_num += 1
    
    logger.error("❌ Job failed: Max attempts or timeout exceeded.")
    driver.quit()
    return False

# This block allows running the script directly for testing, but main.py should call start()
if __name__ == "__main__":
    test_url = "https://example.com/job"
    data = run_job(test_url)
    print(data)
