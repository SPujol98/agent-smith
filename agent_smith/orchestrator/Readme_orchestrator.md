## MBPP Agent

**Test**
1. Dump a task
cd moulinette

uv run moulinette_eval dump mbpp --output ../cache/mbpp_task.json

2. Run your agent

cd ../student
uv run python -m agent_mbpp --task-file ../cache/mbpp_task.json \
--output ../cache/mbpp_solution.json \
--model-name "model/name" --provider-url "https://provider.api/v1"

3. Validate solution
cd ../moulinette
uv run moulinette_eval validate mbpp ../cache/mbpp_task.json \
../cache/mbpp_solution.json

## Swebench

**test**
1. Dump a task
cd moulinette
uv run moulinette_eval dump swebench --output ../cache/swebench_task.json

2. Run your agent
cd ../student
uv run python -m agent_swebench --task-file ../cache/swebench_task.json \
--output ../cache/swebench_solution.json \
--model-name "model/name" --provider-url "https://provider.api/v1"

3. Validate solution
cd ../moulinette
uv run moulinette_eval validate swebench ../cache/swebench_task.json \
../cache/swebench_solution.json

## Resorces

OpenAI API - https://developers.openai.com/api/docs/concepts
https://docs.mistral.ai/admin/identity-access/api-keys
