"""
Query parsing and validation utilities for job search queries.
Handles DSPy-based parsing, validation, and error handling.
"""

import logging
import dspy
import os
from typing import Dict, Any, Optional, List
from pydantic import BaseModel
from config.settings import settings

logger = logging.getLogger(__name__)

# -------------------- DSPy Signature ----------------------- #
class QueryValidationSignature(dspy.Signature):
    """
    Given a job search query, extract the job title and the location (city or region).
    Examples:
    - Query: "HVAC service manager in Seattle"
      job_title: "HVAC Service Manager"
      location: "Seattle"
    """
    query = dspy.InputField(desc="Job query (e.g., 'HVAC technician in Seattle')")
    job_title = dspy.OutputField(desc="Extracted job title, e.g., 'HVAC Technician'")
    location = dspy.OutputField(desc="Extracted location, e.g., 'Seattle'")
    is_valid = dspy.OutputField(desc="True if job title and location are both valid")
    confidence = dspy.OutputField(desc="Confidence score (0 to 100)")

# ------------------ DSPy Setup ----------------------------- #
query_validator = None
try:
    # Try OpenAI first (only use settings, no os.getenv fallback)
    if settings.openai_api_key:
        api_key = settings.openai_api_key
        base_url = settings.openai_base_url
        
        # Configure OpenAI with DSPy using the correct format
        lm = dspy.LM(
            model=f"openai/{settings.openai_model}",
            api_key=api_key,
            base_url=base_url,
            max_tokens=settings.openai_max_tokens,
            temperature=settings.openai_temperature
        )
        dspy.settings.configure(lm=lm)
        query_validator = dspy.Predict(QueryValidationSignature)
        logger.info(f"✅ DSPy + OpenAI {settings.openai_model} configured")
    
    # Fallback to Ollama if OpenAI is not available
    elif not settings.openai_api_key:
        lm = dspy.LM(
            model=settings.ollama_model, 
            base_url=settings.ollama_base_url, 
            max_tokens=settings.ollama_max_tokens
        )
        dspy.settings.configure(lm=lm)
        query_validator = dspy.Predict(QueryValidationSignature)
        logger.info("✅ DSPy + Llama3.2 configured (fallback)")
        
except Exception as e:
    logger.warning(f"⚠️ DSPy not available: {e}")

# -------------------- Pydantic Models ---------------------- #
class QueryValidationResponse(BaseModel):
    is_valid: bool
    job_title: Optional[str]
    location: Optional[str]
    confidence: float = 0.0
    message: str = ""
    suggestions: List[str] = []

# ---------------------- Helper Functions ------------------- #
def clean(text: Optional[str]) -> Optional[str]:
    """Clean and normalize extracted text."""
    if not text or text.lower() in {"none", "n/a", "unknown", "not specified"}:
        return None
    return text.strip().title()

def detect_multiple_items(text: str, item_type: str) -> bool:
    """Detect if multiple items are present in the text."""
    text_lower = text.lower()
    if item_type == "location":
        # Split on ' in ' and check the right side for multiple locations
        if " in " in text_lower:
            location_part = text_lower.split(" in ", 1)[1]
            for sep in [" and ", " or ", " & ", ",", ";", " / ", " \\" ]:
                if sep in location_part:
                    return True
        return False
    elif item_type == "job_title":
        # Check the left side of ' in '
        if " in " in text_lower:
            job_part = text_lower.split(" in ", 1)[0]
            for sep in [" and ", " or ", " & ", ",", ";", " / "]:
                if sep in job_part:
                    return True
        return False
    return False

def validate_query_structure(query: str) -> Dict[str, Any]:
    """Pre-validate query structure before DSPy processing."""
    query = query.strip()
    
    # Check for empty query
    if not query:
        return {
            "is_valid": False,
            "message": "Please enter a valid query with both job title and location",
            "suggestions": ["Try: 'Software Engineer in New York'", "Try: 'Marketing Manager in Los Angeles'"]
        }
    
    # Check for non-job-search queries (questions about general topics, not job-related)
    query_lower = query.lower()
    non_job_keywords = [
        "cost of living", "housing cost", "rent", "weather",
        "population", "demographics", "crime rate", "schools", "education",
        "transportation", "culture", "food", "restaurants", "nightlife",
        "tourism", "attractions", "shopping", "entertainment"
    ]
    
    # Only reject if it contains non-job keywords AND doesn't contain job-related terms
    job_related_terms = [
        "salary", "pay", "wage", "income", "benefits", "job", "career", 
        "position", "role", "employment", "work", "hire", "hiring"
    ]
    
    has_non_job_keywords = any(keyword in query_lower for keyword in non_job_keywords)
    has_job_related_terms = any(term in query_lower for term in job_related_terms)
    
    if has_non_job_keywords and not has_job_related_terms:
        return {
            "is_valid": False,
            "message": "This appears to be a general question rather than a job search query",
            "suggestions": [
                "For job searches, try: 'Software Engineer in New York'",
                "Format: '[Job Title] in [Location]'",
                "Example: 'Marketing Manager in Los Angeles'"
            ]
        }
    
    # Check for multiple locations
    if detect_multiple_items(query, "location"):
        return {
            "is_valid": False,
            "message": "Multiple locations detected. Please enter only one location at a time",
            "suggestions": ["Try: 'Software Engineer in New York' (single location)", 
                          "Submit separate queries for each location"]
        }
    
    # Check for multiple job titles
    if detect_multiple_items(query, "job_title"):
        return {
            "is_valid": False,
            "message": "Multiple job titles detected. Please enter only one job title at a time",
            "suggestions": ["Try: 'Software Engineer in New York' (single job title)", 
                          "Submit separate queries for each job role"]
        }
    
    return {"is_valid": True}

