"""
Discrete-event model of live-patch dissemination in Redis Cluster, built to
mirror the authors' prototype (redis-live-patch.patch in the SIGMOD'25
reproduction package, sdbs-uni-p/sigmod25-distributed-imkvs-live-patching).

Mirrored from the prototype source
  * clusterCron runs every 100 ms per node (independent random phase).  At the
    end of each iteration the prototype calls p_migrate() (reach quiescence
    and apply the *signalled* patch) and then p_applyPatchCheck() (signal the
    next available version).  Hence a received patch is signalled at the next
    iteration and applied one iteration later; at most one version is applied
    per iteration, strictly in order.
  * Every cluster message header carries the sender's applied version and its
    bitmap of available patches; gossip entries carry the gossiped node's
    applied version (notused1 field).
  * Pull ("lazy"): on any non-PATCH message the receiver requests patches the
    sender has and it lacks (p_checkForPatchesAndRequest); gossip revealing a
    newer version triggers a request to that node.  A request for a version
    is not repeated for PATCH_REQUEST_DELAY = 5 s.
  * Push ("eager"): the node that receives the patch from a client sends it to
    every node with a link (p_clusterBroadcastPatch).  Pull stays active, so
    "eager" in the prototype is push + pull.
  * "sync" (lazy-sync / eager-sync): a node signals version v only if every
    other node's known version is >= v-1; eager-sync broadcasts a PONG after
    applying.
Mirrored from Redis 7.0 clusterCron
  * every 10th iteration ping the node with the oldest PONG among 5 random
    peers; every iteration ping peers whose PONG is older than node_timeout/2;
    drop a link whose ping is pending > node_timeout/2 and that has been silent
    > node_timeout/2 (link older than node_timeout); reconnect at a later
    iteration and send a PING on the new link.
Network
  * TCP cluster bus: each transmission is lost with probability `loss`; lost
    or partitioned transmissions are retried after RTO = RTT + 200 ms
    (tcp_rto_min), doubling; FIFO per link; data queued on a dropped link is
    lost.
Additions for this project (not in the prototype)
  * strategy "push_only": eager push with pull disabled (ablation, RQ2).
  * dta="controller": nodes report READY once a patch is signalled; an
    external controller sends ACTIVATE when all nodes are ready; migration is
    gated on activation (RQ3).
  * dta="gossip": migration of v is gated until every known node advertises v
    in its available-patch bitmap; a node broadcasts a PONG when it obtains a
    patch so possession spreads quickly (RQ3).
  * dta="eventloop": controller variant where nodes migrate at an agreed
    wall-clock time from the event loop instead of the next cron iteration
    (hypothetical; requires a quiescence point outside clusterCron) (RQ3).
Not modelled: client load, CPU contention, memory state, failover/elections,
inbound/outbound link split, patch file transfer size.
"""
import heapq
import itertools
import math
import random

TICK = 0.100
RTO_MIN = 0.200
PATCH_REQUEST_DELAY = 5.0
APPLY_COST = 0.0002
LOOPBACK_ONE_WAY = 0.00005


class Net:
    def __init__(self, rng, delay, jitter, loss):
        self.rng = rng
        self.delay = max(delay, LOOPBACK_ONE_WAY)
        self.jitter = jitter
        self.loss = loss
        self.partitions = []
        self.fifo = {}

    def cut(self, a, b, t):
        for s, e, g in self.partitions:
            if s <= t < e and ((a in g) != (b in g)):
                return True
        return False

    def one_way(self):
        d = self.delay
        if self.jitter:
            d += self.rng.uniform(-self.jitter, self.jitter)
        return max(d, LOOPBACK_ONE_WAY)

    def arrival(self, a, b, t):
        rto = 2 * self.delay + RTO_MIN
        attempt = t
        while True:
            if not self.cut(a, b, attempt) and self.rng.random() >= self.loss:
                arr = attempt + self.one_way()
                break
            attempt += rto
            rto = min(rto * 2, 120.0)
            if attempt - t > 600:
                return None
        key = (a, b)
        arr = max(arr, self.fifo.get(key, 0.0))
        self.fifo[key] = arr
        return arr


class Link:
    __slots__ = ("up", "epoch", "ctime", "connecting")

    def __init__(self):
        self.up = True
        self.epoch = 0
        self.ctime = -1000.0
        self.connecting = False


class Node:
    def __init__(self, nid, n, rng):
        self.id = nid
        self.phase = rng.uniform(0, TICK)
        self.iteration = rng.randrange(10)
        self.peers = [p for p in range(n) if p != nid]
        self.pong = {p: -rng.uniform(0, 1.0) for p in self.peers}
        self.ping_sent = {p: 0.0 for p in self.peers}
        self.data_rx = dict(self.pong)
        self.view = {p: 0 for p in self.peers}          # peer -> known applied version
        self.view_poss = {p: frozenset() for p in self.peers}
        self.possessed = set()
        self.applied = 0
        self.signaled = None
        self.allow = math.inf
        self.activate_at = {}
        self.req_time = {}


