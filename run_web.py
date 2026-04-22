import os
import uvicorn

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "admin_panel.app:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info"
    )
