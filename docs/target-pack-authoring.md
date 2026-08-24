# Target pack authoring (M0 contract)

A target is `targets/<name>/target.yaml`; the `name` must equal the directory name.
V1 accepts `target_type: mcp` and exactly one topology entry. The topology remains a
list so later multi-server support does not change the external contract.

Access capability is enforced:

- `black_box`: behavioral testing and diagnosis, no repair;
- `gray_box`: source-aware diagnosis and suggestions, no repair;
- `white_box`: repair may be enabled and is still routed through a worktree and gates.

STDIO servers require `command`; HTTP servers require `url`. SAFE_LIVE is the default.
List every known irreversible tool in both the contract and `safety.yaml`; annotations
are evidence, never authority.

Scenarios must identify a versioned oracle. Generated scenarios without a deterministic,
trace, environment-state, or human-gold oracle cannot authorize autonomous repair.
