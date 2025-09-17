import logging
import dspy
import os
import json
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

# -------------------- Settings Import Fix ---------------------- #
try:
    from src.config.settings import settings
except ImportError:
    # Fallback settings object if import fails
    class FallbackSettings:
        openai_api_key = os.getenv("OPENAI_API_KEY")
        openai_base_url = os.getenv("OPENAI_BASE_URL")
        openai_model = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        openai_max_tokens = int(os.getenv("OPENAI_MAX_TOKENS", "800"))
        openai_temperature = float(os.getenv("OPENAI_TEMPERATURE", "0.1"))
    
    settings = FallbackSettings()
    logger.warning("Using fallback settings - please check your settings import")

# -------------------- Enhanced DSPy Signatures ---------------------- #
class AdvancedQueryParsingSignature(dspy.Signature):
    """
    Advanced LLM-based parser that intelligently extracts ALL job-related information.
    
    INSTRUCTIONS:
    - Extract ONLY information that is EXPLICITLY mentioned in the query
    - Be smart about context - if user says "IT industry" extract "Information Technology" 
    - If user mentions "highschool" or "bachelor" etc, map to proper education levels
    - For experience, extract number of years if mentioned
    - For location, extract ONLY the geographical location, not industry or education
    - For job title, extract the actual job/position, not location or other details
    - If information is not mentioned, return None
    - Be intelligent about synonyms and variations

    For 'industry', map to valid options:
    - All Industries, Aerospace & Defense, Biotechnology, Construction, Education
    - Energy & Utilities, Financial Services, Government, Healthcare
    - Hospitality & Leisure, Information Technology, Media & Entertainment
    - Manufacturing, Non-profit, Professional Services, Real Estate
    - Retail & Wholesale, Transportation & Logistics
    
    For 'company_size', map to valid ranges:
    - ALL FTEs, <25 FTEs, 25-50 FTEs, 50-100 FTEs, 100-200 FTEs
    - 200-500 FTEs, 500-1,000 FTEs, 1,000-3,000 FTEs, 3,000-7,500 FTEs
    - 7,500-15,000 FTEs, 15,000-50,000 FTEs, >50,000 FTEs

    For 'Education', map to valid options: ['None', 'High School', 'Certificate', 'Associate', "Bachelor's", "Master's", 'MBA', 'JD', 'MD', 'PhD', 'Advanced', 'Doctorate', 'Special Program']
    """
    
    user_query = dspy.InputField(desc="Complete user query containing job search information")
    
    job_title = dspy.OutputField(desc="Extract the job title/position only (e.g., 'HVAC Supervisor', 'Software Engineer')")
    location = dspy.OutputField(desc="Extract ONLY geographical location (city, state, country - e.g., 'Mexico', 'San Francisco')")
    education_level = dspy.OutputField(desc="Extract and normalize education level (e.g., 'High School', 'Bachelor\\'s Degree', 'Master\\'s Degree', 'PhD')")
    years_of_experience = dspy.OutputField(desc="Extract number of years of experience as integer, or None if not mentioned")
    industry_type = dspy.OutputField(desc="Extract and normalize industry (e.g., 'Information Technology', 'Healthcare', 'Finance')")
    company_size_preference = dspy.OutputField(desc="Extract company size preference and normalize to ranges like '<25 FTEs', '50-100 FTEs', etc.")
    certifications = dspy.OutputField(desc="Extract any certifications mentioned, or 'None' if user says no certifications")

class SkipDetectionSignature(dspy.Signature):
    """
    Intelligent skip detection - determine if user wants to use defaults.
    """
    user_response = dspy.InputField(desc="User's response to follow-up questions")
    context = dspy.InputField(desc="What information we were asking for")
    
    wants_to_skip = dspy.OutputField(desc="True if user wants to skip/use defaults, False if providing information")
    reasoning = dspy.OutputField(desc="Brief explanation of the decision")

class FollowUpResponseSignature(dspy.Signature):
    """
    Extract information from follow-up responses intelligently.
        For 'industry', map to valid options:
    - All Industries, Aerospace & Defense, Biotechnology, Construction, Education
    - Energy & Utilities, Financial Services, Government, Healthcare
    - Hospitality & Leisure, Information Technology, Media & Entertainment
    - Manufacturing, Non-profit, Professional Services, Real Estate
    - Retail & Wholesale, Transportation & Logistics
    
    For 'company_size', map to valid ranges:
    - ALL FTEs, <25 FTEs, 25-50 FTEs, 50-100 FTEs, 100-200 FTEs
    - 200-500 FTEs, 500-1,000 FTEs, 1,000-3,000 FTEs, 3,000-7,500 FTEs
    - 7,500-15,000 FTEs, 15,000-50,000 FTEs, >50,000 FTEs

    For 'Education', map to valid options: ['None', 'High School', 'Certificate', 'Associate', "Bachelor's", "Master's", 'MBA', 'JD', 'MD', 'PhD', 'Advanced', 'Doctorate', 'Special Program']

    """
    user_response = dspy.InputField(desc="User's response containing multiple pieces of information")
    missing_fields = dspy.InputField(desc="List of fields we were asking about")
    existing_info = dspy.InputField(desc="Information already collected")
    
    extracted_education = dspy.OutputField(desc="Education level if mentioned, otherwise None")
    extracted_experience = dspy.OutputField(desc="Years of experience if mentioned, otherwise None") 
    extracted_industry = dspy.OutputField(desc="Industry if mentioned, otherwise None")
    extracted_company_size = dspy.OutputField(desc="Company size if mentioned, otherwise None")
    extracted_certifications = dspy.OutputField(desc="Certifications if mentioned, otherwise None")

