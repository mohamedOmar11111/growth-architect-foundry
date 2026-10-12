"""growth_engine.commands — on-demand operator verbs, distinct from loops.

Loops are scheduled jobs that WATCH the business (pull ads, draft briefs,
alert). Commands are verbs the operator (or an AI interface) fires to get a
decision: `audit` scores the account, `diagnose` names the bottleneck,
`report` writes the client readout. Same entrypoint as loops —
`python run_loop.py audit --client Aurora_Skincare` — and same rule: every
command runs against exactly one tenant, is read-only with respect to the
live ad accounts, and never auto-sends anything.

Every command is deterministic Python over state the kernel already holds.
No LLM calls — judgment work stays in the AI interface layer (agents and
skills), numbers stay in code.
"""

# All entries run as `run(tenant: TenantContext) -> int`, same contract as
# TENANT_LOOP_MODULES in run_loop.py — which is why run_loop.py can dispatch
# loops and commands through one code path.
COMMAND_MODULES = {
    "audit": "commands.audit",
    "diagnose": "commands.diagnose",
    "report": "commands.report",
}
