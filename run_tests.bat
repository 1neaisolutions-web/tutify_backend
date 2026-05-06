@echo off
echo Running API Endpoint Tests...
call venv\Scripts\activate.bat
python test_api_endpoints.py
pause