# -------------------- DSPy Setup with Proper Error Handling ---------------------- #
advanced_parser = None
skip_detector = None
followup_extractor = None

def initialize_llm():
    """Initialize LLM with proper error handling."""
    global advanced_parser, skip_detector, followup_extractor
    
    try:
        # Check for OpenAI API key
        api_key = getattr(settings, 'openai_api_key', None) or os.getenv("OPENAI_API_KEY")
        
        if not api_key:
            logger.warning("No OpenAI API key found - LLM features will be limited")
            return False
        
        base_url = getattr(settings, 'openai_base_url', None) or os.getenv("OPENAI_BASE_URL")
        model = getattr(settings, 'openai_model', 'gpt-3.5-turbo')
        max_tokens = getattr(settings, 'openai_max_tokens', 800)
        temperature = getattr(settings, 'openai_temperature', 0.1)
        
        lm = dspy.LM(
            model=f"openai/{model}",
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature
        )
        dspy.settings.configure(lm=lm)
        
        advanced_parser = dspy.Predict(AdvancedQueryParsingSignature)
        skip_detector = dspy.Predict(SkipDetectionSignature)
        followup_extractor = dspy.Predict(FollowUpResponseSignature)
        
        logger.info(f"✅ Advanced LLM-driven parser configured with {model}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize LLM: {e}")
        return False

# Initialize LLM on module load
llm_available = initialize_llm()

# -------------------- Configuration ---------------------- #
DEFAULT_VALUES = {
    "industry_type": "All Industries",
    "company_size_preference": "50-100 FTEs",
    "education_level": None,
    "years_of_experience": None,
    "certifications": "None"
}

ALL_FIELDS = ["job_title", "location", "education_level", "years_of_experience", "industry_type", "company_size_preference", "certifications"]

# -------------------- Session Management ---------------------- #
_active_sessions = {}

class JobQuerySession:
    def __init__(self):
        self.collected_info = {}
        self.follow_up_asked = False
        self.conversation_finished = False
        
    def apply_defaults_for_missing(self):
        """Apply defaults only for missing fields."""
        logger.info("🎯 APPLYING DEFAULTS FOR MISSING FIELDS")
        
        for field in ALL_FIELDS:
            if field not in self.collected_info or self.collected_info[field] is None:
                if field in DEFAULT_VALUES:
                    self.collected_info[field] = DEFAULT_VALUES[field]
                    logger.info(f"✅ Applied default: {field} = {DEFAULT_VALUES[field]}")
                else:
                    self.collected_info[field] = None
                    logger.info(f"✅ Set to None: {field}")
        
        self.conversation_finished = True
        logger.info("🏁 CONVERSATION MARKED AS FINISHED")

def get_session(session_id: str = "default") -> JobQuerySession:
    if session_id not in _active_sessions:
        _active_sessions[session_id] = JobQuerySession()
        logger.info(f"📝 Created new session: {session_id}")
    return _active_sessions[session_id]

def reset_session(session_id: str = "default"):
    """Reset and remove the session after workflow is complete."""
    if session_id in _active_sessions:
        _active_sessions.pop(session_id, None)
        logger.info(f"🔄 Session '{session_id}' reset after workflow completion")

# -------------------- Fallback Functions ---------------------- #
def extract_with_fallback(query: str) -> Dict[str, Any]:
    """Simple fallback extraction when LLM is not available."""
    logger.info("🔧 Using fallback extraction (no LLM)")
    
    words = query.split()
    
    # Simple job title extraction (first 2-3 words)
    job_title = " ".join(words[:3]).title() if len(words) >= 3 else query.title()
    
    # Simple location extraction (look for "in [location]")
    location = None
    if " in " in query.lower():
        parts = query.lower().split(" in ")
        if len(parts) > 1:
            location_part = parts[1].split()[0]  # Take first word after "in"
            location = location_part.title()
    
    return {
        "job_title": job_title,
        "location": location,
        "education_level": None,
        "years_of_experience": None,
        "industry_type": None,
        "company_size_preference": None,
        "certifications": None
    }

