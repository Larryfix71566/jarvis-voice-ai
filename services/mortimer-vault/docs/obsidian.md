# Obsidian interop (acceptance test 14)

The vault at `~/Mortimer/vault` is a plain folder of Markdown files with YAML
frontmatter, versioned with git. It requires no plugin or conversion step —
point Obsidian at it directly.

## Opening the vault

1. In Obsidian: **Open folder as vault** → select `~/Mortimer/vault`.
2. Frontmatter fields (`id`, `type`, `created`, `tags`, `confidence`, etc.)
   render as **Properties** in the right-hand panel for any open note.
3. `[[target-id]]` links in the body resolve as normal Obsidian links —
   backlinks, hover preview, and graph view all work against them
   automatically, with no configuration.
4. `.obsidian/` (Obsidian's own config folder, created on first open) is
   already excluded via `.gitignore` — it will not pollute the vault's
   commit history.

## Audit Bases

Two `.base` files are included in `docs/bases/` in this repo. Copy them into
the vault root (or any subfolder) to make them available in Obsidian's Bases
view:

- **`all-decisions.base`** — every `type: decision` file, newest `updated`
  first. This is the quickest way to see what Mortimer believes has been
  decided, and to spot a decision file that's drifted from what you actually
  approved.
- **`stale-memory.base`** — every file with `last_accessed` more than 30 days
  ago, oldest first. This is the confabulation-hunting view: memory the
  supervisor hasn't touched in a while is memory worth spot-checking before
  trusting it in a new session.

To use them: `cp docs/bases/*.base ~/Mortimer/vault/` (or drag them into the
vault in Finder), then open the **Bases** view in Obsidian's left ribbon.

## Editing and reconciliation

You can edit any memory file directly in Obsidian. The service reconciles
this automatically:

1. The file watcher (§7 of the build spec) picks up the change, debounced at
   500 ms, and reindexes it — no restart needed.
2. Because every vault write requires an `expected_hash` matching the file's
   *current* on-disk content, if the supervisor tries to write to a file
   you've just edited in Obsidian, that write is rejected with
   `STALE_FILE`. The supervisor is expected to re-read before retrying — your
   edit always wins over a stale in-flight write.
3. Deleting a file in Obsidian directly (rather than through `/delete`) is
   fine for any file type; the watcher removes it from the index. The
   `DELETE_FORBIDDEN` restriction only applies to deletes issued through the
   vault module/API, as a guardrail against the supervisor deleting curated
   memory — it is not a restriction on you.

## Manual verification checklist

- [ ] Vault opens in Obsidian with no errors.
- [ ] Properties panel shows all nine frontmatter fields for a sample file.
- [ ] A `[[wiki-link]]` in a file body is clickable and resolves.
- [ ] `all-decisions.base` renders a table and lists at least one row after
      creating a `type: decision` file.
- [ ] `stale-memory.base` renders (it may be empty on a fresh vault — nothing
      is stale yet).
- [ ] Editing a file's body in Obsidian, then calling `/health`, shows
      `files_indexed` unchanged and a subsequent `/search` reflects the edit.
