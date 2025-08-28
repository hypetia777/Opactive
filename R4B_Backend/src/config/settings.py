"""Unified Pydantic Settings for the Job Data Processor (Pydantic v2 compatible)"""

try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings
from pydantic import Field
from pathlib import Path
from typing import Optional


class Settings(BaseSettings):
    # OpenAI Configuration (from .env - api_key optional for Ollama fallback)
    openai_api_key: Optional[str] = Field(None, description="OpenAI API key")
    openai_model: str = Field(..., description="OpenAI model to use")
    openai_base_url: Optional[str] = Field(None, description="OpenAI base URL override")
    openai_max_tokens: int = Field(..., description="OpenAI max tokens per request")
    openai_temperature: float = Field(..., description="OpenAI temperature setting")

    # Salary.com Credentials (from .env - required for salary scraping)
    salary_com_username: str = Field(..., description="Salary.com username")
    salary_com_password: str = Field(..., description="Salary.com password")
    
    # CAPTCHA API Key (from .env - required for scraping)
    apikey_2captcha: str = Field(..., description="2captcha API key")

    # MCP Server Configuration (from .env - all required)
    mcp_scraping_server_port: int = Field(..., description="Scraping MCP server port")
    mcp_bls_server_port: int = Field(..., description="BLS MCP server port")
    mcp_salary_server_port: int = Field(..., description="Salary MCP server port")
    mcp_server_bind_host: str = Field(..., description="MCP server binding host (0.0.0.0 for all interfaces)")
    # mcp_server_external_host: str = Field(..., description="MCP server external host for client connections")
    mcp_bls_host: str = Field(..., description="BLS server host for client connections")
    mcp_salary_host: str = Field(..., description="Salary server host for client connections")
    mcp_scraping_host: str = Field(..., description="Scraping server host for client connections")
    
    # MCP Client Timeout Configuration (from .env - for long operations like Salary.com)
    mcp_client_timeout: int = Field(..., description="MCP client total timeout in seconds")
    mcp_connection_timeout: int = Field(..., description="MCP client connection timeout in seconds") 
    mcp_read_timeout: int = Field(..., description="MCP client read timeout in seconds")
    
    # Ollama Configuration (from .env - fallback when OpenAI unavailable)
    ollama_base_url: str = Field(..., description="Ollama server base URL")
    ollama_model: str = Field(..., description="Ollama model to use")
    ollama_max_tokens: int = Field(..., description="Ollama max tokens per request")

    # External Service URLs (from .env - all required)
    indeed_base_url: str = Field(..., description="Indeed website base URL")
    salary_com_login_url: str = Field(..., description="Salary.com login URL")
    captcha_2captcha_submit_url: str = Field(..., description="2captcha submit URL")
    captcha_2captcha_result_url: str = Field(..., description="2captcha result URL")
    
    # FastAPI Server Configuration (from .env)
    fastapi_bind_host: str = Field(..., description="FastAPI server binding host (0.0.0.0 for all interfaces)")
    fastapi_port: int = Field(..., description="FastAPI server port")
    
    # FastAPI Client Configuration (from .env) 
    fastapi_external_host: str = Field(..., description="FastAPI external host for client connections")
    
    @property
    def fastapi_backend_url(self) -> str:
        """Dynamically construct backend URL from external host and port"""
        return f"http://{self.fastapi_external_host}:{self.fastapi_port}"
    
    # Streamlit Configuration (from .env)
    streamlit_host: str = Field(..., description="Streamlit server host")
    streamlit_port: int = Field(..., description="Streamlit server port")

    # Logging Configuration (from .env)
    log_level: str = Field(..., description="Logging level")
    log_path: str = Field(..., description="Log files directory path")

    # Directory Paths (from .env)
    data_export_path: str = Field(..., description="Data export directory path")
    cache_path: str = Field(..., description="Cache directory path")

    def ensure_directories_exist(self):
        """Ensure required data directories exist."""
        for path in [self.data_export_path, self.cache_path, self.log_path]:
            Path(path).mkdir(parents=True, exist_ok=True)

    class Config:
        # Construct absolute path to .env file relative to this settings.py file
        import os
        from pathlib import Path
        _current_file = Path(__file__).resolve()
        _backend_dir = _current_file.parent.parent.parent  # Go up from src/config/ to R4B_Backend/
        env_file = str(_backend_dir / ".env")
        
        env_file_encoding = "utf-8"
        case_sensitive = False  # Allow both UPPER and lower case env vars
        extra = "ignore"  # Ignore unknown keys for security


# Instantiate and expose globally
settings = Settings()
settings.ensure_directories_exist()

# Optional utility function (legacy compatibility)
def get_settings() -> Settings:
    return settings