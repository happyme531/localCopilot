"""
All this file does is take the requests and forwrads them but changes a single parameter which is body['n']
  and also truncates prompts that are too long (because open soruce models have a shorter context size than Codex (GitHub Copilot)

More functionality should be added later such as keep track of context of multiple files and maintaining a user session,
  but this would need lots of experimenting.

    pip install -U httpx -U fastapi -U uvicorn -U websockets
    python middleware.py --port 8000

"""

import json
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
import httpx
import os
from fastapi.responses import JSONResponse

# Check if the platform is not Windows
if os.name != 'nt':
    from signal import SIGPIPE, SIG_DFL, signal
    signal(SIGPIPE,SIG_DFL)

app = FastAPI()


#Return fake token response to Copilot extension
@app.get("/copilot_internal/v2/token")
def get_copilot_token():
    print('get_copilot_token()')
    #token value is just a random number
    content = {'token': '1316850460', 'expires_at': 2600000000, 'refresh_in': 1800}
    return JSONResponse(
        status_code=200,
        content=content
    )

MODEL_DEFAULT = ""
MAX_GENERATE_TOKENS_DEFAULT = None
MAX_PROMPT_WORDS_DEFAULT = 4000

GENERATION_PARAMS_OVERRIDE = None

@app.post("/v1/engines/codegen/completions")
async def code_completion(body: dict):
    global MODEL_DEFAULT
    if MODEL_DEFAULT != "":
        body["model"] = MODEL_DEFAULT
    global MAX_GENERATE_TOKENS_DEFAULT
    if MAX_GENERATE_TOKENS_DEFAULT is not None:
        body["max_tokens"] = MAX_GENERATE_TOKENS_DEFAULT
    global MAX_PROMPT_WORDS_DEFAULT
    if MAX_PROMPT_WORDS_DEFAULT is not None:
        body["prompt"] = body["prompt"][-MAX_PROMPT_WORDS_DEFAULT:]
    global GENERATION_PARAMS_OVERRIDE
    if GENERATION_PARAMS_OVERRIDE is not None:
        body.update(GENERATION_PARAMS_OVERRIDE)

    # VLLM: suffix is not supported
    if "suffix" in body:
        del body["suffix"]
    
    print("making request. body:", {k: v for k, v in body.items() if k != "prompt"})

    global BACKEND_URI
    if BACKEND_URI is None:
        raise HTTPException(status_code=500, detail="Fatal Error, BACKEND_URI is not set")


    def code_completion_stream(body: dict):
        # define the generator for streaming
        async def stream_content():
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream(
                        "POST",
                        f"{BACKEND_URI}/v1/completions",
                        json=body,
                        headers={
                            "Accept": "application/json",
                            "Content-type": "application/json",
                        },
                    ) as response:
                        # Check if the response status is not successful
                        if response.status_code != 200:
                            raise HTTPException(
                                status_code=response.status_code,
                                detail="Failed to fetch from the target endpoint",
                            )

                        # Stream the response content
                        async for chunk in response.aiter_bytes():
                            # print('getting chunk')
                            print(f"{chunk=}")
                            yield chunk
            except httpx.ReadTimeout:
                print("A timeout occurred while reading data from the server.")

        return StreamingResponse(stream_content(), media_type="application/json")

    if "stream" in body and body["stream"]:
        return code_completion_stream(body)
    else:
        raise NotImplementedError

def main():
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--backend", type=str, default="http://localhost:5000")
    global MODEL_DEFAULT
    parser.add_argument("--model", type=str, default=MODEL_DEFAULT)
    global MAX_GENERATE_TOKENS_DEFAULT
    parser.add_argument("--max-generate-tokens", type=int, default=MAX_GENERATE_TOKENS_DEFAULT)
    global MAX_PROMPT_WORDS_DEFAULT
    parser.add_argument("--max-prompt-words", type=int, default=MAX_PROMPT_WORDS_DEFAULT)
    parser.add_argument("--generation-params-override", type=str)
    
    args = parser.parse_args()
    
    
    global BACKEND_URI
    BACKEND_URI = args.backend
    MODEL_DEFAULT = args.model
    MAX_GENERATE_TOKENS_DEFAULT = args.max_generate_tokens
    MAX_PROMPT_WORDS_DEFAULT = args.max_prompt_words
    # parse JSON string into dict
    global GENERATION_PARAMS_OVERRIDE
    if args.generation_params_override is not None:
        GENERATION_PARAMS_OVERRIDE = json.loads(args.generation_params_override)
        print("Using generation params override:", GENERATION_PARAMS_OVERRIDE)

    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()
