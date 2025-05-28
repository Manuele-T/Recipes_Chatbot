from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import vertexai
from vertexai.generative_models import GenerativeModel, Part, Tool, FunctionDeclaration
import pandas as pd
from google.cloud import storage
import io # Required for downloading from GCS to a buffer
import traceback # For detailed error logging
import sys # For flushing stdout
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Import your recipe tools and the function to set the DataFrame
import recipe_tools

# Configuration for GCS
GCS_BUCKET_NAME = "recipes-chatbot-123" # Your bucket name
GCS_BLOB_NAME = "cleaned_recipes.parquet" # Your file name in the bucket

# FastAPI app initialization
PROJECT_ID = "recipes-chatbot-461113"
LOCATION   = "europe-west2"
MODEL_NAME = "gemini-1.5-flash-002" # Or your preferred Gemini model

app = FastAPI(title="Vertex AI Recipes Chatbot")

# --- Pydantic Models ---
class UserQuery(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str

# --- Tool Definitions for Gemini ---
# These descriptions tell Gemini what your functions can do.
# Match function names and parameter names carefully with recipe_tools.py

search_recipes_func = FunctionDeclaration(
    name="search_recipes_by_criteria_tool",
    description=(
        "Searches for recipes based on a list of ingredients, a specific category, maximum calorie count, "
        "maximum sodium content (in mg), cuisine type (which maps to keywords), "
        "maximum cooking time (in minutes), or a recipe name. "
        "Use this tool to find recipes matching user's dietary or preference criteria."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ingredients": {
                "type": "array",
                "items": {"type": "string"},
                "description": "A list of ingredients the user wants in the recipe. e.g., ['chicken', 'broccoli']"
            },
            "category": {
                "type": "string",
                "description": "The category of recipe the user is looking for. e.g., 'Dessert', 'Healthy', 'Italian'"
            },
            "max_calories": {
                "type": "integer",
                "description": "The maximum number of calories per serving for the recipe. e.g., 500"
            },
            "recipe_name": {
                "type": "string",
                "description": "A specific name or keyword in the recipe title the user is looking for. e.g., 'chocolate cake'"
            },
            "max_sodium": {
                "type": "integer",
                "description": "The maximum amount of sodium in milligrams (mg) per serving. e.g., 300"
            },
            "cuisine": {
                "type": "string",
                "description": "The type of cuisine or a specific keyword related to the recipe. e.g., 'Italian', 'Vegan', 'spicy'"
            },
            "max_cook_time": {
                "type": "integer",
                "description": "The maximum cooking time in minutes. e.g., 30 for recipes that take 30 minutes or less"
            }
        }
    }
)

get_nutritional_info_func = FunctionDeclaration(
    name="get_nutritional_info_tool",
    description="Gets nutritional information (like calories, sodium, fat) for a specific recipe by its name.",
    parameters={
        "type": "object",
        "properties": {
            "recipe_name": {
                "type": "string",
                "description": "The exact or partial name of the recipe to get nutritional information for. e.g., 'Spaghetti Carbonara'"
            }
        },
        "required": ["recipe_name"]
    }
)

# Create a Tool object that bundles all your function declarations
recipe_gemini_tools = Tool(function_declarations=[
    search_recipes_func,
    get_nutritional_info_func,
    # Add other FunctionDeclaration objects here if you create more tools
])

# --- FastAPI Event Handlers ---
@app.on_event("startup")
def startup_event():
    print("Application startup: Initializing Vertex AI and loading dataset...")
    try:
        vertexai.init(project=PROJECT_ID, location=LOCATION)
        # Initialize the generative model
        app.state.model = GenerativeModel(MODEL_NAME)
        print(f"Vertex AI initialized with model: {MODEL_NAME}")

        # Load dataset from GCS
        print(f"Attempting to load dataset from GCS: gs://{GCS_BUCKET_NAME}/{GCS_BLOB_NAME}")
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(GCS_BLOB_NAME)
        
        print("Downloading Parquet file as bytes...")
        parquet_bytes = blob.download_as_bytes()
        print(f"Downloaded {len(parquet_bytes)} bytes. Type: {type(parquet_bytes)}.")
        if isinstance(parquet_bytes, bytes):
            print(f"First 100 bytes: {parquet_bytes[:100]}")
        
        recipes_data = None
        try:
            print("Attempting to load Parquet with fastparquet engine...")
            recipes_data = pd.read_parquet(io.BytesIO(parquet_bytes), engine='fastparquet')
            print(f"Successfully loaded Parquet with fastparquet. Shape: {recipes_data.shape}")
        except Exception as e_fp:
            print(f"Failed to load with fastparquet: {e_fp}")
            print("Traceback for fastparquet failure:")
            traceback.print_exc()
            try:
                print("Attempting to load Parquet with default engine (pyarrow if available)...")
                recipes_data = pd.read_parquet(io.BytesIO(parquet_bytes)) # Fallback to default
                print(f"Successfully loaded Parquet with default engine. Shape: {recipes_data.shape}")
            except Exception as e_default:
                print(f"Failed to load with default engine as well: {e_default}")
                print("Traceback for default engine failure:")
                traceback.print_exc()
                raise

        recipe_tools.set_recipes_dataframe(recipes_data)
        print(f"Dataset '{GCS_BLOB_NAME}' loaded successfully from GCS bucket '{GCS_BUCKET_NAME}'.")

    except Exception as e:
        print(f"CRITICAL ERROR during startup: {e}")
        print("Full traceback for critical startup error:")
        traceback.print_exc()
        recipe_tools.set_recipes_dataframe(pd.DataFrame())
        app.state.startup_error = str(e)


