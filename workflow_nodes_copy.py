import logging
from typing import Dict, Any
from src.adaptors.mcp_client import get_mcp_client
from src.utils.query_parser import parse_and_validate_query, reset_session
from src.utils.job_structuring import JobStructurer
import asyncio
import dspy

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# -------------------- DSPy Follow-up Signature ----------------------- #
class FollowUpQuestionSignature(dspy.Signature):
    """Generate a follow-up question to get missing information from the user."""
    missing_fields = dspy.InputField(desc="List of fields that need clarification")
    current_query = dspy.InputField(desc="The original user query")
    follow_up_question = dspy.OutputField(desc="Polite follow-up question to get missing information")

# Initialize follow-up question generator
follow_up_generator = None
try:
    if dspy.settings.lm:
        follow_up_generator = dspy.Predict(FollowUpQuestionSignature)
        logger.info("✅ Follow-up question generator configured")
except Exception as e:
    logger.warning(f"⚠️ Follow-up generator not available: {e}")


async def validate_query_node(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("🧪 [validate_query_node] Running with state: %s", state)
    try:
        query = state.get("query", "")
        if not query:
            raise ValueError("Missing 'query' in state")

        logger.info("📤 [validate_query_node] Processing query: %s", query)

        # Use the query parser module to parse and validate the query
        result = parse_and_validate_query(query)
        
        # Ensure is_valid is set to True for successful validation
        if result.get("is_valid") is None:
            result["is_valid"] = True
        
        # Log the validation result
        logger.info("📋 [validate_query_node] Validation result: %s", result)
        logger.info("📋 [validate_query_node] is_valid: %s", result.get("is_valid"))
        
        # Check if we need to ask follow-up questions
        missing_fields = result.get("missing_fields", [])
        if missing_fields and follow_up_generator:
            try:
                follow_up_result = follow_up_generator(
                    missing_fields=", ".join(missing_fields),
                    current_query=query
                )
                result["follow_up_question"] = follow_up_result.follow_up_question
                result["needs_follow_up"] = True
                logger.info("❓ [validate_query_node] Follow-up question generated: %s", result["follow_up_question"])
            except Exception as e:
                logger.warning(f"⚠️ Failed to generate follow-up question: {e}")
                result["follow_up_question"] = f"Please provide the missing information: {', '.join(missing_fields)}"
                result["needs_follow_up"] = True
        
        # Merge the result with the current state
        final_state = {**state, **result}
        logger.info("📋 [validate_query_node] Final state keys: %s", list(final_state.keys()))
        return final_state

    except Exception as e:
        logger.exception("❌ [validate_query_node] Error in validate_query: %s", e)
        return {
            **state,
            "is_valid": False,
            "error": str(e)
        }


async def scrape_node(state: Dict[str, Any]) -> Dict[str, Any]:
    logger.info("🧪 [scrape_node] Running with state: %s", state)
    try:
        mcp = get_mcp_client()
        job_title = state.get("job_title")
        location = state.get("location")
        max_results = state.get("max_results", 10)

        if not job_title or not location:
            raise ValueError("Missing job_title or location")

        logger.info("📤 [scrape_node] Calling scraping.scrape_jobs with job_title='%s', location='%s'", job_title, location)
        result = await mcp.call_server(
            "scraping",
            "scrape_jobs",
            job_title=job_title,
            location=location,
            max_results=max_results
        )
        logger.info("📥 [scrape_node] Scraping result: %s", result)

        return {**state, "scraped_jobs": result.get("jobs", []), "scraping_metadata": result}
    except Exception as e:
        logger.exception("❌ [scrape_node] Error calling scrape_jobs: %s", e)
        return {
            **state,
            "scraped_jobs": [],
            "scraping_error": str(e)
        }

async def bls_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Call the BLS server to search job by title and attach results."""
    logger.info("🧪 [bls_node] Running with state: %s", state)
    try:
        mcp = get_mcp_client()
        title = state.get("job_title")
        location = state.get("location")
        
        if not title:
            raise ValueError("Missing 'job_title' in state for BLS lookup")
        if not location:
            raise ValueError("Missing 'location' in state for BLS lookup")
        
        # Call the combined tool that gets both BLS job data AND PayScale cost of living data
        logger.info("📤 [bls_node] Calling bls.get_job_and_cost_data with title='%s' and location='%s'", title, location)
        result = await mcp.call_server("bls", "get_job_and_cost_data", job_title=title, location=location)
        logger.info("📥 [bls_node] BLS + PayScale combined result: %s", result)
        
        # Debug: Log the exact structure of the result
        logger.info("🔍 [bls_node] Result keys: %s", list(result.keys()) if isinstance(result, dict) else "Not a dict")
        if isinstance(result, dict):
            logger.info("🔍 [bls_node] job_data keys: %s", list(result.get("job_data", {}).keys()) if result.get("job_data") else "No job_data")
            logger.info("🔍 [bls_node] cost_of_living_data keys: %s", list(result.get("cost_of_living_data", {}).keys()) if result.get("cost_of_living_data") else "No cost_of_living_data")
        
        # Extract BLS data from the combined result
        bls_data = result.get("job_data", {})
        payscale_data = result.get("cost_of_living_data", {})
        
        # Debug: Log what we extracted
        logger.info("🔍 [bls_node] Extracted BLS data: %s", "Available" if bls_data else "Not available")
        logger.info("🔍 [bls_node] Extracted PayScale data: %s", "Available" if payscale_data else "Not available")
        
        # Flatten the data structure for easier UI consumption
        # The UI expects bls_result to contain the actual BLS data directly
        flattened_bls_result = {
            "bls_result": bls_data,  # The actual BLS job data
            "payscale_result": payscale_data,  # The actual PayScale cost of living data
            "combined_result": result  # The full combined result for debugging
        }
        
        # Attach both BLS and PayScale data to state
        return {
            **state, 
            "bls_result": flattened_bls_result,
            "payscale_result": payscale_data,  # Also keep it at top level for compatibility
            "combined_result": result
        }
    except Exception as e:
        logger.exception("❌ [bls_node] Error calling BLS + PayScale: %s", e)
        return {**state, "bls_error": str(e)}

async def salary_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Call the salary.com server to get salary compensation data."""
    logger.info("🧪 [salary_node] Running with state: %s", state)
    try:
        mcp = get_mcp_client()
        job_title = state.get("job_title")
        location = state.get("location")
        education_level = state.get("education_level", "Bachelor's")
        experience_years = state.get("experience_years", 5)
        industry_name = state.get("industry_name", "Biotechnology")
        company_size = state.get("company_size", "25 - 50 FTEs")
        certification_name = state.get("certification_name", "AWS Certified Big Data Specialty")

        if not job_title or not location:
            raise ValueError("Missing 'job_title' or 'location' in state for salary lookup")

        logger.info(
            "📤 [salary_node] Calling salary.scrape_salary_compensation with job_title='%s', city='%s', education='%s', experience=%s, industry='%s', company_size='%s', certification='%s'",
            job_title, location, education_level, experience_years, industry_name, company_size, certification_name
        )
        result = await mcp.call_server(
            "salary", 
            "scrape_salary_compensation", 
            job_title=job_title, 
            city=location,
            education_level=education_level,
            experience_years=experience_years,
            industry_name=industry_name,
            company_size=company_size,
            certification_name=certification_name
        )
        logger.info("📥 [salary_node] Salary.com result: %s", result)

        # Attach salary.com data to state
        return {**state, "salary_result": result}
    except Exception as e:
        logger.exception("❌ [salary_node] Error calling salary.com: %s", e)
        return {**state, "salary_error": str(e)}


async def structure_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Structure job data using existing job_structuring methods."""
    logger.info("🧪 [structure_node] Running with state: %s", state)
    try:
        # Get data from all parallel sources
        scraped_jobs = state.get("scraped_jobs", [])
        bls_result = state.get("bls_result", {})
        salary_result = state.get("salary_result", {})
        payscale_result = state.get("payscale_result", {})
        
        # Extract the actual data from nested structures
        actual_bls_data = bls_result
        if isinstance(bls_result, dict) and "bls_result" in bls_result:
            actual_bls_data = bls_result["bls_result"]
        elif isinstance(bls_result, dict) and "job_data" in bls_result:
            actual_bls_data = bls_result["job_data"]
            
        actual_salary_data = salary_result
        if isinstance(salary_result, dict) and "salary_result" in salary_result:
            actual_salary_data = salary_result["salary_result"]
            
        actual_payscale_data = payscale_result
        if isinstance(payscale_result, dict) and "payscale_result" in payscale_result:
            actual_payscale_data = payscale_result["payscale_result"]
        elif isinstance(bls_result, dict) and "cost_of_living_data" in bls_result:
            actual_payscale_data = bls_result["cost_of_living_data"]
        
        # Log what data we received from each source
        logger.info("📊 [structure_node] Received data from parallel sources:")
        logger.info("   - Scraped Jobs: %d", len(scraped_jobs))
        logger.info("   - BLS Result: %s", "Available" if actual_bls_data else "Not available")
        logger.info("   - Salary.com Result: %s", "Available" if actual_salary_data else "Not available")
        logger.info("   - PayScale Cost of Living: %s", "Available" if actual_payscale_data else "Not available")
        
        # Initialize the job structurer
        structurer = JobStructurer()
        
        # Create workflow data structure that the job_structuring methods expect
        # Note: job_structuring.py expects bls_result to have median_pay at top level, not nested in job_data
        flattened_bls_data = actual_bls_data
        if isinstance(actual_bls_data, dict) and actual_bls_data.get("job_data"):
            # Flatten the BLS data structure for job_structuring.py compatibility
            flattened_bls_data = actual_bls_data["job_data"]
            logger.info(f"📤 [structure_node] Flattened BLS data for job_structuring: {flattened_bls_data.get('median_pay', 'No median_pay')}")
        
        workflow_data = {
            "results": {
                "scraped_jobs": scraped_jobs,
                "bls_result": flattened_bls_data,  # Flattened for job_structuring.py compatibility
                "salary_result": actual_salary_data,
                "payscale_result": actual_payscale_data
            }
        }
        
        logger.info("📤 [structure_node] Processing workflow data with job structuring methods")
        
        # Use the existing method to process workflow data to Excel format
        excel_data = structurer.process_workflow_data_to_excel_format(workflow_data)
        
        # Use the existing method to format data for display
        table_data = structurer.format_excel_data_for_display(excel_data)
        
        # Create structured jobs from scraped data using existing method
        structured_jobs = structurer.create_job_data_from_scraped(scraped_jobs)
        
        # Merge all results into state
        result = {
            **state,
            "structured_jobs": [job.__dict__ if hasattr(job, '__dict__') else job for job in structured_jobs],
            "excel_data": excel_data,
            "table_data": table_data,
            "structuring_completed": True,
            "structuring_status": "success",
            "structuring_message": f"Successfully processed {len(excel_data)} records",
            "bls_result": actual_bls_data,
            "salary_result": actual_salary_data,
            "payscale_result": actual_payscale_data
        }
        
        logger.info("📥 [structure_node] Successfully structured data using job_structuring methods")
        logger.info("📊 [structure_node] Excel data rows: %d", len(excel_data))
        logger.info("📊 [structure_node] Table data rows: %d", len(table_data))

        # Reset session after workflow and scraping complete
        session_id = state.get("session_id", "default")
        reset_session(session_id)

        return result
        
    except Exception as e:
        logger.exception("❌ [structure_node] Error structuring job data: %s", e)
        return {
            **state,
            "structured_jobs": [],
            "excel_data": [],
            "table_data": [],
            "structuring_status": "error",
            "structuring_error": str(e),
            "structuring_completed": False
        }



async def parallel_data_collection_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Execute BLS, salary.com, and scraping in parallel using asyncio"""
    logger.info("🚀 [parallel_data_collection_node] Starting parallel data collection")
    logger.info("📋 [parallel_data_collection_node] State keys: %s", list(state.keys()))
    logger.info("📋 [parallel_data_collection_node] is_valid: %s", state.get("is_valid"))
    
    try:
        job_title = state.get("job_title")
        location = state.get("location")
        max_results = state.get("max_results", 10)
        
        if not job_title or not location:
            raise ValueError("Missing 'job_title' or 'location' in state for parallel data collection")
        
        logger.info("📤 [parallel_data_collection_node] Executing in parallel:")
        logger.info("   Job Title: %s", job_title)
        logger.info("   Location: %s", location)
        logger.info("   Data Sources: BLS, Salary.com, Indeed Scraping")
        
        # Execute all three data collection processes in parallel
        logger.info("🔄 [parallel_data_collection_node] Starting parallel execution...")
        
        # Create tasks for parallel execution
        bls_task = bls_node(state)
        salary_task = salary_node(state)
        scrape_task = scrape_node(state)
        
        # Execute all tasks in parallel
        bls_result, salary_result, scrape_result = await asyncio.gather(
            bls_task, 
            salary_task, 
            scrape_task,
            return_exceptions=True
        )
        
        # Handle any exceptions from parallel execution
        if isinstance(bls_result, Exception):
            logger.error("❌ [parallel_data_collection_node] BLS failed: %s", bls_result)
            bls_result = {"bls_error": str(bls_result)}
        
        if isinstance(salary_result, Exception):
            logger.error("❌ [parallel_data_collection_node] Salary.com failed: %s", salary_result)
            salary_result = {"salary_error": str(salary_result)}
        
        if isinstance(scrape_result, Exception):
            logger.error("❌ [parallel_data_collection_node] Scraping failed: %s", scrape_result)
            scrape_result = {"scraping_error": str(scrape_result)}
        
        # Combine all results into the state
        combined_state = {
            **state,
            "bls_result": bls_result,
            "salary_result": salary_result,
            "scraped_jobs": scrape_result.get("scraped_jobs", []),
            "scraping_metadata": scrape_result.get("scraping_metadata", {})
        }
        
        # Debug: Log the BLS result structure
        logger.info("🔍 [parallel_data_collection_node] BLS result keys: %s", list(bls_result.keys()) if isinstance(bls_result, dict) else "Not a dict")
        if isinstance(bls_result, dict):
            logger.info("🔍 [parallel_data_collection_node] BLS result has payscale_result: %s", "payscale_result" in bls_result)
            logger.info("🔍 [parallel_data_collection_node] BLS result has cost_of_living_data: %s", "cost_of_living_data" in bls_result)
            logger.info("🔍 [parallel_data_collection_node] BLS result has combined_result: %s", "combined_result" in bls_result)
        
        # Extract PayScale data from BLS result if available
        if isinstance(bls_result, dict) and "payscale_result" in bls_result:
            combined_state["payscale_result"] = bls_result["payscale_result"]
            logger.info("✅ [parallel_data_collection_node] PayScale data extracted from BLS result")
        elif isinstance(bls_result, dict) and "cost_of_living_data" in bls_result:
            # PayScale data is directly in the BLS result
            combined_state["payscale_result"] = bls_result["cost_of_living_data"]
            logger.info("✅ [parallel_data_collection_node] PayScale data extracted directly from BLS result")
        elif isinstance(bls_result, dict) and "combined_result" in bls_result:
            # If BLS returned combined result, extract PayScale from there
            combined_data = bls_result["combined_result"]
            if "cost_of_living_data" in combined_data:
                combined_state["payscale_result"] = combined_data["cost_of_living_data"]
                logger.info("✅ [parallel_data_collection_node] PayScale data extracted from combined result")
        
        # Also extract PayScale data from the top-level payscale_result if available
        if "payscale_result" in combined_state and combined_state["payscale_result"]:
            logger.info("✅ [parallel_data_collection_node] PayScale data available at top level")
        else:
            logger.info("⚠️ [parallel_data_collection_node] No PayScale data available")
        
        logger.info("✅ [parallel_data_collection_node] Parallel execution completed:")
        logger.info("   - BLS: %s", "Success" if "bls_error" not in bls_result else "Failed")
        logger.info("   - Salary.com: %s", "Success" if "salary_error" not in salary_result else "Failed")
        logger.info("   - Scraping: %d jobs found", len(combined_state.get("scraped_jobs", [])))
        
        # Log PayScale results specifically
        if "payscale_result" in combined_state:
            payscale_data = combined_state["payscale_result"]
            if payscale_data and "success" in payscale_data and payscale_data["success"]:
                logger.info("   - PayScale Cost of Living: Success - %s", payscale_data.get("comparison_to_national", "Data available"))
            else:
                logger.info("   - PayScale Cost of Living: Failed - %s", payscale_data.get("error", "Unknown error") if payscale_data else "No data")
        else:
            logger.info("   - PayScale Cost of Living: Not available")
        
        # Debug: Log final combined state keys
        logger.info("🔍 [parallel_data_collection_node] Final combined state keys: %s", list(combined_state.keys()))
        logger.info("🔍 [parallel_data_collection_node] Final combined state has payscale_result: %s", "payscale_result" in combined_state)
        
        return combined_state
        
    except Exception as e:
        logger.exception("❌ [parallel_data_collection_node] Error in parallel execution: %s", e)
        return {**state, "parallel_error": str(e)}


async def initialize_mcp_client() -> bool:
    logger.info("🔧 Initializing MCP client...")
    try:
        mcp = get_mcp_client()
        # The direct MCP client manager automatically discovers servers on ports 9002, 9003, and 9004
        # No need to manually configure servers
        return await mcp.initialize()
    except Exception as e:
        logger.exception("Failed to set up MCP client: %s", e)
        return False


async def cleanup_mcp_client():
    logger.info("🧼 Cleaning up MCP client...")
    try:
        mcp = get_mcp_client()
        await mcp.close()
    except Exception as e:
        logger.warning("⚠️ MCP client cleanup error: %s", e)
