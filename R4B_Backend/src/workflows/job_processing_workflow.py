# workflows/job_processing_workflow.py

import logging
from typing import Dict, Any
from langgraph.graph import StateGraph, END
from workflows.workflow_nodes import (
    validate_query_node,
    scrape_node,
    bls_node,
    salary_node,
    parallel_data_collection_node,
    structure_node,
    initialize_mcp_client,
    cleanup_mcp_client
)

logger = logging.getLogger(__name__)

class JobProcessingWorkflow:
    """Simplified job processing workflow using only parsing and scraping"""

    def __init__(self):
        self.workflow = None
        self.is_initialized = False

    async def initialize(self):
        """Initialize the workflow and MCP client"""
        try:
            success = await initialize_mcp_client()
            if not success:
                logger.error("Failed to initialize MCP client")
                return False

            self.workflow = self._build_workflow()
            self.is_initialized = True

            logger.info("Simplified job processing workflow initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize workflow: {e}")
            return False

    def _build_workflow(self):
        graph = StateGraph(dict)
        graph.add_node("validate", validate_query_node)
        graph.add_node("parallel_data_collection", parallel_data_collection_node)
        graph.add_node("structure", structure_node)
        
        # Conditional transition after validate: valid → parallel data collection, else end.
        def after_validate(state: Dict[str, Any]) -> str:
            return "parallel_data_collection" if state.get("is_valid", False) else END

        # After parallel data collection, proceed to structuring
        def after_parallel_data_collection(state: Dict[str, Any]) -> str:
            return "structure"

        graph.set_entry_point("validate")
        graph.add_conditional_edges(
            "validate",
            after_validate,
            {"parallel_data_collection": "parallel_data_collection", END: END}
        )
        
        # Parallel data collection handles BLS, salary.com, and scraping internally
        graph.add_edge("parallel_data_collection", "structure")
        graph.add_edge("structure", END)
        
        return graph.compile()

    async def run(self, initial_state: Dict[str, Any]) -> Dict[str, Any]:
        if not self.is_initialized:
            raise RuntimeError("Workflow not initialized. Call initialize() first.")

        try:
            logger.info(f"Running simplified workflow for: {initial_state.get('query', 'N/A')}")
            result = await self.workflow.ainvoke(initial_state)
            logger.info("Workflow completed successfully")

            # ✅ Ensure structured jobs are included
            structured_jobs = result.get("structured_jobs") or result.get("scraped_jobs") or []
            scraped_jobs = result.get("scraped_jobs") or []
            
            # Update result with both structured and raw data
            result["structured_jobs"] = structured_jobs
            result["scraped_jobs"] = scraped_jobs
            result["raw_jobs"] = scraped_jobs  # optional alias
            
            # Include table data for UI display (PDF format)
            result["table_data"] = result.get("table_data", [])
            result["pdf_table_format"] = result.get("table_data", [])  # Alias for clarity
            
            # Include structuring status
            result["structuring_status"] = result.get("structuring_status", "unknown")
            result["structuring_completed"] = result.get("structuring_completed", False)

            logger.info(f"✅ Returning {len(structured_jobs)} structured jobs")
            logger.info(f"📊 PDF table data rows: {len(result.get('table_data', []))}")
            return result

        except Exception as e:
            logger.error(f"Error running workflow: {e}")
            error_result = initial_state.copy()
            error_result.update({
                "error": str(e),
                "workflow_status": "failed"
            })
            return error_result

    async def cleanup(self):
        try:
            await cleanup_mcp_client()
            self.is_initialized = False
            logger.info("Workflow cleanup completed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

# Entry point for other modules
async def create_job_processing_workflow():
    workflow = JobProcessingWorkflow()
    success = await workflow.initialize()
    if success:
        return workflow
    else:
        raise RuntimeError("Failed to initialize job processing workflow")
