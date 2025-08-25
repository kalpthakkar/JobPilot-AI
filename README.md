# 🚀 JobPilot AI

**JobPilot AI** is a next-generation, AI-powered job application and management platform that automates the end-to-end process of job searching, intelligent application submission, and workflow analytics. It combines state-of-the-art AI, ML, NLP, and cloud technologies to deliver a seamless, highly customizable, and extensible solution for job seekers and recruiters.

---

## 📖 Table of Contents

- [Introduction](#introduction)
- [Features & Capabilities](#features--capabilities)
- [Tech Stack & Architecture](#tech-stack--architecture)
- [How It Works](#how-it-works)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Development & Testing](#development--testing)
- [Docker & Deployment](#docker--deployment)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)
- [Acknowledgements](#acknowledgements)

---

## 📝 Introduction

**JobPilot AI** is designed to be the most advanced and flexible job automation tool available. Unlike other auto job application bots, JobPilot AI leverages deep integration with LLMs, advanced NLP, and analytics to not only automate applications but also optimize, personalize, and track every step of your job search journey.

---

## ✨ Features & Capabilities

- **Automated Job Application**: Automatically fills and submits job applications on various platforms.
- **AI-Powered Data Extraction**: Parses job descriptions, requirements, and company data using NLTK, spaCy, and, advanced AI models.
- **Multi-Platform Support**: Automates applications across multiple job boards and company portals.
- **Gmail API Integration**: Reads and sends emails for application confirmations, follow-ups, and status tracking.
- **Resume & Document Management**: Handles resume uploads and document parsing.
- **Job Queue & Status Tracking**: Manages job application queue, statuses, and results.
- **API Server**: FastAPI-based backend for job management and integration.
- **Cloud-Ready & Scalable**: Deployable on Fly.io, Docker, or any cloud provider.
- **Secure Credential Management**: All sensitive data and API keys are stored in the `.credentials/` folder.
- **Browser Automation**: Supports Chrome and Brave browsers via Selenium and Chromedriver.
- **Logging & Error Handling**: Centralized logging for debugging and monitoring.
- **Dockerized Workflow**: Easy deployment and reproducibility using Docker.
- **Extensible Modules**: Modular design for easy customization and extension.

---

## 🏆 What Sets JobPilot AI Apart?

- **True AI Matching**: Uses embeddings and LLMs (Ollama, GPT-4, etc.) for semantic matching, not just keyword search.
- **Automated Email Handling**: Reads, parses, and sends emails via Gmail API for end-to-end automation.
- **Smart Document Generation**: AI-generated, context-aware resumes and cover letters for each application.
- **Full Analytics Suite**: Built-in dashboards and analytics for tracking, optimizing, and visualizing your job search.
- **Plug-and-Play Extensibility**: Easily add new job boards, models, or analytics modules.
- **Privacy & Security**: Local-first, with all credentials and sensitive data stored securely.
- **Cloud & Local Flexibility**: Run locally, in Docker, or deploy to the cloud with a single command.

---

## 🛠️ Tech Stack & Architecture

### **AI, ML, and NLP**

- **LLMs**: Ollama, GPT-4, GPT-3.5, Llama 2, Mistral, and other open-source models (configurable).
- **LangChain**: For prompt orchestration, chaining, and agent workflows.
- **Embeddings**: Sentence Transformers, OpenAI Embeddings, Ollama Embeddings.
- **NLP**: spaCy, NLTK, HuggingFace Transformers for parsing, entity extraction, and text analytics.
- **Data Science & Analytics**: Pandas, NumPy, Matplotlib, Seaborn, Plotly for data analysis and visualization.
- **Machine Learning**: Scikit-learn for custom ranking, classification, and analytics.

### **Backend**

- **FastAPI**: High-performance API server.
- **Uvicorn**: ASGI server for FastAPI.
- **ChromaDB**: Vector database for storing embeddings and semantic search.
- **SQLite**: Lightweight database for job queue and results.
- **Celery**: (Optional) For background job processing and scheduling.

### **Frontend**

- **React.js**: (Optional, if enabled) For dashboards and analytics UI.
- **Jinja2**: For server-rendered templates (if needed).
- **Plotly Dash**: For interactive analytics dashboards.

### **Automation & Engineering**

- **Selenium**: Browser automation for job application submission.
- **Chromedriver/BraveDriver**: Browser drivers for Chrome and Brave.
- **Requests, BeautifulSoup**: For web scraping and parsing.
- **Makefile**: For workflow automation.

### **Networking & API**

- **Gmail API**: For reading and sending emails (OAuth2 setup in `.credentials/`).
- **RESTful API**: For integration with external tools and services.
- **WebSockets**: (Optional) For real-time updates.

### **Cloud & DevOps**

- **Docker**: Containerization for reproducible environments.
- **Fly.io**: Cloud deployment.
- **GitHub Actions**: CI/CD pipelines.

### **Security**

- **.env & .credentials/**: All secrets, API keys, and OAuth tokens are stored securely and never committed.
- **OAuth2**: For Gmail and other integrations.

---

## ⚙️ How It Works

1. **Configure Environment**: Set up `.env` and user data.
2. **Gmail API Setup**: Place your Gmail OAuth credentials in `.credentials/`.
3. **User Configuration**: Users configure their profiles, job preferences, and upload resumes in `config/user_data.json`.
4. **Queue Jobs**: Add job URLs or descriptions via API, CLI, or UI.
5. **Job Search & Application**:
    - The application searches for jobs based on user-defined criteria.
    - It automatically fills out and submits applications using browser automation.
6. **Automated Application**: Selenium automates browser actions to submit applications.
7. **Data Extraction & Parsing**: Job descriptions and requirements are parsed using AI models to extract relevant information.
8. **Email Handling**: Gmail API reads confirmations, sends follow-ups.
9. **Status Tracking & Management**: The application tracks the status of each job application and provides updates to the user.
10. **Analytics & Insights**: Track outcomes, visualize progress, and optimize strategy.
11. **API Integration**: The backend API allows for integration with other tools and platforms for a seamless workflow.

---

## 📦 Setup & Installation

To get started with **JobPilot AI**, follow these steps:

1. **Clone the repository**:
    ```bash
    git clone https://github.com/kalpthakkar/JobPilot-AI.git
    cd jobpilot_ai
    ```
2. **Python Environment**
    python -m venv venv_jobpilot
    venv_jobpilot\Scripts\activate
2. **Install dependencies**:
    ```bash
    pip install -r [requirements.txt](http://_vscodecontentref_/4)
    ```
3. **Configure environment variables**: Copy `.env.example` to `.env` and update the values as needed.
4. **User Data**: Fill in your details in [user_data.json](http://_vscodecontentref_/8)
    cp [user_data_template.json](http://_vscodecontentref_/6) [user_data.json](http://_vscodecontentref_/7)
5. **Chromedriver**
    Download and place the correct version in config/chromedriver-win64/ or ensure it's in your PATH.
6. **Set up Docker (optional)**: If you prefer using Docker, follow the instructions in the [Docker & Deployment](#docker--deployment) section.
7. **Run the application**:
    ```bash
    uvicorn jobpilot_ai.main:app --reload
    ```
8. **Access the API docs**: Open `http://localhost:8000/docs` in your browser to access the automatically generated API documentation.

📧 Gmail API Setup
1. Go to Google Cloud Console.
2. Create a new project and enable the Gmail API.
3. Create OAuth 2.0 credentials (Desktop app).
4. Download credentials.json and place it in `.credentials/gmail_credentials.json`.
5. On first run, the app will prompt for Gmail authentication and store the token in `.credentials/gmail_token.json`.

---

## ⚙️ Configuration

**JobPilot AI** uses a `config/user_data.json` file for user-specific settings and data. Here's an example of the configuration file:

```json
{
  "user": {
    "name": "John Doe",
    "email": "john.doe@example.com",
    "phone": "+1234567890",
    "resume_path": "/path/to/resume.pdf"
  },
  "job_preferences": {
    "location": "Remote",
    "keywords": ["software engineer", "python", "ai"],
    "excluded_keywords": ["intern", "junior"],
    "salary_min": 60000,
    "salary_max": 120000
  },
  "notifications": {
    "email": true,
    "sms": false
  }
}
```

### Configuration Options

- **user**: Personal information used for job applications.
- **job_preferences**: Criteria for job searches, including location, keywords, and salary range.
- **notifications**: Preferences for receiving notifications about job applications and updates.

---

## 📚 Usage

Once **JobPilot AI** is set up and running, you can use it to automate your job applications. Here's how:

1. **Update your profile**: Make sure your `config/user_data.json` file is up-to-date with your latest information.
2. **Start the application**: Run the application using the command:
    ```bash
    uvicorn jobpilot_ai.main:app --reload
    ```
3. **Access the web interface**: Open your web browser and go to `http://localhost:8000` to access the JobPilot AI interface.
4. **Monitor job applications**: Keep track of your job applications, interviews, and responses all in one place.
5. **Analyze and Optimize**: Use the insights and analytics provided by JobPilot AI to optimize your resume and job applications for better results.

---

## 🧪 Development & Testing

For developers looking to contribute to **JobPilot AI**, here's how you can set up your development environment:

1. **Install development dependencies**:
    ```bash
    pip install -r requirements-dev.txt
    ```
2. **Run tests**:
    ```bash
    pytest
    ```
3. **Linting and formatting**:
    ```bash
    flake8
    black .
    ```
4. **Build and run Docker containers** (for testing Docker setup):
    ```bash
    docker-compose up --build
    ```

---

## 🐳 Docker & Deployment

**JobPilot AI** can be easily deployed using Docker. Here's how to set it up:

1. **Build the Docker image**:
    ```bash
    docker build -t jobpilot_ai .
    ```
2. **Run the Docker container**:
    ```bash
    docker run -d -p 8000:8000 jobpilot_ai
    ```
3. **Access the application**: Open your browser and go to `http://localhost:8000`.

For detailed Docker configuration, refer to the `docker-compose.yml` and `Dockerfile` in the project root.

---

## 🛠 Troubleshooting

- **Common Issues**:
    - If you encounter issues with browser automation, ensure that the correct version of Chromedriver is installed and matches your browser version.
    - For API-related issues, check the logs in the `logs/` directory for more information.
- **Getting Help**:
    - Check the [FAQ](#faq) section for common questions and solutions.
    - For further assistance, consider opening an issue on the [GitHub repository](https://github.com/kalpthakkar/JobPilot-AI/issues).

---

## 🤝 Contributing

We welcome contributions to **JobPilot AI**! To get involved:

1. **Fork the repository** on GitHub.
2. **Create a new branch** for your feature or bugfix:
    ```bash
    git checkout -b feature/my-feature
    ```
3. **Make your changes** and commit them:
    ```bash
    git commit -m "Add my feature"
    ```
4. **Push to your fork** and submit a pull request.

Please ensure your code adheres to the project's coding standards and includes appropriate tests.

---

## 📜 License

**JobPilot AI** is licensed under the MIT License. See the [LICENSE](LICENSE) file for more information.

---

## 🙏 Acknowledgements

- Inspired by the need for efficient and automated job application processes.
- Leveraging modern technologies like LLM, RAG, FastAPI, Selenium, and AI/ML for data extraction and processing.
- Thanks to all contributors and open-source libraries that make this project possible.

---

## 📞 Contact

For any inquiries or support, please contact:

- **Kalp Thakkar** - [kalpthakkar2001@gmail.com](mailto:kalpthakkar2001@gmail.com)
- **GitHub**: [kalpthakkar](https://github.com/kalpthakkar)
- **LinkedIn**: [kalpthakkar](https://www.linkedin.com/in/kalpthakkar)

---

## 📅 Roadmap

Future plans for **JobPilot AI** include:

- Enhanced AI models for better data extraction and parsing.
- Support for more job platforms and application workflows.
- Advanced analytics and reporting features for job seekers.
- Integration with popular CI/CD tools for automated resume and profile updates.

---

## ❓ FAQ

**Q: How do I reset my configuration?**
A: To reset your configuration, delete the `config/user_data.json` file and rename `config/user_data_template.json` to `config/user_data.json`. Then, update the new `user_data.json` file with your details.

**Q: Can I use my own AI models for data extraction?**
A: Yes, **JobPilot AI** supports integration with custom AI models. Refer to the documentation on [extending modules](#extensible-modules) for more information.

**Q: How can I contribute to the project?**
A: We welcome contributions! Please refer to the [Contributing](#contributing) section for details on how to get involved.

**Q: Who do I contact for support?**
A: For support, please contact [kalpthakkar2001@gmail.com](mailto:kalpthakkar2001@gmail.com) or open an issue on the GitHub repository.

---

## Changelog

### v1.0.0

- Initial release of **JobPilot AI** with core features:
    - Automated job application submission
    - AI-powered data extraction from job descriptions
    - Resume and document management
    - Job queue and status tracking
    - FastAPI-based backend API
    - Browser automation using Selenium and Chromedriver
    - Centralized logging and error handling
    - Dockerized workflow for easy deployment
    - Modular design for extensibility

---