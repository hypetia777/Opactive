"""
Job-related API routes for the FastAPI application.
"""

from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any, Optional
import requests

import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from config.logging_config import get_logger
from utils.error_handlers import create_error_response, handle_exceptions
from models.job_data import JobQuery
from workflows.job_processing_workflow import create_job_processing_workflow

logger = get_logger(__name__)

router = APIRouter(tags=["jobs"])

# Global workflow instance
workflow_instance = None

async def get_workflow():
    """Get or create the workflow instance."""
    global workflow_instance
    if workflow_instance is None:
        workflow_instance = await create_job_processing_workflow()
    return workflow_instance

@router.post("/query")
async def query_jobs(query: JobQuery):
    """
    Query jobs based on search criteria using the actual workflow.
    
    Args:
        query: Job search query parameters
        
    Returns:
        Job search results
    """
    try:
        logger.info(f"Processing job query: {query.job_title} in {query.location}")
        
        # Get the workflow instance
        workflow = await get_workflow()
        if not workflow:
            raise HTTPException(status_code=500, detail="Failed to initialize workflow")
        
        # Prepare the initial state for the workflow
        initial_state = {
            "query": f"{query.job_title} in {query.location}",
            "job_title": query.job_title,
            "location": query.location,
            "max_results": query.max_results
        }
        
        # Run the workflow
        logger.info("Starting job processing workflow...")
        result = await workflow.run(initial_state)
        logger.info("Workflow completed")
        
        # Log what we received from the workflow
        logger.info(f"Workflow result keys: {list(result.keys())}")
        logger.info(f"BLS result: {result.get('bls_result', 'Not found')}")
        logger.info(f"Salary result: {result.get('salary_result', 'Not found')}")
        logger.info(f"Scraped jobs count: {len(result.get('scraped_jobs', []))}")
        logger.info(f"Structured jobs count: {len(result.get('structured_jobs', []))}")
        
        # Process the results from parallel execution
        scraped_jobs = result.get("scraped_jobs", [])
        bls_result = result.get("bls_result", {})
        salary_result = result.get("salary_result", {})
        structured_jobs = result.get("structured_jobs", [])
        validation_result = result.get("is_valid", True)
        
        # Build the response with all three data sources
        response = {
            "status": "success" if not result.get("error") else "error",
            "message": "Job query processed successfully" if not result.get("error") else result.get("error"),
            "query": {
                "job_title": query.job_title,
                "location": query.location,
                "max_results": query.max_results
            },
            "results": {
                "total_found": len(scraped_jobs),
                "jobs": scraped_jobs,
                "scraped_jobs": scraped_jobs,  # For UI compatibility
                "bls_data": bls_result,
                "bls_result": bls_result,      # For UI compatibility
                "salary_data": salary_result if salary_result.get("success") else None,
                "salary_result": salary_result, # For UI compatibility
                "structured_jobs": structured_jobs,
                "processing_time": result.get("processing_time", 0.0),
                "validation": {
                    "valid": validation_result,
                    "message": result.get("validation_message", "")
                }
            },
            "workflow_status": result.get("workflow_status", "completed")
        }
        
        # Log what we're sending to the UI
        logger.info(f"UI response results keys: {list(response['results'].keys())}")
        logger.info(f"UI BLS data available: {'Yes' if response['results']['bls_data'] else 'No'}")
        logger.info(f"UI Salary data available: {'Yes' if response['results']['salary_data'] else 'No'}")
        logger.info(f"UI Jobs count: {len(response['results']['jobs'])}")
        
        return response
        
    except Exception as e:
        logger.error(f"Error processing job query: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "job-api",
        "timestamp": "2024-01-01T00:00:00Z"
    }


