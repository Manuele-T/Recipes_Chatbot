from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

PROJECT_ID = "ai-query-service"       # set at runtime in Cloud Run env
LOCATION   = "europe-west2"

app = FastAPI(title="Vertex AI FAQ Chatbot")

# Data model for incoming question
class Question(BaseModel):
    question: str

@app.post("/ask")
async def ask(q: Question):
    try:
        # 1) System prompt to ask for Markdown output
        system_prompt = """
You are a helpful assistant. If the question you are answering to requires a detailed answer, always answer in valid Markdown, using:
 - headings (#, ##, etc.)
 - bold (**bold**)
 - italics (*italics*)
 - bullet lists (- item)
 - numbered lists (1., 2., 3.)
"""
        # 2) Combine with the user's question
        full_prompt = system_prompt + "\n\nUser question: " + q.question
        # 3) Generate content
        response = app.state.model.generate_content(full_prompt)
        return {"answer": response.text}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# Serve the React build index.html at /
@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("frontend/build/index.html")

# Serve all other React static assets
app.mount(
    "/static",
    StaticFiles(directory="frontend/build/static"),
    name="static"
)

# Initialize Vertex AI on startup
@app.on_event("startup")
def startup_event():
    vertexai.init(project=PROJECT_ID, location=LOCATION)
    app.state.model = GenerativeModel("gemini-1.5-flash")