# Third-party notices

The Foundry's own code, commands, tests and docs are MIT-licensed (see `LICENSE`).
Four of the six files in `01_Context_Vault/` are adapted from an open-source project. Its licence text is
reproduced verbatim in [`licenses/`](./licenses/). Files may have been modified from upstream
(renamed, trimmed, re-voiced); upstream copyright remains with the original authors.

| Upstream | Licence | Copyright holder | Used in this repo |
|---|---|---|---|
| [msitarzewski/agency-agents](https://github.com/msitarzewski/agency-agents) | MIT | AgentLand Contributors | 5 agent personas: `Agents/marketing/` (twitter, instagram, tiktok, reddit) and `Agents/design/design-image-prompt-engineer.md` |

## Original or locally adapted (covered by the root MIT licence)

`Agents/marketing/marketing-linkedin-strategist.md` and all of `core/engine/`.

## History

A larger set of personas, protocols and skills from other MIT/Apache-2.0 projects (everything-claude-code,
humanizer, grill-me, prompt-master, diagram-design, caveman) was bundled in earlier releases and removed on
1 Nov 2026 because the engine never used it. Earlier tagged releases still contain it, with its licences.
A previously bundled `karpathy_rules.md` derived from an unlicensed upstream and was removed rather than
redistributed.

## How this was determined

Upstream was identified by matching file names and frontmatter against the project's published tree, then
confirming its repository licence through the GitHub API. Matching by name is strong evidence, not a
byte-for-byte audit: if you are an upstream author and a file here is misattributed or you want it removed,
open an issue and it will be fixed promptly.
