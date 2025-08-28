# src/api/fastapi_app.py
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
import logging
import json

# Import the router properly
try:
    from api.routes.job_routes import router as job_router
    print("Successfully imported job_router")
except ImportError as e:
    print(f"Failed to import job_router: {e}")
    job_router = None

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Job Salary Research API",
    description="MCP client-facing API for job market insights",
    version="1.0.0",
    debug=True  # Enable debug mode for better error messages
)

# Add global exception handler for validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Global handler for validation errors"""
    
    # Get request details
    method = request.method
    url = str(request.url)
    
    # Try to get request body
    body = None
    try:
        body = await request.body()
        if body:
            body_str = body.decode('utf-8')
            logger.error(f"Validation failed for {method} {url}")
            logger.error(f"Request body: {body_str}")
            
            # Try to parse as JSON for better formatting
            try:
                body_json = json.loads(body_str)
                logger.error(f"Parsed JSON: {json.dumps(body_json, indent=2)}")
            except:
                pass
        else:
            logger.error(f"Validation failed for {method} {url} - Empty body")
    except Exception as e:
        logger.error(f"Could not read request body: {e}")
    
    # Log validation errors
    logger.error(f"Validation errors: {exc.errors()}")
    
    # Process errors to make them JSON serializable
    processed_errors = []
    for error in exc.errors():
        processed_error = {
            "type": error.get("type"),
            "loc": error.get("loc", []),
            "msg": error.get("msg", ""),
            "input": str(error.get("input")) if error.get("input") is not None else None
        }
        
        # Handle the ctx field which might contain non-serializable objects
        if "ctx" in error:
            ctx = error["ctx"]
            if isinstance(ctx, dict):
                processed_ctx = {}
                for key, value in ctx.items():
                    if isinstance(value, Exception):
                        processed_ctx[key] = str(value)
                    else:
                        try:
                            # Test if the value is JSON serializable
                            json.dumps(value)
                            processed_ctx[key] = value
                        except TypeError:
                            processed_ctx[key] = str(value)
                processed_error["ctx"] = processed_ctx
            else:
                processed_error["ctx"] = str(ctx)
        
        processed_errors.append(processed_error)
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": processed_errors,
            "message": "Request validation failed",
            "request_info": {
                "method": method,
                "url": url,
                "body": body.decode('utf-8') if body else None
            },
            "help": "Check the API documentation for expected request format"
        }
    )

# Add global exception handler for general errors
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Global handler for general errors"""
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "error": str(exc),
            "type": type(exc).__name__
        }
    )

# Include the job routes only if import was successful
if job_router is not None:
    app.include_router(job_router, prefix="/jobs", tags=["Jobs"])
    logger.info("Job routes included successfully")
else:
    logger.error("Job routes could not be included due to import error")

# Add a root endpoint for basic testing
@app.get("/")
async def root():
    return {
        "message": "Job Salary Research API",
        "version": "1.0.0",
        "status": "running",
        "router_status": "loaded" if job_router is not None else "failed",
        "endpoints": {
            "POST /jobs/query": "Process job search query",
            "POST /jobs/test": "Test endpoint for debugging",
            "GET /jobs/health": "Health check",
            "GET /jobs/status": "Service status",
            "GET /docs": "API documentation"
        }
    }

# Add startup and shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info("Job Salary Research API starting up...")
    if job_router is None:
        logger.warning("API started but job routes are not available")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Job Salary Research API shutting down...")
    # Clean up workflow cache
    if job_router is not None:
        try:
            from api.routes.job_routes import cleanup_workflow
            await cleanup_workflow()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")