class Cluster:
    """strategy: 'lazy' | 'eager' | 'push_only'.  sync: bool (prototype's -sync methods).
    dta: None | 'controller' | 'gossip' | 'eventloop'."""

    def __init__(self, n, strategy, delay=0.0, jitter=0.0, loss=0.0, node_timeout=15.0,
                 seed=0, sync=False, dta=None, clock_sigma=0.0):
        self.rng = random.Random(seed)
        self.n = n
        self.pull = strategy in ("lazy", "eager")
        self.push = strategy in ("eager", "push_only")
        self.sync = sync
        self.dta = dta
        self.nt = node_timeout
        self.net = Net(self.rng, delay, jitter, loss)
        self.nodes = [Node(i, n, self.rng) for i in range(n)]
        self.links = {frozenset((a, b)): Link() for a in range(n) for b in range(a + 1, n)}
        self.q = []
        self.seq = itertools.count()
        self.now = 0.0
        self.clock_off = [self.rng.gauss(0, clock_sigma) if clock_sigma else 0.0 for _ in range(n)]
        self.ready = {}
        self.submit_time = {}
        self.apply_time = {}
        self.counters = {k: 0 for k in ("PING", "PONG", "PATCH_REQ", "PATCH", "dup_patch",
                                        "link_drops", "lost_on_drop", "ctrl_msgs")}
        self.gossip_k = min(max(3, n // 10), n - 2) if n > 2 else 0
        for nd in self.nodes:
            if dta in ("controller", "eventloop"):
                nd.allow = 0
            self._at(nd.phase, "tick", nd.id)

    # ------------------------------------------------------------ plumbing
    def _at(self, t, kind, *args):
        heapq.heappush(self.q, (t, next(self.seq), kind, args))

    def run(self, until):
        while self.q and self.q[0][0] <= until:
            t, _, kind, args = heapq.heappop(self.q)
            self.now = t
            getattr(self, "_ev_" + kind)(*args)
        self.now = until

    def link(self, a, b):
        return self.links[frozenset((a, b))]

    def _header(self, a, b, gossip=False):
        nd = self.nodes[a]
        h = {"applied": nd.applied, "poss": frozenset(nd.possessed), "gossip": ()}
        if gossip and self.gossip_k:
            others = [p for p in nd.peers if p != b]
            h["gossip"] = [(g, nd.view[g]) for g in self.rng.sample(others, self.gossip_k)]
        return h

    def send(self, a, b, mtype, body=None):
        lk = self.link(a, b)
        if not lk.up:
            return False
        hdr = self._header(a, b, gossip=mtype in ("PING", "PONG"))
        arr = self.net.arrival(a, b, self.now)
        self.counters[mtype] += 1
        if arr is not None:
            self._at(arr, "msg", a, b, lk.epoch, mtype, hdr, body)
        return True

    def send_ping(self, a, b, kind="PING"):
        if self.send(a, b, kind) and kind == "PING":
            nd = self.nodes[a]
            if nd.ping_sent[b] == 0:
                nd.ping_sent[b] = self.now

    def broadcast_pong(self, a):
        for p in self.nodes[a].peers:
            self.send_ping(a, p, "PONG")

    # ------------------------------------------------------------ receive
    def _ev_msg(self, a, b, epoch, mtype, hdr, body):
        if self.link(a, b).epoch != epoch:
            self.counters["lost_on_drop"] += 1
            return
        nd = self.nodes[b]
        nd.data_rx[a] = self.now
        nd.view_poss[a] = hdr["poss"]
        nd.view[a] = max(nd.view[a], hdr["applied"])
        if self.pull and mtype != "PATCH":
            self._request(nd, a, hdr["poss"])
        if mtype == "PING":
            self.send_ping(b, a, "PONG")
        elif mtype == "PONG":
            nd.pong[a] = self.now
            nd.ping_sent[a] = 0.0
        elif mtype == "PATCH_REQ":
            for v in body:
                if v in nd.possessed:
                    self.send(b, a, "PATCH", v)
        elif mtype == "PATCH":
            if body in nd.possessed:
                self.counters["dup_patch"] += 1
            else:
                self._obtain(nd, body)
        for g, v in hdr["gossip"]:
            if g != b and v > nd.view[g]:
                nd.view[g] = v
                nd.view_poss[g] = nd.view_poss[g] | frozenset(range(1, v + 1))
                if self.pull:
                    self._request(nd, g, nd.view_poss[g])

    def _request(self, nd, holder, offered):
        missing = [v for v in offered if v not in nd.possessed
                   and self.now - nd.req_time.get(v, -1e9) > PATCH_REQUEST_DELAY]
        if missing and self.link(nd.id, holder).up:
            for v in missing:
                nd.req_time[v] = self.now
            self.send(nd.id, holder, "PATCH_REQ", sorted(missing))

    def _obtain(self, nd, v):
        nd.possessed.add(v)
        if self.dta == "gossip":
            self.broadcast_pong(nd.id)

    def _ev_submit(self, v, node):
        self.submit_time[v] = self.now
        nd = self.nodes[node]
        nd.possessed.add(v)
        if self.push:
            for p in nd.peers:
                self.send(node, p, "PATCH", v)
        if self.dta == "gossip":
            self.broadcast_pong(node)

    def schedule_submit(self, t, v, node=0):
        self._at(t, "submit", v, node)

    # ------------------------------------------------------------ patching
    def _may_signal(self, nd, v):
        if self.sync:
            return v <= min(nd.view.values()) + 1
        return True

    def _may_migrate(self, nd, v):
        if self.dta in ("controller",):
            return v <= nd.allow
        if self.dta == "eventloop":
            return False
        if self.dta == "gossip":
            return all(v in nd.view_poss[p] for p in nd.peers)
        return True

    def _migrate(self, nd):
        v = nd.signaled
        nd.applied = v
        nd.signaled = None
        self.apply_time.setdefault(v, {})[nd.id] = self.now + APPLY_COST
        if self.sync and self.push:
            self.broadcast_pong(nd.id)

    def _ev_tick(self, nid):
        nd = self.nodes[nid]
        now = self.now
        nd.iteration += 1
        self._heartbeats(nd, now)
        # p_migrate()
        if nd.signaled is not None and self._may_migrate(nd, nd.signaled):
            self._migrate(nd)
        # p_applyPatchCheck()
        if nd.signaled is None:
            nxt = nd.applied + 1
            if nxt in nd.possessed and self._may_signal(nd, nxt):
                nd.signaled = nxt
                if self.dta in ("controller", "eventloop"):
                    self.counters["ctrl_msgs"] += 1
                    self._at(now + self.net.one_way(), "ready", nid, nxt)
        self._at(now + TICK, "tick", nid)

    def _heartbeats(self, nd, now):
        nid = nd.id
        for p in nd.peers:
            lk = self.link(nid, p)
            if not lk.up and not lk.connecting:
                lk.connecting = True
                self._at(now + 2 * self.net.delay, "connect", nid, p, now)
        if nd.iteration % 10 == 0:
            cand = [p for p in self.rng.sample(nd.peers, min(5, len(nd.peers)))
                    if self.link(nid, p).up and nd.ping_sent[p] == 0]
            if cand:
                self.send_ping(nid, min(cand, key=lambda p: nd.pong[p]))
        half = self.nt / 2
        for p in nd.peers:
            lk = self.link(nid, p)
            if not lk.up:
                continue
            if (nd.ping_sent[p] and now - nd.ping_sent[p] > half
                    and now - lk.ctime > self.nt and now - nd.data_rx[p] > half):
                lk.up = False
                lk.epoch += 1
                self.counters["link_drops"] += 1
                continue
            if nd.ping_sent[p] == 0 and now - nd.pong[p] > half:
                self.send_ping(nid, p)

    def _ev_connect(self, a, b, started):
        lk = self.link(a, b)
        lk.connecting = False
        if lk.up or self.net.cut(a, b, started) or self.net.cut(a, b, self.now):
            return
        lk.up = True
        lk.epoch += 1
        lk.ctime = self.now
        nd = self.nodes[a]
        old = nd.ping_sent[b]
        self.send_ping(a, b)
        if old:
            nd.ping_sent[b] = old

    # ------------------------------------------------------------ controller
    def _ev_ready(self, nid, v):
        s = self.ready.setdefault(v, set())
        s.add(nid)
        if len(s) == self.n:
            T = self.now + 2 * self.net.delay + 0.010
            for i in range(self.n):
                self.counters["ctrl_msgs"] += 1
                self._at(self.now + self.net.one_way(), "activate", i, v, T)

    def _ev_activate(self, nid, v, T):
        nd = self.nodes[nid]
        nd.allow = max(nd.allow, v)
        if self.dta == "eventloop":
            local_T = T - self.clock_off[nid]
            self._at(max(local_T, self.now) + self.rng.uniform(0, 0.0005), "el_migrate", nid, v)

    def _ev_el_migrate(self, nid, v):
        nd = self.nodes[nid]
        if nd.signaled == v:
            self._migrate(nd)

    # ------------------------------------------------------------ metrics
    def lag(self, v, nodes=None):
        nodes = range(self.n) if nodes is None else nodes
        at = self.apply_time.get(v, {})
        if any(i not in at for i in nodes):
            return math.inf
        return max(at[i] for i in nodes) - self.submit_time[v]

    def skew(self, v):
        at = self.apply_time.get(v, {})
        if len(at) < self.n:
            return math.inf
        return max(at.values()) - min(at.values())

    def max_divergence(self):
        """Largest number of distinct applied versions seen simultaneously (sampled at apply events)."""
        events = sorted((t, v, i) for v, d in self.apply_time.items() for i, t in d.items())
        cur = [0] * self.n
        worst = 1
        for t, v, i in events:
            cur[i] = v
            worst = max(worst, max(cur) - min(cur) + 1)
        return worst