# --- API Endpoints ---
@app.post("/ask", response_model=ChatResponse)
async def ask_question(query: UserQuery):
    if hasattr(app.state, 'startup_error') and app.state.startup_error:
        raise HTTPException(
            status_code=503,
            detail=f"Service unavailable due to startup error: {app.state.startup_error}"
        )
    if not app.state.model:
        raise HTTPException(status_code=503, detail="Model not initialized. Service unavailable.")

    print(f"Received query: {query.question}")
    
    try:
        chat = app.state.model.start_chat()
        response = chat.send_message(
            query.question,
            tools=[recipe_gemini_tools]
        )
        print(f"Gemini initial response: {response.candidates[0].content.parts if response.candidates else 'No candidates'}")

        # Ensure there's content and parts before accessing them
        if not response.candidates or not response.candidates[0].content.parts:
            print("Gemini response had no candidates or parts.")
            final_text_answer = "I could not retrieve an answer. Please try rephrasing your question."
            if hasattr(response, 'prompt_feedback') and response.prompt_feedback: # check existence of prompt_feedback
                print(f"Prompt feedback: {response.prompt_feedback}")
                final_text_answer += f" (Reason: {response.prompt_feedback})"
            if response.candidates and hasattr(response.candidates[0], 'finish_reason') and response.candidates[0].finish_reason: # check existence of finish_reason
                 print(f"Finish Reason: {response.candidates[0].finish_reason}")
                 if str(response.candidates[0].finish_reason) != "STOP":
                    final_text_answer += f" (Details: {response.candidates[0].finish_reason})"
            return ChatResponse(answer=final_text_answer)

        first_part = response.candidates[0].content.parts[0]
        
        # Check if it's a function call
        if hasattr(first_part, 'function_call') and first_part.function_call and first_part.function_call.name:
            function_call = first_part.function_call
            api_response_text = ""
            tool_name = function_call.name
            tool_args = {key: value for key, value in function_call.args.items()}
            print(f"Gemini wants to call tool: {tool_name} with args: {tool_args}")

            if tool_name == "search_recipes_by_criteria_tool":
                function_result_str = recipe_tools.search_recipes_by_criteria_tool(**tool_args)
            elif tool_name == "get_nutritional_info_tool":
                function_result_str = recipe_tools.get_nutritional_info_tool(**tool_args)
            else:
                function_result_str = f"Unknown tool: {tool_name}. I can't process this request."
            
            print(f"Tool {tool_name} executed. Result: {str(function_result_str)[:200]}...")

            response = chat.send_message(
                Part.from_function_response(
                    name=tool_name,
                    response={"content": function_result_str}
                )
            )
            print(f"Gemini response after function call: {response.candidates[0].content.parts if response.candidates else 'No candidates'}")
            if response.candidates and response.candidates[0].content.parts and hasattr(response.candidates[0].content.parts[0], 'text'):
                api_response_text = response.candidates[0].content.parts[0].text
            else: # Handle case where response after function call might not have text (e.g. another function call, or empty)
                api_response_text = "Tool executed. Waiting for next step or final response." # Or some other placeholder
                print("Warning: No direct text part in Gemini's response after function execution.")
        
        elif hasattr(first_part, 'text'): # No function call, just a text response from Gemini
            api_response_text = first_part.text
        else:
            api_response_text = "I received a response, but it was not in the expected format (no function call or text)."
            print("Warning: Gemini response part had no function_call and no text.")


        return ChatResponse(answer=api_response_text)

    except AttributeError as e:
        print(f"AttributeError processing Gemini response: {e} - Response: {response if 'response' in locals() else 'Response not available'}")
        print("--- Full Traceback for AttributeError in /ask endpoint ---")
        traceback.print_exc()
        print("--- End Traceback ---")
        try:
            if response.candidates and response.candidates[0].content.parts[0].text:
                 return ChatResponse(answer=response.candidates[0].content.parts[0].text)
        except:
            pass 
        raise HTTPException(status_code=500, detail=f"Error processing Gemini response structure: {e}")
    except Exception as e:
        print(f"Error in /ask endpoint: {e}")
        # --- MODIFICATION FOR TRACEBACK ---
        print("--- Full Traceback for /ask endpoint error ---")
        traceback.print_exc()
        print("--- End Traceback ---")
        # --- END MODIFICATION ---
        raise HTTPException(status_code=500, detail=str(e))

# --- Static File Serving (Keep as is from your original main.py) ---
@app.get("/manifest.json", include_in_schema=False) # Added route for manifest.json
async def manifest():
    return FileResponse("frontend/build/manifest.json")

@app.get("/", include_in_schema=False)
async def root():
    return FileResponse("frontend/build/index.html")

app.mount(
    "/static",
    StaticFiles(directory="frontend/build/static"),
    name="react-static-assets"
)