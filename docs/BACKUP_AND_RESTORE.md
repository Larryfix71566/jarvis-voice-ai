# Backup and restore

What is backed up, where it goes, how to check it, and how to get it back.
Implemented by `scripts/backup_db.py` (nightly, launchd `com.mortimer.backup`
at 03:15) and checked by `scripts/restore_check.py` (by hand).

Anything marked **untested** was written without access to the Mac and has not
been run there.

## What is backed up

| Artifact | Source | Backup file |
| --- | --- | --- |
| Main database | `data/jarvis.db` | `jarvis.<stamp>.db` |
| Cost ledger | `data/costs.db` | `costs.<stamp>.db` |
| Knowledge-base documents | `$MORTIMER_HOME` (default `~/Mortimer`): `vault/` including its git history, and `config/` | `kb-vault.<stamp>.tar.gz` |
| Encrypted secrets vault | `data/secrets.vault` | `secrets.<stamp>.vault` (ciphertext only) |
| Manifest | all of the above | `manifest.<stamp>.json` (file, bytes, sha256; migrations and document count) |

Not backed up: the knowledge-base search index (`~/Mortimer/index/`, rebuilt by
`mortimer-vault reindex --full`), logs, and **the vault key**. Databases at a
custom `JARVIS_DB_PATH` are not covered (the script reads `data/jarvis.db`).

Each artifact is kept 14 deep per kind, locally in `data/backups/` and, when
configured, off-disk.

## Off-disk destination

Set `JARVIS_BACKUP_DEST` in `.env` (or the environment) to an **existing**
directory on another volume, for example `/Volumes/MortimerBackup`:

    JARVIS_BACKUP_DEST=/Volumes/MortimerBackup

The nightly job does not source `.env`; the script reads this one key from
`.env` itself, so the launchd plist does not change.

Rules the script enforces:

* it never creates the destination; if the volume is not mounted the run prints
  `FAILED off-disk: destination does not exist` and exits 1 (local backups are
  still made);
* the path must be absolute and outside the repository (and `data/`);
* a destination on the same volume as `data/` gets a warning: it protects
  against deletion, not disk loss;
* inside the destination it creates only `mortimer-backup/{db,kb,secrets}`
  (mode 0700, files 0600) and verifies each copy by sha256.

Privacy: `jarvis.db` holds conversation memory and the KB holds session
digests. A folder that syncs to a cloud provider (iCloud Drive, Dropbox) would
send them there. The script itself never uploads anything.

## Running and reading it

Run now:

    JARVIS_BACKUP_DEST=/Volumes/MortimerBackup /usr/bin/python3 scripts/backup_db.py

Run the scheduled job now and read its log:

    launchctl kickstart -k gui/$(id -u)/com.mortimer.backup
    tail -n 20 logs/backup.launchd.log

Lines to expect: `ok data/jarvis.db ...`, `ok kb ...`, `ok data/secrets.vault
(encrypted, ciphertext only) ...`, `ok off-disk -> ...`, then the vault-key
status line.

**Untested on the Mac:** the launchd job runs `/usr/bin/python3` (the Command
Line Tools Python, believed to be 3.9; check with `/usr/bin/python3 --version`).
The script avoids 3.10+ syntax and APIs and its test checks that, but it was
not run under 3.9 here. macOS privacy protection (TCC) may deny a background
job write access to a removable volume or an iCloud folder with no prompt; the
symptom is a `PermissionError` in `logs/backup.launchd.log`, the fix is a
System Settings grant (Full Disk Access or Removable Volumes for
`/usr/bin/python3`). A hand run from Terminal can succeed while the job fails,
so do the `kickstart` check above.

## The vault key (manual, attended)

`data/secrets.vault` is encrypted; without its key the backup copy is useless,
and **the key is deliberately never written by any automation**. Do this once,
and again after `python -m jarvis.vault rotate-key`:

1. `python -m jarvis.vault export-key` and copy the output.
2. Store it somewhere that is neither this Mac nor the backup volume (a
   password manager). Never put it in the backup destination: a key beside its
   ciphertext makes the ciphertext as good as plaintext (the nightly run warns
   if it sees a `*vault-key*` or `*.key` file there).
3. Tell the backup where it is, so the nightly run stops warning:

       python3 scripts/backup_db.py --record-key-export "1Password"

   The note holds a date and the words you give, nothing else; a value that
   looks like a key is refused. The record cannot detect a later `rotate-key`.

Every run prints `vault key export: recorded <date> (<n> days ago), stored in
"<where>"` or `NOT RECORDED`.

## Restore check (manual)

    .venv/bin/python scripts/restore_check.py            # local and off-disk
    .venv/bin/python scripts/restore_check.py --local-only
    .venv/bin/python scripts/restore_check.py --dest /Volumes/MortimerBackup

Read-only. For the newest set it verifies the manifest checksums, opens each
database read-only and runs `integrity_check`, compares `jarvis.db` migrations
with the code (behind = warning, unknown = failure), compares the `costs.db`
schema with the live one, reads the whole KB archive (no absolute or `..`
paths, document count equals the manifest), confirms the vault copy is present,
and prints the key-export status. Exit 0 means nothing failed; 1 means a failure
or no backups. It does not decrypt the vault; it prints the command to do that
yourself:

    JARVIS_VAULT_PATH=<backup copy> .venv/bin/python -m jarvis.vault status

To test the exported key as well:

    read -rs JARVIS_VAULT_KEY && export JARVIS_VAULT_KEY && JARVIS_VAULT_PATH=<backup copy> .venv/bin/python -m jarvis.vault status; unset JARVIS_VAULT_KEY

It is not scheduled. Run it after the first successful backup, then now and
then (monthly is reasonable).

## Restoring

Stop Mortimer first: `./scripts/mortimer.sh stop`.

**Databases.** Copy the snapshot over the live file after removing the old WAL
side files, then migrate and restart:

    rm -f data/jarvis.db-wal data/jarvis.db-shm
    cp <backup>/jarvis.<stamp>.db data/jarvis.db
    python scripts/init_db.py
    ./scripts/mortimer.sh

Same for `costs.db` (no migration step). A backup that is behind the code is
brought forward by `init_db.py`.

**Knowledge base.** Extract the archive into `MORTIMER_HOME` and rebuild the
index:

    tar -xzf <backup>/kb-vault.<stamp>.tar.gz -C ~/Mortimer
    mortimer-vault reindex --full

**Secrets vault.** Copy the ciphertext back to `data/secrets.vault` and give
the process the key: export `JARVIS_VAULT_KEY` for the session, or re-add it to
the Keychain under service `mortimer`, account `vault-key` (for example
`security add-generic-password -s mortimer -a vault-key -w`; **untested**
against the exact format the `keyring` library stores). There is no
`import-key` command yet; adding one belongs in `jarvis/vault.py`, which is on
the human-only list.
