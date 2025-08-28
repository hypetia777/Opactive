import logging
from typing import Dict, Any
from adaptors.mcp_client import get_mcp_client
from utils.query_parser import parse_and_validate_query
from utils.job_structuring import JobStructurer
import asyncio

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


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
        if not title:
            raise ValueError("Missing 'job_title' in state for BLS lookup")
        logger.info("📤 [bls_node] Calling bls.search_job with title='%s'", title)
        result = await mcp.call_server("bls", "search_job", job_title=title)
        logger.info("📥 [bls_node] BLS search result: %s", result)
        # Attach BLS data (e.g., median_pay) into state
        return {**state, "bls_result": result}
    except Exception as e:
        logger.exception("❌ [bls_node] Error calling BLS: %s", e)
        return {**state, "bls_error": str(e)}

async def salary_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Call the salary.com server to get salary compensation data."""
    logger.info("🧪 [salary_node] Running with state: %s", state)
    try:
        mcp = get_mcp_client()
        job_title = state.get("job_title")
        location = state.get("location")
        
        if not job_title or not location:
            raise ValueError("Missing 'job_title' or 'location' in state for salary lookup")
        
        logger.info("📤 [salary_node] Calling salary.scrape_salary_compensation with job_title='%s', city='%s'", job_title, location)
        result = await mcp.call_server(
            "salary", 
            "scrape_salary_compensation", 
            job_title=job_title, 
            city=location
        )
        logger.info("📥 [salary_node] Salary.com result: %s", result)
        
        # Attach salary.com data to state
        return {**state, "salary_result": result}
    except Exception as e:
        logger.exception("❌ [salary_node] Error calling salary.com: %s", e)
        return {**state, "salary_error": str(e)}


async def structure_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Structure job data to match PDF table format with min/max salary columns and experience levels."""
    logger.info("🧪 [structure_node] Running with state: %s", state)
    try:
        # Get data from all parallel sources
        scraped_jobs = state.get("scraped_jobs", [])
        bls_result = state.get("bls_result", {})
        salary_result = state.get("salary_result", {})
        
        # Log what data we received from each source
        logger.info("📊 [structure_node] Received data from parallel sources:")
        logger.info("   - Scraped Jobs: %d", len(scraped_jobs))
        logger.info("   - BLS Result: %s", "Available" if bls_result else "Not available")
        logger.info("   - Salary.com Result: %s", "Available" if salary_result else "Not available")
        
        if not scraped_jobs:
            logger.warning("⚠️ [structure_node] No scraped jobs found in state")
            return {
                **state,
                "structured_jobs": [],
                "structuring_status": "warning",
                "structuring_message": "No jobs to structure"
            }
        
        logger.info("📤 [structure_node] Structuring %d jobs with BLS and salary.com data", len(scraped_jobs))
        
        # Initialize the job structurer
        structurer = JobStructurer()
        
        # Structure the job data with both BLS and salary.com data
        structuring_result = structurer.structure_job_data(scraped_jobs, bls_result, salary_result)
        
        # Create table format for UI display
        table_data = structurer.export_to_table_format(structuring_result["structured_jobs"])
        
        # Merge all results into state
        result = {
            **state,
            **structuring_result,
            "table_data": table_data,
            "structuring_completed": True
        }
        
        logger.info("📥 [structure_node] Successfully structured %d jobs", len(structuring_result["structured_jobs"]))
        logger.info("📊 [structure_node] Summary: %s", structuring_result.get("summary", {}))
        
        return result
        
    except Exception as e:
        logger.exception("❌ [structure_node] Error structuring job data: %s", e)
        return {
            **state,
            "structured_jobs": [],
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
        logger.info("   Data Sources: BLS, Salary.com (Indeed Scraping DISABLED)")
        
        # Execute BLS and Salary.com data collection in parallel (Indeed disabled due to timeout issues)
        logger.info("🔄 [parallel_data_collection_node] Starting parallel execution...")
        
        # Create tasks for parallel execution
        bls_task = bls_node(state)
        salary_task = salary_node(state)
        # scrape_task = scrape_node(state)  # COMMENTED OUT - causing timeout issues
        
        # Execute all tasks in parallel
        # ORIGINAL: Execute all three including Indeed scraping
        # bls_result, salary_result, scrape_result = await asyncio.gather(
        #     bls_task, 
        #     salary_task, 
        #     scrape_task,
        #     return_exceptions=True
        # )
        
        # TEMPORARY: Execute only BLS and Salary.com (Indeed disabled due to timeout)
        bls_result, salary_result = await asyncio.gather(
            bls_task, 
            salary_task,
            return_exceptions=True
        )
        
        # TEMPORARY: Set empty scraping result since Indeed is disabled
        scrape_result = {
            "scraped_jobs": [],
            "scraping_metadata": {"status": "disabled", "message": "Indeed scraping temporarily disabled due to timeout issues"}
        }
        
        # Handle any exceptions from parallel execution
        if isinstance(bls_result, Exception):
            logger.error("❌ [parallel_data_collection_node] BLS failed: %s", bls_result)
            bls_result = {"bls_error": str(bls_result)}
        
        if isinstance(salary_result, Exception):
            logger.error("❌ [parallel_data_collection_node] Salary.com failed: %s", salary_result)
            salary_result = {"salary_error": str(salary_result)}
        
        # ORIGINAL: Handle scraping exceptions
        # if isinstance(scrape_result, Exception):
        #     logger.error("❌ [parallel_data_collection_node] Scraping failed: %s", scrape_result)
        #     scrape_result = {"scraping_error": str(scrape_result)}
        # TEMPORARY: scrape_result is manually set above as disabled, no exception handling needed
        
        # Combine all results into the state
        combined_state = {
            **state,
            "bls_result": bls_result,
            "salary_result": salary_result,
            "scraped_jobs": scrape_result.get("scraped_jobs", []),
            "scraping_metadata": scrape_result.get("scraping_metadata", {})
        }
        
        logger.info("✅ [parallel_data_collection_node] Parallel execution completed:")
        logger.info("   - BLS: %s", "Success" if "bls_error" not in bls_result else "Failed")
        logger.info("   - Salary.com: %s", "Success" if "salary_error" not in salary_result else "Failed")
        logger.info("   - Indeed Scraping: DISABLED (timeout issues)")
        logger.info("   - Total jobs found: %d", len(combined_state.get("scraped_jobs", [])))
        
        return combined_state
        
    except Exception as e:
        logger.exception("❌ [parallel_data_collection_node] Error in parallel execution: %s", e)
        return {**state, "parallel_error": str(e)}


async def initialize_mcp_client() -> bool:
    logger.info("🔧 Initializing MCP client...")
    try:
        mcp = get_mcp_client()
        # The direct MCP client manager automatically discovers servers on configured ports from settings
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
