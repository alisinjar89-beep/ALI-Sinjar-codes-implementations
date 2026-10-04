# Deployment Notes

## Docker Compose demonstration
The recommended local assessment path uses Docker Compose and exposes Rasa on 5005, the action server on 5055, and the React frontend on 3000.

## Hugging Face Spaces
Hugging Face Docker Spaces expose one public application port, normally 7860. For a demonstration Space, place an Nginx or lightweight reverse proxy in front of the frontend and internal Rasa/action processes, then expose only port 7860. Store `CLIMATIQ_API_KEY` and any travel-provider credentials as Space Secrets rather than repository variables.

## Configuration management
`.env.example` lists all required variable names. Production environments must configure short provider timeouts, HTTPS termination, restricted CORS origins, log redaction, and retention limits for handover data.
