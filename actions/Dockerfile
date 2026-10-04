FROM rasa/rasa-sdk:3.6.2
USER root
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt
COPY . /app/actions
USER 1001
CMD ["start", "--actions", "actions.actions", "--port", "5055"]