# -------------------- LLM-Driven Functions ---------------------- #
def extract_with_llm(query: str) -> Dict[str, Any]:
    """Use LLM to extract all information intelligently."""
    if not llm_available or not advanced_parser:
        logger.warning("🔥 LLM not available - using fallback")
        return extract_with_fallback(query)
    
    try:
        logger.info(f"🤖 Using LLM to parse: '{query}'")
        
        result = advanced_parser(user_query=query)
        
        extracted = {
            "job_title": clean_text(result.job_title),
            "location": clean_text(result.location),
            "education_level": clean_text(result.education_level),
            "years_of_experience": clean_number(result.years_of_experience),
            "industry_type": clean_text(result.industry_type),
            "company_size_preference": clean_text(result.company_size_preference),
            "certifications": clean_text(result.certifications)
        }
        
        logger.info(f"🎯 LLM extracted: {extracted}")
        return extracted
        
    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return extract_with_fallback(query)

def is_user_skipping_llm(response: str, context: str = "") -> bool:
    """Use LLM to detect skip intent."""
    if not llm_available or not skip_detector:
        # Simple fallback
        skip_words = ["skip", "no", "continue", "default", "pass", "none"]
        return any(word in response.lower() for word in skip_words)
    
    try:
        result = skip_detector(
            user_response=response,
            context=context or "information about your job preferences"
        )
        
        is_skip = result.wants_to_skip.lower() in ["true", "yes", "1"]
        logger.info(f"🧠 LLM skip detection: {is_skip} - {result.reasoning}")
        return is_skip
        
    except Exception as e:
        logger.warning(f"LLM skip detection failed: {e}")
        return "skip" in response.lower() or "default" in response.lower()

def extract_from_followup_llm(response: str, missing_fields: List[str], existing_info: Dict[str, Any]) -> Dict[str, Any]:
    """Use LLM to extract information from follow-up responses."""
    if not llm_available or not followup_extractor:
        return {}
    
    try:
        existing_str = ", ".join([f"{k}: {v}" for k, v in existing_info.items() if v is not None])
        
        result = followup_extractor(
            user_response=response,
            missing_fields=", ".join(missing_fields),
            existing_info=existing_str
        )
        
        extracted = {}
        if result.extracted_education and result.extracted_education.lower() != "none":
            extracted["education_level"] = result.extracted_education
        if result.extracted_experience and result.extracted_experience.lower() != "none":
            try:
                extracted["years_of_experience"] = int(result.extracted_experience)
            except:
                pass
        if result.extracted_industry and result.extracted_industry.lower() != "none":
            extracted["industry_type"] = result.extracted_industry
        if result.extracted_company_size and result.extracted_company_size.lower() != "none":
            extracted["company_size_preference"] = result.extracted_company_size
        if result.extracted_certifications and result.extracted_certifications.lower() != "none":
            extracted["certifications"] = result.extracted_certifications
        
        logger.info(f"🎯 Follow-up extraction: {extracted}")
        return extracted
        
    except Exception as e:
        logger.warning(f"Follow-up extraction failed: {e}")
        return {}

def clean_text(text: Optional[str]) -> Optional[str]:
    """Clean text output."""
    if not text or text.lower().strip() in ["none", "n/a", "unknown", "not specified", "null", ""]:
        return None
    return text.strip()

def clean_number(text: Optional[str]) -> Optional[int]:
    """Clean number output."""
    if not text:
        return None
    try:
        return int(str(text).strip())
    except:
        return None

