#!/usr/bin/env bash
# Smoke test of the authors' SIGMOD'25 reproduction package (Section 5.1).
# Runs on any machine with git + bash (Linux, macOS, Git Bash on Windows); no
# special kernel needed.  It checks the parts of the artifact that do not
# require the MMView/WfPatch kernel or a 384 GB server:
#   S1  the package is publicly available and has the documented structure
#   S2  the Redis prototype patch applies cleanly to upstream Redis 7.0.11
#   S3  the memtier_benchmark patch applies to the pinned memtier commit
#   S4  the kpatch patches apply to the pinned kpatch commit
#   S5  the prototype source contains the mechanisms the paper claims
#       (version + bitmap in the header, gossip version field, PATCH
#        REQUEST/PATCH message types, eager broadcast, quiescence in clusterCron)
#   S6  size of the Redis change (paper: ~700 changed lines incl. dissemination)
# Usage: bash smoke_authors_artifact.sh [WORKDIR]   -> prints PASS/FAIL per check,
# writes smoke_authors_artifact.log, exits non-zero if any check fails.
set -u
W=${1:-./_authors}
mkdir -p "$W"; W=$(cd "$W" && pwd)
LOG="$W/smoke_authors_artifact.log"; : > "$LOG"
fails=0
pass() { echo "PASS  $1" | tee -a "$LOG"; }
fail() { echo "FAIL  $1" | tee -a "$LOG"; fails=$((fails+1)); }
q() { "$@" >>"$LOG" 2>&1; }

REPO=https://github.com/sdbs-uni-p/sigmod25-distributed-imkvs-live-patching
A="$W/artifact"
[[ -d $A/.git ]] || q git -c core.longpaths=true clone --depth 1 "$REPO" "$A"
E="$A/reproduction/redis-cluster/experiments"
echo "artifact commit: $(git -C "$A" rev-parse HEAD)" | tee -a "$LOG"

# S1 structure
ok=1
for p in README.md LICENSE server/download-vm server/run-vm reproduction/reproduce-experiments \
         reproduction/reproduce-analysis "$E/setup-redis" "$E/patches/redis-live-patch.patch" \
         "$E/patches/memtier_benchmark.patch" "$E/redis-build-utils/setup-kpatch" \
         reproduction/plots reproduction/plot-comparison; do
  [[ -e $A/$p || -e $p ]] || { echo "missing $p" >>"$LOG"; ok=0; }
done
((ok)) && pass "S1 package available, documented structure present" || fail "S1 package structure"

# S2-S4 replay the authors' setup-redis / setup-memtier_benchmark / setup-kpatch
# steps exactly (checkout pinned commit, then `git am` their patches in order).
# Clones use core.autocrlf=false so Windows checkouts match Linux byte-for-byte.
GIT="git -c core.autocrlf=false -c user.name=smoke -c user.email=smoke@localhost"
am_replay() {  # dir url ref patch...
  local d=$1 url=$2 ref=$3; shift 3
  [[ -d $d/.git ]] || q $GIT clone "$url" "$d"
  q $GIT -C "$d" am --abort; q $GIT -C "$d" reset -q --hard; q $GIT -C "$d" checkout -q --detach "$ref" || return 1
  for p in "$@"; do q $GIT -C "$d" am "$p" || return 1; done
}
if am_replay "$W/redis" https://github.com/redis/redis 7.0.11 "$E/patches/redis-live-patch.patch"; then
  pass "S2 redis-live-patch.patch applies (git am) to redis 7.0.11"
  grep -q "p_migrate();" "$W/redis/src/cluster.c" && pass "S2 patched cluster.c contains the clusterCron quiescence call" || fail "S2 patched tree"
else fail "S2 redis-live-patch.patch"; fi
if am_replay "$W/redis" https://github.com/redis/redis 7.0.11 "$E/patches/redis-live-patch.patch" "$E/patches/redis-network-single-latencies.patch"; then
  pass "S2b live-patch + network-latency patches apply in sequence"
else fail "S2b combined patches"; fi
MC=$(grep -o '[0-9a-f]\{40\}' "$E/setup-memtier_benchmark" | head -1)
if am_replay "$W/memtier" https://github.com/RedisLabs/memtier_benchmark "$MC" "$E/patches/memtier_benchmark.patch"; then
  pass "S3 memtier_benchmark.patch applies (git am) to pinned commit ${MC:0:8}"
else fail "S3 memtier patch (commit $MC)"; fi
KC=$(grep -o '[0-9a-f]\{40\}' "$E/redis-build-utils/setup-kpatch" | head -1)
if am_replay "$W/kpatch" https://github.com/dynup/kpatch "$KC"      "$E/redis-build-utils/kpatch-patches/0001-Commits-squashed-of-Rommel-et-al.patch"      "$E/redis-build-utils/kpatch-patches/0002-Bump-to-v0.9.5.patch"; then
  pass "S4 kpatch patches 0001+0002 apply (git am) to pinned commit ${KC:0:8}"
else fail "S4 kpatch patches (commit $KC)"; fi

# S5 mechanisms named in the paper
P="$E/patches/redis-live-patch.patch"
chk() { grep -qE -- "$2" "$P" && pass "S5 $1" || fail "S5 $1"; }
chk "header carries uint16 current_patch_version at offset 2256" 'offsetof\(clusterMsg, current_patch_version\) == 2256'
chk "header carries available_patches bitmap at offset 2258" 'offsetof\(clusterMsg, available_patches\) == 2258'
chk "gossip notused1 field reused for version" 'gossip->notused1 = htons\(n->current_patch_version\)'
chk "PATCH_REQUEST message type (pull)" 'define CLUSTERMSG_TYPE_PATCH_REQUEST'
chk "PATCH message type" 'define CLUSTERMSG_TYPE_PATCH '
chk "eager push from client-receiving node" 'from_client && \(method & PATCH_METHOD_EAGER\)'
chk "quiescence point at end of clusterCron" '^\+    p_migrate\(\);'
chk "in-order application (next = current+1)" 'next_version = myself->current_patch_version \+ 1'
B=$(grep -E '^\+#define MAX_PATCHES ' "$P" | awk '{print $3}')
echo "MAX_PATCHES=$B (bitmap bytes = $((B/8)))" | tee -a "$LOG"
[[ $B == 16 ]] && pass "S5 2-byte version + 2-byte bitmap = 4 extra header bytes (default build)" \
               || fail "S5 header size (MAX_PATCHES=$B)"

# S6 size of change (non-WfPatch-library files)
n=$(awk '/^\+\+\+ b\//{f=$2} /^\+[^+]/{ if (f !~ /wfpatch-userland/) c++ } END{print c}' "$P")
echo "added lines outside the WfPatch library: $n" | tee -a "$LOG"
(( n >= 500 && n <= 1000 )) && pass "S6 Redis change size ~700 lines (measured $n added)" || fail "S6 change size $n"

echo "---- $fails failed check(s)" | tee -a "$LOG"
exit $fails
