# Eco-Travel Advisor - Rasa Sustainable Tourism Assistant

This repository is a complete, assessment-oriented Rasa Open Source project. It implements adaptive trip intake, optional browser location sharing, carbon estimation through Climatiq, travel-provider retrieval adapters, OpenRouteService routing support, weighted eco-ranking, two-stage fallback recovery, human handover context packaging, a React interface, automated tests, and Docker deployment.

## Important 2026 provider note

The assignment brief names the Amadeus Self-Service sandbox. The Self-Service portal is no longer generally available after July 2026. The project therefore retains an isolated `AmadeusLegacyClient` adapter for assessment traceability, but it stays disabled unless an authorised enterprise-compatible base URL and credentials are supplied. The system never labels demonstration inventory as live Amadeus data.

## Architecture

- Rasa NLU uses spaCy tokenisation and features, word and character CountVectors features, and `DIETClassifier`.
- Rasa Core uses rules, `TEDPolicy`, a slot-filling form, and persistent conversation slots.
- `actions/actions.py` connects dialogue management with provider services, ranking logic, and handover packaging.
- Climatiq `/travel/v1/distance` is called when `CLIMATIQ_API_KEY` exists.
- OpenRouteService supports coordinate-based walking, cycling, and driving routes when its key is configured.
- An Amadeus-compatible adapter can retrieve flight and hotel inventory when authorised credentials remain available.
- React communicates through the Rasa REST webhook and renders quick replies, carbon results, hotel carousels, colour-coded eco cards, GPS consent, and a human handover indicator.

## Setup

1. Copy `.env.example` to `.env` and add only authorised API credentials.
2. Install Docker Desktop with Docker Compose support.
3. Run `docker compose build`.
4. Train a model with `docker compose run --rm rasa train`.
5. Start all services using `docker compose up`.
6. Open `http://localhost:3000` for the web interface.
7. Rasa is exposed at `http://localhost:5005`; the action server uses `http://localhost:5055`.

## Tests

Run the complete evaluation sequence inside the Rasa environment:

```bash
bash scripts/evaluate.sh
```

The script validates Rasa data, creates an 80/20 NLU split, trains the model, performs held-out NLU testing, executes five-fold cross-validation, tests Core stories, and runs every pytest unit test. Rasa writes intent reports, confusion matrices, confidence histograms, and Core results into the evaluation folders produced by those commands.

Pure Python tests can run separately with:

```bash
PYTHONPATH=. pytest -q tests
```

The repository does not include invented F1 values. The marking target of at least 0.85 per intent remains an explicit acceptance criterion until the evaluator executes the Rasa runtime on the supplied environment.

## API privacy, sustainability ethics, and accessibility

- Secrets remain environment variables, while `.env` is ignored by Git.
- Browser geolocation requires explicit permission and manual origin entry always remains available.
- Handover context contains current planning slots and recent conversation text only.
- Demonstration inventory is explicitly labelled instead of being presented as live provider evidence.
- Live carbon outputs identify Climatiq and describe results as approximate decision support.
- Hotel environmental certification is never inferred from branding or ordinary inventory fields.
- The frontend uses semantic buttons, labels, live regions, responsive layouts, and text alongside colour states.

## Project map

- `config.yml`: Rasa NLU and dialogue-policy configuration.
- `domain.yml`: intents, entities, slots, form, responses, and custom actions.
- `data/`: NLU examples, stories, and rules for multiple planning scenarios.
- `actions/`: Climatiq, OpenRouteService, Amadeus-compatible adapter, ranking, handover, and fallback actions.
- `frontend/`: React client plus an offline evidence prototype.
- `tests/`: Core stories, scoring/provider tests, and custom action unit tests.
- `scripts/evaluate.sh`: reproducible NLU, Core, and unit-test workflow.
- `docker-compose.yml`: Rasa 5005, action server 5055, frontend 3000.
- `docs/`: architecture, conversation-flow sources, and prototype scenario documentation.

## GitHub publication

The folder is repository-ready. Initialise Git, commit the files, create a remote repository, and push the main branch. Never commit `.env` or active API credentials.

### Frontend evidence figures

The report frontend figures are reproducible repository-rendered interface states rather than invented live API screenshots. Run `python docs/generate_frontend_evidence.py` to regenerate the trip intake, location choice, ranked results, carbon comparison, fallback clarification, and human-handover figures. Demonstration figures use `mock_data/travel_options.json` and the production `rank_options()` / `build_handover_context()` services, while live Climatiq values are only labelled live when valid provider credentials return them.