def validate_extracted_fields(query: str, job_title: Optional[str], location: Optional[str]) -> Dict[str, Any]:
    """Validate that extracted fields actually exist in the original query."""
    query_lower = query.lower()
    
    # Check if the extracted job title actually appears in the query
    if job_title:
        job_title_words = job_title.lower().split()
        # Check if most words of the job title appear in the query
        matching_words = sum(1 for word in job_title_words if word in query_lower)
        
        # If less than half the job title words appear in query, it's likely hallucinated
        if len(job_title_words) > 1 and matching_words < len(job_title_words) / 2:
            return {
                "is_valid": False,
                "extracted_job_title": None,  # Mark as invalid
                "extracted_location": location,
                "message": "Extracted job title doesn't match the query content"
            }
        # For single word job titles, be more strict
        elif len(job_title_words) == 1 and job_title_words[0] not in query_lower:
            return {
                "is_valid": False,
                "extracted_job_title": None,  # Mark as invalid
                "extracted_location": location,
                "message": "Extracted job title doesn't match the query content"
            }
    
    return {
        "is_valid": True,
        "extracted_job_title": job_title,
        "extracted_location": location
    }

def determine_missing_fields(job_title: Optional[str], location: Optional[str]) -> Dict[str, Any]:
    """Determine which required fields are missing and provide appropriate error messages."""
    missing_fields = []
    
    if not job_title:
        missing_fields.append("job title")
    if not location:
        missing_fields.append("location")
    
    if missing_fields:
        if len(missing_fields) == 2:
            message = "Missing required fields: job title and location"
            suggestions = [
                "Try: 'Software Engineer in New York'",
                "Try: 'Marketing Manager in Los Angeles'",
                "Format: '[Job Title] in [Location]'"
            ]
        elif "job title" in missing_fields:
            message = "Missing required field: job title"
            suggestions = [
                "Please specify the job title you're looking for",
                "Try: 'Software Engineer in New York'",
                "Format: '[Job Title] in [Location]'"
            ]
        else:  # location missing
            message = "Missing required field: location"
            suggestions = [
                "Please specify the location where you want to work",
                "Try: 'Software Engineer in New York'",
                "Format: '[Job Title] in [Location]'"
            ]
        
        return {
            "is_valid": False,
            "message": message,
            "suggestions": suggestions
        }
    
    return {"is_valid": True}

# ---------------------- Main Parsing Function ---------------------- #
def parse_and_validate_query(query: str) -> Dict[str, Any]:
    """
    Main function to parse and validate a job search query.
    
    Args:
        query (str): The job search query to parse
        
    Returns:
        Dict[str, Any]: Parsing result with validation status, extracted fields, and messages
    """
    logger.info(f"🧪 Parsing query: '{query}'")
    
    # Pre-validation for query structure
    structure_validation = validate_query_structure(query)
    if not structure_validation["is_valid"]:
        logger.warning(f"⚠️ Query structure validation failed: {structure_validation['message']}")
        return {
            "is_valid": False,
            "job_title": None,
            "location": None,
            "confidence": 0.0,
            "message": structure_validation["message"],
            "suggestions": structure_validation["suggestions"]
        }

    if query_validator:
        try:
            result = query_validator(query=query)
            job_title = clean(result.job_title)
            location = clean(result.location)

            # Validate that extracted fields actually exist in the original query
            field_validation = validate_extracted_fields(query, job_title, location)
            if not field_validation["is_valid"]:
                logger.warning(f"⚠️ Extracted fields validation failed: {field_validation['message']}")
                # Use the corrected fields from validation
                job_title = field_validation["extracted_job_title"]
                location = field_validation["extracted_location"]

            # Check for missing required fields
            missing_fields_validation = determine_missing_fields(job_title, location)
            if not missing_fields_validation["is_valid"]:
                logger.warning(f"⚠️ Missing required fields validation failed: {missing_fields_validation['message']}")
                return {
                    "is_valid": False,
                    "job_title": job_title,
                    "location": location,
                    "confidence": 0.0,
                    "message": missing_fields_validation["message"],
                    "suggestions": missing_fields_validation["suggestions"]
                }

            # Existing validation logic for successful extractions
            if job_title and location:
                if len(location) <= 50 and not any(bad in location.lower() for bad in ["various", "including"]):
                    result_data = {
                        "is_valid": True,
                        "job_title": job_title,
                        "location": location,
                        "confidence": float(result.confidence or 80),
                        "message": "Parsed with DSPy"
                    }
                    logger.info(f"✅ DSPy parsed: {result_data}")
                    return result_data
                else:
                    logger.warning(f"⚠️ DSPy location invalid: {location}")
                    return {
                        "is_valid": False,
                        "job_title": job_title,
                        "location": location,
                        "confidence": 0.0,
                        "message": "Invalid location format detected",
                        "suggestions": ["Please specify a single, specific location", 
                                       "Try: 'Software Engineer in Seattle'"]
                    }
            
        except Exception as e:
            logger.warning(f"❌ DSPy parse exception: {e}")

    # If DSPy failed completely
    return {
        "is_valid": False,
        "job_title": None,
        "location": None,
        "confidence": 0.0,
        "message": "Unable to parse query. Please enter a valid query with both job title and location",
        "suggestions": ["Try: 'Software Engineer in New York'", 
                        "Format: '[Job Title] in [Location]'",
                        "Example: 'Marketing Manager in Los Angeles'"]
    }
