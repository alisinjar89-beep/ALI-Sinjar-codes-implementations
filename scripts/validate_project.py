from pathlib import Path
import yaml, json, sys
root=Path(__file__).resolve().parents[1]
required=['config.yml','domain.yml','data/nlu.yml','data/stories.yml','data/rules.yml','actions/actions.py','docker-compose.yml','frontend/src/App.jsx','README.md']
missing=[p for p in required if not (root/p).exists()]
for p in ['config.yml','domain.yml','data/nlu.yml','data/stories.yml','data/rules.yml','tests/test_stories.yml']:
    yaml.safe_load((root/p).read_text(encoding='utf-8'))
assert not missing, f"Missing files: {missing}"
domain=yaml.safe_load((root/'domain.yml').read_text())
nlu=yaml.safe_load((root/'data/nlu.yml').read_text())
intents=set(domain['intents'])
training=set(item.get('intent') for item in nlu['nlu'] if item.get('intent'))
covered=(intents-{'nlu_fallback'}) <= training
print('PROJECT VALIDATION: PASS')
print(f'Required files checked: {len(required)}')
print(f'Domain intents: {len(intents)}')
print(f'NLU training intents: {len(training)}')
print(f'NLU intent coverage: {covered}')
print('YAML parse checks: PASS')
