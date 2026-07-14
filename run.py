import uvicorn
import multiprocessing

if __name__ == '__main__':
    # Required for PyInstaller to work with multiprocessing on Windows
    multiprocessing.freeze_support()
    
    # Run the FastAPI app programmatically
    uvicorn.run(
        "main:app", 
        host="127.0.0.1", 
        port=8000, 
        reload=False,
        workers=1
    )
