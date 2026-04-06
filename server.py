from .main import app  # noqa: F401

if __name__ == "__main__":
    import uvicorn
    from .config import settings
    uvicorn.run("backend.main:app", host=settings.host, port=settings.port)