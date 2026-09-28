The Mortimer-specific skill-creator adaptation in this directory is informed by
Anthropic's public `anthropics/skills` repository, specifically
`skills/skill-creator`, at commit
`33375500bcea98d610eb30ce10ac4e59b89c390d`.

The upstream package snapshot digest is
`7293d1fb6fc7eddc22c663354a80cefb12bb14fbe2950a23cd7f7416605a6b30`, computed
as SHA-256 over sorted package-relative paths and exact file bytes. The upstream
license is Apache License 2.0; its text is retained in `LICENSE.txt`.

The Mortimer instructions and references are a substantial rewrite. They do
not include or execute upstream scripts, assets, evaluation UI, or provider
invocation code. Upstream concepts retained include progressive disclosure,
intent capture, examples, and iterative quality review. Mortimer-specific
sandbox, privacy, model-routing, and activation boundaries take precedence.
