# Job Scraping and Processing System

A comprehensive job scraping and processing application with CAPTCHA handling, web interface, and automated workflow processing.

## Project Structure

```
demo/
├── README.md                 # This file
├── requirements.txt          # Python dependencies
├── run_app.py               # Main application launcher
├── captcha_test.py          # CAPTCHA testing and job scraping
├── src/                     # Main application source code
│   ├── api/                 # Web API components
│   │   ├── fastapi_app.py   # FastAPI application
│   │   ├── streamlit_app.py # Streamlit web interface
│   │   └── routes/          # API routes
│   ├── models/              # Data models
│   │   ├── job_data.py      # Job data structures
│   │   └── workflow_state.py # Workflow state management
│   ├── workflows/           # Workflow processing
│   │   ├── job_processing_workflow.py
│   │   └── workflow_nodes.py
│   ├── config/              # Configuration
│   │   ├── settings.py      # Application settings
│   │   └── internal_mapping.py # Job title mappings
│   ├── adaptors/            # MCP adaptors
│   │   ├── mcp_client.py    # MCP client implementation
│   │   └── server_registry.py # Server registry
│   └── mcp_servers/         # MCP servers
│       ├── scraping_server.py # Job scraping server
│       ├── bls_server.py      # BLS data server
│       └── captcha_debug.html # CAPTCHA debugging
└── env/                     # Python virtual environment
```

## Features

- **Job Scraping**: Automated job listing extraction from Indeed with CAPTCHA handling
- **CAPTCHA Solving**: Integration with CapSolver for automated CAPTCHA resolution
- **Web Interface**: Streamlit-based user interface for job search and processing
- **API Backend**: FastAPI backend for data processing and workflow management
- **MCP Servers**: Model Context Protocol servers for scraping and data enrichment
- **Workflow Processing**: Automated job data processing, validation, and parsing
- **AI-Powered Parsing**: OpenAI GPT-4o integration for intelligent query parsing and validation
- **Workflow Processing**: Automated job data processing and validation

## Setup and Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Environment Variables**:
   Set the following environment variables:
   - `CAPSOLVER_API_KEY`: Your CapSolver API key for CAPTCHA solving
   - `OPENAI_API_KEY`: Your OpenAI API key for GPT-4o integration (recommended)
   - `OPENAI_BASE_URL`: Optional custom OpenAI endpoint URL
   - `OPENAI_MODEL`: OpenAI model to use (default: gpt-4o)
   - `OPENAI_MAX_TOKENS`: Maximum tokens for responses (default: 512)
   - `OPENAI_TEMPERATURE`: Response creativity (default: 0.1)

3. **OpenAI Configuration** (Recommended):
   The application now uses OpenAI's GPT-4o for intelligent query parsing and validation. This provides:
   - Better accuracy in extracting job titles and locations
   - Improved understanding of complex queries
   - More reliable validation results
   
   If OpenAI is not configured, the system will fall back to the local Llama 3.2 model.

4. **Run the Application**:
   ```bash
   python run_app.py
   ```

## Usage

### Running the Full Application
The main entry point `run_app.py` launches both the FastAPI backend and Streamlit frontend concurrently.

### Testing CAPTCHA Handling
Use `captcha_test.py` to test CAPTCHA solving functionality on job sites.

### Individual Components
- **FastAPI Backend**: Available at `http://localhost:8000`
- **Streamlit Frontend**: Available at `http://localhost:8501`

## Dependencies

- FastAPI: Web API framework
- Streamlit: Web interface
- Selenium: Web scraping
- BeautifulSoup: HTML parsing
- Pydantic: Data validation
- LangChain: AI workflow processing
- OpenAI: GPT-4o integration for intelligent parsing
- DSPy: AI programming framework
- CapSolver: CAPTCHA solving service

## Architecture

The application follows a modular architecture with:
- **API Layer**: FastAPI for backend services
- **UI Layer**: Streamlit for user interface
- **Processing Layer**: MCP servers for specialized tasks, workflow nodes for parsing and validation
- **AI Layer**: OpenAI GPT-4o integration for intelligent query parsing and validation
- **Data Layer**: Pydantic models for data validation
- **Workflow Layer**: Automated job processing pipelines

## Development

The project is organized to support:
- Easy testing of individual components
- Scalable workflow processing
- Modular CAPTCHA handling
- Extensible MCP server architecture
- AI-powered query parsing and validation
