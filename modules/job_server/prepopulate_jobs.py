import requests

SERVER_URL = "http://127.0.0.1:8000"  # Change to your deployed URL as needed

job_urls = [
    "https://www.uber.com/global/en/careers/list/140557/",
    f"https://workday.wd5.myworkdayjobs.com/en-US/Workday/job/Israel-Tel-Aviv/Software-Engineer---HiredScore_JR-0096009-2?q=software%20engineer",
]

def load_jobs():
    response = requests.post(
        f"{SERVER_URL}/load-jobs",
        json={"urls": job_urls}
    )
    print("✅ Response:", response.status_code, response.json())

if __name__ == "__main__":
    load_jobs()
