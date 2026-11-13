# RQ3: distribute-then-activate (DtA) design against the authors' prototype

Everything here refers to `reproduction/redis-cluster/experiments/patches/redis-live-patch.patch`
in the authors' package (commit 58bc1b5 of sdbs-uni-p/sigmod25-distributed-imkvs-live-patching).

**Status:** this is a design for code changes. The C changes have **not** been compiled or run.
The behaviour of each variant is evaluated with the model in `../sim` (`dta=` argument).

## What the prototype already does

* `p_applyPatchCheck()` / `p_applyPatch()` run at the end of every `clusterCron()` (100 ms).
  They *signal* the next available version (`wf_set_patch`, `wf_signal_patching`) and set
  `CLUSTER_NODE_PATCH_PENDING`.
* `p_migrate()` runs just before that, in the next iteration. It calls `wf_quiescence()`, which
  performs the address-space switch, and then increments `myself->current_patch_version`.
* Methods `lazy-sync` and `eager-sync` (`PATCH_METHOD_SYNC`) already exist. A node signals version v
  only if every other node's known `current_patch_version` is at least v-1. This bounds divergence
  to one version, but nodes running v and v-1 can still coexist. The paper's experiments do not use
  these methods: they are commented out in `config-common-patch.yaml`.

## Variant A: controller-gated migration (`dta="controller"`; the D1 proposal)

1. Add a flag bit `PATCH_METHOD_HOLD` and a client command `PATCH ACTIVATE <version>` that sets
   `myself->activated_version`.
2. In `p_migrate()`, return early while
   `(method & PATCH_METHOD_HOLD) && myself->current_patch_version + 1 > myself->activated_version`.
   Signalling, and with it WfPatch's background preparation of the new address space, still happens
   immediately. Only the switch is held.
3. Readiness is the existing log line `[Patch Signaled]`. A small controller can also poll
   `CLUSTER NODES`-style state through a new `PATCH STATUS` command. Once every node reports that
   version as signalled, the controller sends `PATCH ACTIVATE v` to all nodes.

## Variant B: decentralized possession barrier (`dta="gossip"`)

No controller is needed. Every header already carries `available_patches`, which is copied into
`sender->available_patches` in `clusterProcessPacket()`.

1. In `p_migrate()`, hold while any known non-handshake node lacks bit v in `available_patches`.
2. In `p_setPatchVersion()`, call `p_clusterBroadcastPatchVersionUsingPong()` (existing function)
   when a new patch is stored. Possession then becomes visible to all nodes within one RTT instead
   of one heartbeat interval.

## Variant C: timed activation from the event loop (`dta="eventloop"`; hypothetical)

This is variant A, but `PATCH ACTIVATE v T` carries a wall-clock time T. Each node calls
`p_migrate()` from `clusterBeforeSleep()` once `wf_time() >= T`, instead of waiting for the next
`clusterCron()`. A quiescence point outside `clusterCron` changes which functions sit on the stack
during migration. The set of unpatchable functions must be re-derived, as the paper does for the
cron-based point. Across machines this variant also needs clock synchronisation (e.g., chrony).

## Accounting for the change in testing

* **A/A check:** run the modified binary with HOLD disabled against the unmodified binary under the
  same load. This shows that the code change itself does not shift lag, throughput, or latency.
* **Same control:** use the same seed, cluster size, and cron phase distribution. The model shows
  that the window between the first and last node applying a version is dominated by the
  unsynchronised 100 ms cron phases.
