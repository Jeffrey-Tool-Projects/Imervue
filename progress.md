# progress.md: Imervue

Outstanding work only. When an item is done, delete it in the same commit and add a `#done` entry to `docs/updates/` (format and query commands: `docs/updates/README.md`). No finished items, no history, no rules (rules live in `CLAUDE.md`).
Item numbers (`#n`) are never reused. Tags: [DECIDE] needs the owner's decision, [BLOCKED] waits on something else, [UNVERIFIED] observed but not confirmed.
Cross-repo and workspace items live in `D:\Codes\progress.md` (relevant here: S-10, X-9, X-10, X-18).

## Open

- [UNVERIFIED] Install Rigora from a released executable (U-20261126-01): only the `pip --no-deps --target` step and the dialog wiring were exercised, not a Nuitka build.
  Next: on a clean Windows machine, open Puppet in the released EXE, press Install Rigora, confirm both tabs build in place, load File > Examples > Imeru, restart and confirm Rigora still loads from `lib/site-packages`.

- [UNVERIFIED] Thumbnail wall fill time after U-20261126-04 is not measured; the remaining GUI-thread costs on that path are one `os.stat` per landed tile (`tile_loader_results.py`, `file_signature`), up to 512 stats in `_image_metadata_index.prime` per folder click, a synchronous `write_user_setting()` per folder click, and texture uploads with `glGenerateMipmap` inside paint with no per-frame cap.
  Next: time a cold (cache cleared) and a warm open of a folder of about 2,000 JPEGs on a real machine, before and after; then send the signature with the worker result, move `prime` into the scan worker, debounce the session write and cap uploads per frame.

- [BLOCKED] Codacy file-complexity threshold: every runtime file that scored 80 or more is split (PR #111, fix/main-quality). Hosted Codacy still flags files above the current threshold of 20; at 60 about 50 files would remain, at 50 about 88.
  Next: the owner raises the threshold in the Codacy repository quality settings (the environment Codacy token returns HTTP 401 here), then decide whether the 60-80 band needs another pass. canvas_render.py remains at 68.

- File-tree follow-up: image_issue_panel.py:95 still calls the absent _FileTreeView._open_in_explorer helper.
  Next: migrate the caller to the shared reveal API with a behavior test and synchronized user documentation. A direct call with one selected path reproduces AttributeError before any OS launch.


- Interpreter verification can block inside Windows process creation for an invalid executable, before its subprocess timeout applies.
  Next: investigate a bounded, background-safe production probe with preserved interpreter-discovery behavior. The test-only ENOEXEC injection verifies error handling but does not fix or prove this runtime case; no OS dialog cause has been established.

- Pre-existing quirks pinned (not fixed) by the complexity-split contract tests: pip_install_workers._ImportWorker formats `{exc or type(exc).__name__}`, so an exception with an empty message shows as "name: "; control_tooltips_fields reuses an owner's help with its `&` read as a mnemonic, giving a double space; control_tooltips.ensure_tooltip raises AttributeError for a plain QObject.
  Next: fix each with a regression test and update the contract test that pins it (tests/test_pip_installer_contracts.py, tests/test_control_tooltips_contracts.py).

- More pre-existing quirks pinned (not fixed) by the split contracts: a press exactly at (0, 0) never starts a GPU-view drag-select (input_controller_tiles); with a selection, normal brush blend writes the brush RGB into fully transparent pixels outside it (alpha stays 0; brush_dab). The .codacy.yaml bandit entry for clip_search.py and the .bandit B403 comment about its torch pickle loading look stale (no subprocess or pickle code remains there).
  Next: confirm each with a focused test, fix or drop it, and update the contract that pins it.

- After the dev merge, user_setting_dict.py measures 83 locally; hosted Codacy previously scored it 76. The former puppet/webcam_tracker.py belongs to Rigora after extraction.
  Next: check their hosted scores once the merge lands on main and split the remaining Imervue module if it reaches 80.
