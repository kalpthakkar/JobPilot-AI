# modules/core/test.py
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
        
        print("""
        Set State: (1) Description, (2) Auth, (3) Logged, (4) Submitted
        Quit: N
        """)
        user_input_response = str(input("Press any other key to skip (execute as default)..."))
        if user_input_response.lower() == 'n':
            return 'Job Terminated through User Input'
        
        start_time = time.time() # Capture start time
        logger.info(f"🔁 Iteration {iteration + 1} Starts")

        # Parse the webpage
        interactor.parse_page()

        # [Only for Development] Save the parsed result to a JSON file - Initial parsing
        interactor.save_parsed_data(file_num)

        # Set form state using FormState(Enum) -> (DESCRIPTION_PAGE, AUTH_PAGE, LOGGED_IN, FORM_SUBMITTED)
        if user_input_response == '1':
            interactor.form_state = FormState.DESCRIPTION_PAGE
        elif user_input_response == '2':
            interactor.form_state = FormState.AUTH_PAGE
        elif user_input_response == '3':
            interactor.form_state = FormState.LOGGED_IN
        elif user_input_response == '4':
            interactor.form_state = FormState.FORM_SUBMITTED
        else:
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
        duration = time.time() - start_time # # Compute end time 
        formatted_duration = time.strftime("%H:%M:%S", time.gmtime(duration))
        print(f"""
              Time Taken: {formatted_duration}.{int((duration % 1) * 1000):03d}
        """)
    
    logger.error("❌ Job failed: Max attempts or timeout exceeded.")
    driver.quit()
    return False

# This block allows running the script directly for testing, but main.py should call start()
if __name__ == "__main__":
    test_url = f"https://nordstrom.wd501.myworkdayjobs.com/nordstrom_careers/job/Seattle-WA/Data-Engineer---Insights-Delivery-Team---Hybrid---Seattle_R-752290-1?jr_id=683f9c3079c6e91d4dd90bbf"
    data = run_job(test_url)
    print(data)