# -------------------- Main Parser Function ---------------------- #
def parse_job_query(query: str, session_id: str = "default", is_followup: bool = False) -> Dict[str, Any]:
    """
    FULLY LLM-DRIVEN PARSING with proper fallbacks.
    """
    logger.info(f"🚀 PARSING: '{query}' (followup: {is_followup}, LLM: {llm_available})")
    
    session = get_session(session_id)
    
    # Handle follow-up responses
    if is_followup:
        logger.info("📥 Processing follow-up")
        
        missing_context = f"your {', '.join([f for f in ALL_FIELDS if session.collected_info.get(f) is None])}"
        
        if is_user_skipping_llm(query, missing_context):
            logger.info("🎯 Skip detected - applying defaults")
            session.apply_defaults_for_missing()
            
            return {
                "is_valid": True,
                "job_title": session.collected_info.get("job_title", "Any Position"),
                "location": session.collected_info.get("location", "Any Location"),
                "education_level": session.collected_info.get("education_level"),
                "experience_years": session.collected_info.get("years_of_experience"),
                "industry_name": session.collected_info.get("industry_type"),
                "company_size": session.collected_info.get("company_size_preference"),
                "certification_name": session.collected_info.get("certifications"),
                "confidence": 100.0,
                "message": "Perfect! I'll search for jobs using your preferences and defaults.",
                "missing_fields": [],
                "follow_up_question": None
            }
        else:
            # Extract using available method
            missing_fields = [f for f in ALL_FIELDS if session.collected_info.get(f) is None]
            followup_info = extract_from_followup_llm(query, missing_fields, session.collected_info)
            
            # Update session
            for key, value in followup_info.items():
                if value is not None:
                    session.collected_info[key] = value
                    logger.info(f"📝 Updated: {key} = {value}")
            
            # Apply defaults for remaining
            session.apply_defaults_for_missing()
            
            return {
                "is_valid": True,
                "job_title": session.collected_info.get("job_title", "Any Position"),
                "location": session.collected_info.get("location", "Any Location"),
                "education_level": session.collected_info.get("education_level"),
                "experience_years": session.collected_info.get("years_of_experience"),
                "industry_name": session.collected_info.get("industry_type"),
                "company_size": session.collected_info.get("company_size_preference"),
                "certification_name": session.collected_info.get("certifications"),
                "confidence": 100.0,
                "message": "Great! I have processed your information.",
                "missing_fields": [],
                "follow_up_question": None
            }
    
    # Initial query processing
    logger.info("🎯 Processing initial query")
    
    extracted_info = extract_with_llm(query)
    
    # Update session
    for key, value in extracted_info.items():
        if value is not None:
            session.collected_info[key] = value
            logger.info(f"📝 Extracted: {key} = {value}")
    
    # Check missing fields
    missing_fields = [f for f in ALL_FIELDS if session.collected_info.get(f) is None]
    important_missing = [f for f in missing_fields if f not in ["job_title", "location"]]
    
    # Ask follow-up if needed
    if session.collected_info.get("job_title") and important_missing and not session.follow_up_asked:
        session.follow_up_asked = True
        
        field_names = {
            "education_level": "educational background",
            "years_of_experience": "years of experience",
            "industry_type": "industry preference", 
            "company_size_preference": "company size preference",
            "certifications": "certifications"
        }
        
        missing_names = [field_names.get(f, f.replace('_', ' ')) for f in important_missing[:4]]
        
        if len(missing_names) == 1:
            question = f"Could you please share your {missing_names[0]}?"
        elif len(missing_names) == 2:
            question = f"Could you please share your {missing_names[0]} and {missing_names[1]}?"
        else:
            question = f"Could you please share your {', '.join(missing_names[:-1])}, and {missing_names[-1]}?"
        
        question += "\n\n(You can say 'skip', 'no', 'continue', or 'default' for any field you want to use our defaults for)"
        
        return {
            "is_valid": False,
            "job_title": session.collected_info.get("job_title"),
            "location": session.collected_info.get("location"),
            "education_level": session.collected_info.get("education_level"),
            "experience_years": session.collected_info.get("years_of_experience"),
            "industry_name": session.collected_info.get("industry_type"),
            "company_size": session.collected_info.get("company_size_preference"),
            "certification_name": session.collected_info.get("certifications"),
            "confidence": 50.0,
            "message": question,
            "missing_fields": important_missing,
            "follow_up_question": question
        }
    
    # Complete with defaults
    session.apply_defaults_for_missing()
    
    return {
        "is_valid": True,
        "job_title": session.collected_info.get("job_title", "Any Position"),
        "location": session.collected_info.get("location", "Any Location"),
        "education_level": session.collected_info.get("education_level"),
        "experience_years": session.collected_info.get("years_of_experience"),
        "industry_name": session.collected_info.get("industry_type"),
        "company_size": session.collected_info.get("company_size_preference"),
        "certification_name": session.collected_info.get("certifications"),
        "confidence": 100.0,
        "message": "Ready to search for jobs!",
        "missing_fields": [],
        "follow_up_question": None
    }

# -------------------- Backward Compatibility ---------------------- #
def parse_and_validate_query(query: str, session=None, is_follow_up_response: bool = False) -> Dict[str, Any]:
    session_id = "default" if session is None else str(id(session))
    return parse_job_query(query, session_id, is_follow_up_response)

def parse_and_validate_with_optional_prompts(query: str, session=None, is_follow_up_response: bool = False) -> Dict[str, Any]:
    return parse_and_validate_query(query, session, is_follow_up_response)

# -------------------- Test Function ---------------------- #
def test_parser():
    """Test the parser functionality."""
    print(f"LLM Available: {llm_available}")
    
    test_queries = [
        "HVAC Supervisor in Mexico it industry highschool degree",
        "software engineer in new york",
        "data scientist with 5 years experience"
    ]
    
    for query in test_queries:
        print(f"\nTesting: {query}")
        result = parse_job_query(query)
        print(f"Result: {result}")

if __name__ == "__main__":
    test_parser()
