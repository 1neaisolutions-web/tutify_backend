@echo off
echo ========================================
echo Running Chatbot Seeder
echo ========================================
cd /d %~dp0
python -m app.seed.cli --chatbots --force
pause
