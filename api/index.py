import sys
import os
 
# Add the backend folder to the path so we can import from it
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
 
from app import app  # Vercel needs a variable named `app`
 