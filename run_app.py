import subprocess
import time
import webbrowser
import os
import sys
import urllib.request
import urllib.error

def _popen_kwargs():
    """On Windows, suppress extra console windows for child processes."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.join(base_dir, "backend")

    print("Starting StockDashboard Backend...")
    # Run backend
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--port", "8000"],
        cwd=backend_dir,
        **_popen_kwargs()
    )

    print("Starting StockDashboard Frontend...")
    # Run frontend (shell=True + CREATE_NO_WINDOW avoids a second console window on Windows)
    frontend_proc = subprocess.Popen(
        "npm run dev",
        shell=True,
        cwd=base_dir,
        **_popen_kwargs()
    )
    
    print("Waiting for backend server to start...")
    
    # Wait for backend health endpoint
    max_retries = 30
    backend_ready = False
    for i in range(max_retries):
        try:
            req = urllib.request.Request("http://localhost:8000/health")
            with urllib.request.urlopen(req) as response:
                if response.getcode() == 200:
                    backend_ready = True
                    break
        except urllib.error.URLError:
            pass
        time.sleep(0.5)

    if not backend_ready:
        print("Warning: Backend did not start within expected time.")
    else:
        print("Backend is ready!")

    print("Opening Browser...")
    time.sleep(1) # Brief pause for frontend dev server
    webbrowser.open("http://localhost:5173")
    
    print("Servers are running! Press Ctrl+C to stop.")
    try:
        backend_proc.wait()
        frontend_proc.wait()
    except KeyboardInterrupt:
        print("\nShutting down servers...")
        backend_proc.terminate()
        frontend_proc.terminate()
        backend_proc.wait()
        frontend_proc.wait()
        print("Servers stopped.")

if __name__ == "__main__":
    main()
