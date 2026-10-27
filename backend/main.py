import uvicorn
from api import app


def main():
    print("Starting NovaSecurity API on http://0.0.0.0:8000...")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
