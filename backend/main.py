import uvicorn
from api import app


def main():
    print("Starting Proofline API on http://127.0.0.1:8000...")
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
