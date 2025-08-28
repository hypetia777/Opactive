#!/usr/bin/env python3
"""
FastAPI and Streamlit Startup Script
Starts FastAPI backend and Streamlit frontend with ports configured from .env file
Note: MCP servers should be started separately
"""

import asyncio
import subprocess
import sys
import time
import os
from pathlib import Path

# Change working directory to src/ so that settings.py can find ../env
original_cwd = os.getcwd()
src_dir = Path(__file__).parent / "src"
os.chdir(src_dir)

# Add src to path for imports
sys.path.insert(0, str(src_dir))

from config.settings import settings

# Change back to original directory
os.chdir(original_cwd)


class ServiceManager:
    """Manages startup of FastAPI and Streamlit services with dynamic configuration"""
    
    def __init__(self):
        self.processes = []
        self.src_dir = Path(__file__).parent / "src"
    
    def start_fastapi(self):
        """Start FastAPI server with dynamic configuration"""
        print(f"🌐 Starting FastAPI on {settings.fastapi_bind_host}:{settings.fastapi_port}")
        print(f"   External URL: {settings.fastapi_backend_url}")
        
        cmd = [
            "uvicorn", 
            "api.fastapi_app:app",
            "--host", settings.fastapi_bind_host,
            "--port", str(settings.fastapi_port),
            "--reload"
        ]
        
        process = subprocess.Popen(
            cmd,
            cwd=str(self.src_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self.processes.append({
            "name": "fastapi",
            "process": process,
            "port": settings.fastapi_port
        })
        
        return process
    
    def start_streamlit(self):
        """Start Streamlit with dynamic configuration"""
        print(f"🎯 Starting Streamlit on {settings.streamlit_host}:{settings.streamlit_port}")
        
        cmd = [
            "streamlit", "run", 
            str(self.src_dir / "api" / "streamlit_app.py"),
            "--server.address", settings.streamlit_host,
            "--server.port", str(settings.streamlit_port),
            "--server.headless", "true"
        ]
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        self.processes.append({
            "name": "streamlit", 
            "process": process,
            "port": settings.streamlit_port
        })
        
        return process
    
    async def check_service_health(self, name: str, port: int, max_attempts: int = 30):
        """Check if a service is responding on its port"""
        import aiohttp
        
        url = f"http://localhost:{port}"
        if name == "fastapi":
            url += "/"
        # Note: Streamlit health check will use base URL
        
        for attempt in range(max_attempts):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=2)) as response:
                        if response.status < 500:  # Accept any non-server-error response
                            print(f"✅ {name} is healthy on port {port}")
                            return True
            except:
                pass
            
            await asyncio.sleep(1)
        
        print(f"❌ {name} failed to start on port {port}")
        return False
    
    async def start_all_services(self):
        """Start FastAPI and Streamlit services"""
        print("=" * 60)
        print("🚀 OPACTIVE R4B AUTOMATED SALARY INSIGHTS SYSTEM")
        print("🌐 FastAPI + Streamlit Startup")
        print("=" * 60)
        print(f"📋 Configuration loaded from .env:")
        print(f"   • FastAPI Bind: {settings.fastapi_bind_host}:{settings.fastapi_port}")
        print(f"   • FastAPI External: {settings.fastapi_backend_url}")
        print(f"   • Streamlit: {settings.streamlit_host}:{settings.streamlit_port}")
        print("   ⚠️  Note: MCP servers should be started separately")
        print("=" * 60)
        
        try:
            # 1. Start FastAPI Backend
            print("\n🌐 Starting FastAPI Backend...")
            self.start_fastapi()
            await asyncio.sleep(5)
            
            # 2. Start Streamlit Frontend
            print("\n🎯 Starting Streamlit Frontend...")
            self.start_streamlit()
            await asyncio.sleep(3)
            
            # 4. Health checks
            print("\n🔍 Performing Health Checks...")
            all_healthy = True
            
            for service in self.processes:
                healthy = await self.check_service_health(service["name"], service["port"])
                if not healthy:
                    all_healthy = False
            
            if all_healthy:
                print("\n" + "=" * 60)
                print("✅ FASTAPI & STREAMLIT STARTED SUCCESSFULLY!")
                print("=" * 60)
                print(f"🌐 FastAPI Backend: {settings.fastapi_backend_url}")
                print(f"🎯 Streamlit Frontend: http://{settings.streamlit_host}:{settings.streamlit_port}")
                print(f"📚 API Documentation: {settings.fastapi_backend_url}/docs")
                print("⚠️  Note: Ensure MCP servers are running separately for full functionality")
                print("=" * 60)
                print("Press Ctrl+C to stop FastAPI and Streamlit")
                print("=" * 60)
                
                # Keep running
                try:
                    while True:
                        await asyncio.sleep(1)
                except KeyboardInterrupt:
                    print("\n🛑 Shutting down all services...")
                    self.cleanup()
            else:
                print("\n❌ FastAPI or Streamlit failed to start. Check logs above.")
                self.cleanup()
                sys.exit(1)
                
        except Exception as e:
            print(f"\n❌ Error starting services: {e}")
            self.cleanup()
            sys.exit(1)
    
    def cleanup(self):
        """Clean up all processes"""
        for service in self.processes:
            try:
                service["process"].terminate()
                service["process"].wait(timeout=5)
                print(f"🛑 Stopped {service['name']}")
            except:
                try:
                    service["process"].kill()
                    print(f"🔥 Force killed {service['name']}")
                except:
                    pass


def main():
    """Main entry point"""
    try:
        # Validate settings
        print("🔧 Validating configuration...")
        settings_test = settings  # This will raise validation errors if .env is incomplete
        print("✅ Configuration valid")
        
        # Start services
        manager = ServiceManager()
        asyncio.run(manager.start_all_services())
        
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        print("\n💡 Make sure your .env file contains all required variables.")
        print("See README.md for the complete .env template.")
        sys.exit(1)


if __name__ == "__main__":
    main()
