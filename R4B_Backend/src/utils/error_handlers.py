"""
Centralized error handling utilities for the Job Scraping and Processing System.
"""

import logging
import traceback
from typing import Any, Dict, Optional, Callable
from functools import wraps
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from config.logging_config import get_logger

logger = get_logger(__name__)

class JobScrapingError(Exception):
    """Base exception for job scraping errors."""
    
    def __init__(self, message: str, error_code: str = None, details: Dict[str, Any] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        self.timestamp = datetime.now()

class ScrapingError(JobScrapingError):
    """Exception raised during web scraping operations."""
    pass

class ValidationError(JobScrapingError):
    """Exception raised during data validation."""
    pass

def handle_exceptions(
    error_type: type = JobScrapingError,
    log_error: bool = True,
    reraise: bool = True,
    default_return: Any = None
):
    """
    Decorator to handle exceptions in a consistent way.
    
    Args:
        error_type: Type of exception to catch
        log_error: Whether to log the error
        reraise: Whether to re-raise the exception
        default_return: Default return value if exception occurs
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except error_type as e:
                if log_error:
                    logger.error(
                        f"Error in {func.__name__}: {str(e)}",
                        extra={
                            "function": func.__name__,
                            "error_code": getattr(e, 'error_code', None),
                            "details": getattr(e, 'details', {}),
                            "traceback": traceback.format_exc()
                        }
                    )
                if reraise:
                    raise
                return default_return
            except Exception as e:
                if log_error:
                    logger.error(
                        f"Unexpected error in {func.__name__}: {str(e)}",
                        extra={
                            "function": func.__name__,
                            "traceback": traceback.format_exc()
                        }
                    )
                if reraise:
                    raise JobScrapingError(f"Unexpected error: {str(e)}")
                return default_return
        return wrapper
    return decorator

def retry_on_failure(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    Decorator to retry function on failure.
    
    Args:
        max_retries: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff_factor: Factor to multiply delay by on each retry
        exceptions: Tuple of exceptions to catch and retry
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            
            last_exception = None
            current_delay = delay
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1} failed for {func.__name__}: {str(e)}. "
                            f"Retrying in {current_delay} seconds..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            f"All {max_retries + 1} attempts failed for {func.__name__}: {str(e)}"
                        )
                        raise last_exception
        return wrapper
    return decorator

def log_execution_time(func: Callable) -> Callable:
    """Decorator to log function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.info(f"{func.__name__} executed successfully in {execution_time:.2f} seconds")
            return result
        except Exception as e:
            execution_time = (datetime.now() - start_time).total_seconds()
            logger.error(f"{func.__name__} failed after {execution_time:.2f} seconds: {str(e)}")
            raise
    return wrapper

def create_error_response(
    error: Exception,
    status_code: int = 500,
    include_traceback: bool = False
) -> Dict[str, Any]:
    """
    Create a standardized error response.
    
    Args:
        error: The exception that occurred
        status_code: HTTP status code
        include_traceback: Whether to include traceback in response
        
    Returns:
        Standardized error response dictionary
    """
    response = {
        "error": True,
        "message": str(error),
        "status_code": status_code,
        "timestamp": datetime.now().isoformat(),
        "error_type": type(error).__name__
    }
    
    if hasattr(error, 'error_code'):
        response["error_code"] = error.error_code
    
    if hasattr(error, 'details'):
        response["details"] = error.details
    
    if include_traceback:
        response["traceback"] = traceback.format_exc()
    
    return response


