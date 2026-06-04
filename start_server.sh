#!/bin/bash
cd /home/johnlee/CCC151_FINAL_PROJECT/Social_Sphere
source app/venv/bin/activate
python -c "
from dotenv import load_dotenv
load_dotenv()
import uvicorn
from app.main import app
uvicorn.run(app, host='0.0.0.0', port=8000)
"
