import os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from datetime import datetime

# Minimální aplikace pro diagnostiku Railway
app = FastAPI(title="Lecture App Minimal", version="1.0.0")

@app.get("/")
async def root():
    """Minimální health check endpoint"""
    return {
        "status": "healthy",
        "message": "Minimal Lecture App FastAPI běží!",
        "port": os.getenv('PORT', '8000'),
        "timestamp": datetime.now().isoformat(),
        "env_vars": {
            "PORT": os.getenv('PORT', 'NOT SET'),
            "DATABASE_URL": "SET" if os.getenv('DATABASE_URL') else "NOT SET",
            "OPENAI_API_KEY": "SET" if os.getenv('OPENAI_API_KEY') else "NOT SET",
            "TWILIO_ACCOUNT_SID": "SET" if os.getenv('TWILIO_ACCOUNT_SID') else "NOT SET",
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "lecture-app-minimal"}

@app.post("/")
async def root_post(request: Request):
    """Fallback pro Twilio"""
    return {"message": "Minimal app - Twilio endpoint not implemented"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port) 