# src/adaptors/mcp_client.py

import logging
import json
import os
from typing import Dict, List, Any, Optional
import aiohttp

from config.settings import settings

from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

class DirectMCPClientManager:
    """HTTP-only MCP client manager using streamable_http"""

    def __init__(self, settings):
        self.settings = settings
        self.client: Optional[MultiServerMCPClient] = None
        self._initialized = False
        self.available_servers = []
        self.failed_servers = []

    async def _test_server_connection(self, url: str) -> bool:
        """Test if MCP HTTP server is reachable via valid JSON-RPC"""
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "list_tools",
                "id": "test"
            }
            headers = {
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=self.settings.mcp_connection_timeout)) as response:
                    if response.status == 200:
                        data = await response.json()
                        return "result" in data
                    elif response.status == 406:
                        # Accept 406 as "reachable" (MCP HTTP server responds but doesn't accept the request format)
                        logger.info(f"⚠️ MCP server {url} responded with 406 Not Acceptable, treating as reachable")
                        return True
                    else:
                        logger.warning(f"❌ MCP server {url} responded with status {response.status}")
                        return False
        except Exception as e:
            logger.warning(f"Server connection test failed for {url}: {e}")
            return False

    async def initialize(self, server_configs: Dict[str, Dict[str, Any]] = None):
        """Initialize client with HTTP (streamable_http) transport"""
        try:
            available_server_configs = {}

            host_map = {
                "scraping": settings.mcp_scraping_host,
                "bls": settings.mcp_bls_host,
                "salary": settings.mcp_salary_host
            }
            port_map = {
                "scraping": settings.mcp_scraping_server_port,
                "bls": settings.mcp_bls_server_port,
                "salary": settings.mcp_salary_server_port
            }

            for server_name in port_map:
                url = f"http://{host_map[server_name]}:{port_map[server_name]}/mcp/"

                # Test server connection before adding to config
                logger.info(f"🔍 Testing connection to {server_name} server at {url}")
                if await self._test_server_connection(url):
                    config = {
                        "transport": "streamable_http",
                        "url": url
                    }
                    available_server_configs[server_name] = config
                    self.available_servers.append(server_name)
                    logger.info(f"✅ Registered MCP server '{server_name}' at {url}")
                else:
                    self.failed_servers.append(server_name)
                    logger.warning(f"❌ Failed to connect to {server_name} server at {url}")

            if not available_server_configs:
                logger.error("❌ No MCP servers are available")
                return False

            self.client = MultiServerMCPClient(available_server_configs)
            self._initialized = True
            logger.info(f"🚀 MCP Client initialized with {len(available_server_configs)} HTTP servers")
            
            # Log available vs failed servers
            if self.available_servers:
                logger.info(f"Available servers: {', '.join(self.available_servers)}")
            if self.failed_servers:
                logger.warning(f"Failed servers: {', '.join(self.failed_servers)}")
            
            return True

        except Exception as e:
            logger.exception("❌ Failed to initialize MCP client", exc_info=e)
            return False

    @property
    def is_initialized(self) -> bool:
        return self._initialized and self.client is not None

    def _prepare_tool_arguments(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """Prepare arguments based on the specific tool's expected format"""
        if tool_name == "scrape_jobs":
            # The scraping server expects job_title, location, and max_results directly
            return kwargs
        elif tool_name == "health_check":
            # Health check doesn't need arguments
            return {}
        else:
            # Generic tool call - pass arguments as-is
            return kwargs

    async def call_server(self, server_name: str, tool_name: str, **kwargs) -> Any:
        if not self.is_initialized:
            raise RuntimeError("MCP Client not initialized")

        if server_name not in self.available_servers:
            raise RuntimeError(f"Server '{server_name}' is not available. Available servers: {self.available_servers}")

        try:
            # Prepare arguments in the correct format for the tool
            prepared_args = self._prepare_tool_arguments(tool_name, **kwargs)
            logger.info(f"📤 Calling {server_name}.{tool_name} with prepared args: {prepared_args}")
            
            async with self.client.session(server_name) as session:
                result = await session.call_tool(tool_name, arguments=prepared_args)

            logger.info(f"✅ Received response from {server_name}.{tool_name}")
            logger.debug(f"🔍 Raw result: {result}")
            
            # Extract content from the result
            # MCP call_tool returns a CallToolResult object with content
            if hasattr(result, 'content') and result.content:
                # If the content is a list, get the first item
                if isinstance(result.content, list) and len(result.content) > 0:
                    content_item = result.content[0]
                    # If it's a TextContent object, get the text
                    if hasattr(content_item, 'text'):
                        try:
                            # Try to parse as JSON if it looks like JSON
                            parsed_result = json.loads(content_item.text)
                            logger.info(f"🔍 Parsed JSON result: {parsed_result}")
                            return parsed_result
                        except json.JSONDecodeError:
                            # Return as plain text if not JSON
                            logger.info(f"🔍 Plain text result: {content_item.text}")
                            return content_item.text
                    else:
                        logger.info(f"🔍 Direct content result: {content_item}")
                        return content_item
                else:
                    logger.info(f"🔍 Empty or non-list content: {result.content}")
                    return result.content
            else:
                # Return the raw result if no content attribute
                logger.info(f"🔍 Raw result returned: {result}")
                return result

        except Exception as e:
            logger.exception(f"❌ Error calling {server_name}.{tool_name}", exc_info=e)
            raise

    async def get_server_tools(self, server_name: str) -> List[str]:
        if not self.is_initialized:
            return []

        if server_name not in self.available_servers:
            logger.warning(f"Server '{server_name}' is not available")
            return []

        try:
            async with self.client.session(server_name) as session:
                tools_result = await session.list_tools()
                # tools_result should have a tools attribute
                if hasattr(tools_result, 'tools'):
                    return [tool.name for tool in tools_result.tools if hasattr(tool, 'name')]
                else:
                    logger.warning(f"Unexpected tools result format: {tools_result}")
                    return []
        except Exception as e:
            logger.warning(f"Could not list tools for {server_name}: {e}")
            return []

    async def health_check(self) -> Dict[str, bool]:
        health = {}
        for server in self.available_servers:
            try:
                result = await self.call_server(server, "health_check")
                health[server] = result.get("status") == "healthy" if isinstance(result, dict) else False
            except Exception as e:
                logger.warning(f"Health check failed for {server}: {e}")
                health[server] = False
        
        # Also include failed servers in health check
        for server in self.failed_servers:
            health[server] = False
            
        return health

    async def close(self):
        if self.client:
            try:
                await self.client.close()
                self._initialized = False
                logger.info("🔒 Closed MCP client connections")
            except Exception as e:
                logger.warning(f"Error closing MCP client: {e}")
                
    async def set_servers(self, server_configs: Dict[str, Dict[str, Any]]):
        """
        Accepts server config but does nothing in direct mode.
        Exists to maintain compatibility with abstract MCP interface.
        """
        logger.debug("DirectMCPClientManager.set_servers called but ignored in direct mode.")

# Factory function
_mcp_instance = None

def create_mcp_client_manager(settings, use_mock: bool = False):
    logger.info("Creating Direct MCP Client Manager for HTTP-only mode")
    return DirectMCPClientManager(settings)

def get_mcp_client():
    global _mcp_instance
    if _mcp_instance is None:
        _mcp_instance = create_mcp_client_manager(settings)
    return _mcp_instance