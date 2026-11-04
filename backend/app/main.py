from fastapi import FastAPI

app = FastAPI(title="DevFlow AI")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
