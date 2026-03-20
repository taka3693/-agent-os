
from fastapi import FastAPI
from pydantic import BaseModel
from skills.decision.generate_decision import generate_decision

app = FastAPI()

class Req(BaseModel):
    request: str

@app.post("/decision")
def decision(req: Req):
    result = generate_decision(req.request, context=req.request)
    return {
        "ok": True,
        "result": result
    }

@app.get("/")
def root():
    return {"status": "ok"}


@app.get("/health")
def health():
    return {"ok": True}
