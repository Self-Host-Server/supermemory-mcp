.PHONY: node conda render-docs claude-paid claude-free

# Load .env file
ifneq (,$(wildcard .env))
    include .env
    export $(shell sed 's/=.*//' .env)
endif

run:=conda run -n $(conda_name) 

node:
	$(run) nodeenv -p
	$(run) npm install
	$(run) npm update

conda:
	conda env create -f environment.yml -n $(conda_name)
	make node

render-docs:
	$(run) python3 scripts/render_env_docs.py

claude-paid:
	claude --resume $(conda_name) --model paid-premium || claude --name $(conda_name) --model paid-premium

claude-free:
	claude --resume $(conda_name) --model free-stack || claude --name $(conda_name) --model free-stack