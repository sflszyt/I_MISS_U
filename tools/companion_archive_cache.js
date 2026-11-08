/* D15: only compiled archive bytes. Authentication is always live, never cached. */
(function(root) {
  'use strict';
  function stable(v) {
    if (Array.isArray(v)) return '[' + v.map(stable).join(',') + ']';
    if (v && typeof v === 'object') return '{' + Object.keys(v).sort().map(function(k) { return JSON.stringify(k) + ':' + stable(v[k]); }).join(',') + '}';
    return JSON.stringify(v);
  }
  function stale() { var e = new Error('ARCHIVE_INVALIDATED'); e.stale = true; return e; }
  function policyChanged() { var e = stale(); e.policy = true; return e; }
  function warmMiss() { var e = new Error('ARCHIVE_WARM_MISS'); e.warmMiss = true; return e; }
  function immutable(value) {
    var copy=JSON.parse(JSON.stringify(value));
    function freeze(v){if(v&&typeof v==='object'){Object.keys(v).forEach(function(k){freeze(v[k]);});Object.freeze(v);}return v;}
    return freeze(copy);
  }
  function authority(code) { var e = new Error(code || 'ARCHIVE_AUTHORITY'); e.authority = true; return e; }
  function relationship(scope) { return {person:scope.person, relationship_id:scope.relationship_id, viewer:scope.viewer}; }
  function refreshRequired(gate) { var e = new Error('ARCHIVE_REFRESH_REQUIRED'); e.refresh = gate; return e; }
  function token() { return Date.now().toString(36) + ':' + Math.random().toString(36).slice(2); }
  var HEX = /^[a-f0-9]{64}$/;
  function hashString(value) { return typeof value === 'string' && HEX.test(value); }
  function record(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
  function IndexedArchiveStore(indexedDB, disabledPreference) { this.indexedDB = indexedDB; this.opening = null; this.disabledPreference = disabledPreference; this.writes = new Set(); }
  IndexedArchiveStore.prototype.open = function() {
    var self = this;
    if (!self.opening) self.opening = new Promise(function(resolve, reject) {
      if (!self.indexedDB) { reject(new Error('STORAGE_UNAVAILABLE')); return; }
      var request = self.indexedDB.open('companion-private-archive-v1', 1), expired = false;
      var timer = setTimeout(function() { expired = true; reject(new Error('STORAGE_TIMEOUT')); }, 3000);
      request.onupgradeneeded = function() {
        var db = request.result;
        db.createObjectStore('files', {keyPath:'path'}); db.createObjectStore('control');
      };
      request.onerror = request.onblocked = function() { clearTimeout(timer); reject(new Error('STORAGE_UNAVAILABLE')); };
      request.onsuccess = function() { clearTimeout(timer); var db = request.result;
        if (expired) { db.close(); return; }
        db.onversionchange = function() { db.close(); self.opening = null; }; resolve(db);
      };
    }).catch(function(e) { self.opening = null; throw e; });
    return self.opening;
  };
  IndexedArchiveStore.prototype.isDisabled = function() {
    try { return !!(this.disabledPreference && this.disabledPreference()); }
    catch (_) { return true; }
  };
  // Every file operation checks the persistent generation in the SAME transaction.
  // Clear in another tab therefore orders before/after writes even without events.
  IndexedArchiveStore.prototype.run = async function(action, guard) {
    var db = await this.open(), executionDisabled = false, self = this;
    if (guard) guard();
    return new Promise(function(resolve, reject) {
      var tx = db.transaction(['files','control'], 'readwrite'), output, error, committedGeneration;
      if (guard) self.writes.add(tx);
      var timer = setTimeout(function() { try { tx.abort(); } catch (_) {} reject(new Error('STORAGE_TIMEOUT')); }, 3000);
      tx.oncomplete = function() {
        self.writes.delete(tx); clearTimeout(timer);
        // A preference can change while IDB is committing, with notifications delayed.
        // Repair any just-committed old-policy write before reporting completion.
        if (!executionDisabled && self.isDisabled()) {
          // The expected policy change may invalidate the original guard, but
          // its epoch/owner check still runs first. Never repair a newer owner,
          // re-enabled preference or generation, even after a delayed open().
          function repairGuard() {
            if (guard) { try { guard(); } catch (e) { if (!e.policy) throw e; } }
            if (!self.isDisabled() || !committedGeneration) throw stale();
          }
          self.clear(true, repairGuard, committedGeneration).then(function() { reject(policyChanged()); }, function() { reject(policyChanged()); }); return;
        }
        try { if (guard) guard(); resolve(output); } catch (e) { reject(e); }
      };
      tx.onabort = tx.onerror = function() { self.writes.delete(tx); clearTimeout(timer); reject(error || new Error('STORAGE_FAILED')); };
      var control = tx.objectStore('control'), files = tx.objectStore('files'), request = control.get('state');
      request.onsuccess = function() {
        executionDisabled = self.isDisabled();
        var meta = request.result || {generation:token(), namespace:'', revision:'', disabled:executionDisabled};
        try {
          if (guard) guard();
          if (executionDisabled) { meta.disabled = true; files.clear(); control.put(meta, 'state'); }
          action(meta, files, control, function(v) { output = v; });
          // Production actions enqueue control.put synchronously (bind/clear
          // may replace meta). Read the actual resulting state in this same tx.
          var committed = control.get('state');
          committed.onsuccess = function() { committedGeneration = committed.result && committed.result.generation; };
        }
        catch (e) { error = e; tx.abort(); }
      };
    });
  };
  IndexedArchiveStore.prototype.cancelWrites = function() {
    this.writes.forEach(function(tx) { try { tx.abort(); } catch (_) {} });
  };
  IndexedArchiveStore.prototype.snapshot = function(guard) {
    return this.run(function(meta, files, control, done) { control.put(meta, 'state'); done(meta); }, guard);
  };
  IndexedArchiveStore.prototype.invalidate = function() {
    return this.run(function(meta, files, control, done) { meta.generation = token(); control.put(meta, 'state'); done(meta); });
  };
  IndexedArchiveStore.prototype.bind = function(namespace, revision, allowed, generation, disabled, guard) {
    var self = this;
    return this.run(function(meta, files, control, done) {
      if (meta.generation !== generation) throw stale();
      // The current preference, including explicit re-enable, dominates old metadata.
      meta.disabled = self.disabledPreference ? self.isDisabled() : !!disabled;
      if (meta.disabled) files.clear();
      if (meta.namespace !== namespace || meta.revision !== revision) {
        meta = Object.assign({}, meta, {generation:token(), namespace:namespace, revision:revision});
        var cursor = files.openCursor();
        cursor.onsuccess = function() { var c = cursor.result; if (!c) return;
          var v = c.value;
          if (meta.disabled || v.namespace !== namespace || !allowed.some(function(f) { return f.path === v.path && f.sha256 === v.sha256; })) c.delete();
          c.continue();
        };
      }
      control.put(meta, 'state'); done(meta);
    }, guard);
  };
  IndexedArchiveStore.prototype.get = function(path, generation, guard) {
    return this.run(function(meta, files, control, done) {
      if (meta.generation !== generation) throw stale();
      var r = files.get(path); r.onsuccess = function() { done(meta.disabled ? undefined : r.result); };
    }, guard);
  };
  IndexedArchiveStore.prototype.put = function(value, generation, guard) {
    return this.run(function(meta, files) {
      if (meta.generation !== generation) throw stale();
      if (!meta.disabled) files.put(value);
    }, guard);
  };
  IndexedArchiveStore.prototype.remove = function(path, generation, guard) {
    return this.run(function(meta, files) { if (meta.generation !== generation) throw stale(); files.delete(path); }, guard);
  };
  IndexedArchiveStore.prototype.current = function(generation, guard, path) {
    return this.run(function(meta, files, control, done) {
      if (meta.generation !== generation) throw stale();
      if (path === undefined) { done(meta); return; }
      // Membership and generation must be observed in the same transaction.
      // Another tab can remove one damaged file without changing the generation.
      var request = files.getKey(path);
      request.onsuccess = function() { done(Object.assign({}, meta, {recordPresent:request.result !== undefined})); };
    }, guard);
  };
  IndexedArchiveStore.prototype.clear = function(disabled, guard, generation) {
    var self = this;
    return this.run(function(meta, files, control, done) {
      if (generation !== undefined && meta.generation !== generation) throw stale();
      meta = {generation:token(), namespace:'', revision:'', disabled:self.disabledPreference ? self.isDisabled() : disabled === undefined ? meta.disabled : !!disabled};
      files.clear(); control.put(meta, 'state'); done(meta);
    }, guard);
  };

  function ArchiveDeviceCache(options) {
    this.o = options; this.store = options.store || new IndexedArchiveStore(root.indexedDB, options.disabledPreference);
    this.operationOwner = 0; this.epoch = 0; this.pending = null; this.identity = null; this.manifestRevision = null;
    this.memory = new Map(); this.retained = false; this.disabled = false; this.storageOK = true;
    this.memoryGeneration = null; this.barrier = Promise.resolve();
    this.preparationPolicy = null; this.lastSuccessfulPolicy = null;
    this.deferred = null; this.stageAttemptEpoch = null; this.lastManifest = null; this.deferredRepair = false;
  }
  ArchiveDeviceCache.prototype.hash = async function(raw) {
    var bytes = await this.o.crypto.subtle.digest('SHA-256', raw);
    return Array.from(new Uint8Array(bytes), function(n) { return n.toString(16).padStart(2,'0'); }).join('');
  };
  ArchiveDeviceCache.prototype.readPolicy = function() {
    try { return {disabled:this.o.disabledPreference ? !!this.o.disabledPreference() : this.disabled,
      invalidation:this.o.invalidationToken ? String(this.o.invalidationToken() || '') : ''}; }
    catch (_) { return {disabled:true, invalidation:'unavailable'}; }
  };
  ArchiveDeviceCache.prototype.check = function(epoch, owner) {
    if (epoch !== this.epoch || (owner !== undefined && owner !== this.operationOwner)) throw stale();
    if (this.preparationPolicy && stable(this.preparationPolicy) !== stable(this.readPolicy())) throw policyChanged();
  };
  ArchiveDeviceCache.prototype.forget = function(persistent) {
    if (this.deferred) this.deferred.phase = 'invalidated';
    this.deferred = null; this.lastManifest = null; this.deferredRepair = false;
    this.epoch++; this.operationOwner++; this.memory.clear(); this.pending = null; this.retained = false;
    this.memoryGeneration = null;
    this.preparationPolicy = null; this.lastSuccessfulPolicy = null;
    if (this.store.cancelWrites) this.store.cancelWrites();
    if (persistent !== false) {
      var self = this;
      this.barrier = this.barrier.catch(function() {}).then(function() { return self.store.invalidate(); });
      this.barrier.catch(function() {});
    }
    if (this.o.invalidate) this.o.invalidate();
  };
  ArchiveDeviceCache.prototype.clear = async function(disabled, remote) {
    this.forget(false); if (disabled !== undefined) this.disabled = !!disabled;
    // Publish the user's decision before awaiting a transaction that may fail or hang.
    if (!remote && this.o.notify) this.o.notify(disabled);
    var epoch = this.epoch, owner = this.operationOwner;
    var cleared = false;
    this.barrier = this.barrier.catch(function() {}).then(function() { return this.store.clear(disabled, function() { if (epoch !== this.epoch) throw stale(); }.bind(this)); }.bind(this));
    try { var meta = await this.barrier; this.check(epoch, owner); this.disabled = this.o.disabledPreference ? this.readPolicy().disabled : meta.disabled; cleared = true; }
    catch (e) { if (e.stale) throw e; this.check(epoch, owner); this.storageOK = false; }
    this.o.status(!cleared ? '已停止使用本页档案；浏览器未确认清除副本，可在浏览器设置中清除此站点数据。' : this.disabled ? '已停用设备档案副本；仍需联网验证和下载。' : '已清除设备档案副本，请点重试重新准备。');
  };
  ArchiveDeviceCache.prototype.jsonOnline = async function(path) {
    var ctrl = new AbortController(), timer;
    var resource = path === '/cdn-cgi/access/get-identity' ? 'IDENTITY' : 'MANIFEST';
    function failure(code) {
      var error = authority(); error.dataResource = resource; error.dataCode = code; return error;
    }
    try {
      return await Promise.race([
        (async function(self) {
          var r;
          try { r = await self.o.fetch(path + (path.indexOf('?') < 0 ? '?' : '&') + 'archive_check=' + encodeURIComponent(token()),
            {credentials:'same-origin', cache:'no-store', redirect:'error', signal:ctrl.signal}); }
          catch (_) { throw failure('NETWORK'); }
          if (r.redirected) throw failure('REDIRECT');
          if (!r.ok) throw failure(Number.isInteger(r.status) && r.status >= 100 && r.status <= 599 ? 'HTTP_' + r.status : 'HTTP');
          try { return await r.json(); } catch (_) { throw failure('JSON'); }
        })(this),
        new Promise(function(resolve,reject) { timer = setTimeout(function() { reject(failure('TIMEOUT')); ctrl.abort(); }, 15000); })
      ]);
    } catch (error) { throw error && error.authority ? error : failure('NETWORK'); }
    finally { clearTimeout(timer); }
  };
  ArchiveDeviceCache.prototype.readIdentity = async function() {
    var id = await this.jsonOnline('/cdn-cgi/access/get-identity');
    if (!id || typeof id.account_id !== 'string' || !/^[a-fA-F0-9]{32}$/.test(id.account_id) ||
        typeof id.user_uuid !== 'string' || !/^[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12}$/.test(id.user_uuid) ||
        id.service_token_id || id.service_token || id.service_token_uuid || id.service_token_status || id.common_name) {
      var error = authority(); error.dataResource = 'IDENTITY'; error.dataCode = 'SCHEMA'; throw error;
    }
    return this.hash(new TextEncoder().encode(stable([this.o.origin, id.account_id.toLowerCase(), id.user_uuid.toLowerCase()])));
  };
  ArchiveDeviceCache.prototype.validateManifest = async function(m) {
    var scope = m && m.scope;
    if (!record(m) || !record(scope) || typeof scope.person !== 'string' || !/^[a-z0-9_-]+$/.test(scope.person) || scope.viewer !== 'father' ||
        scope.relationship_id !== scope.person + '_father' || stable(relationship(scope)) !== stable(relationship(this.o.scope)) ||
        Object.keys(scope).sort().join(',') !== 'memory_release,person,relationship_id,viewer') throw authority('ARCHIVE_REFRESH_REQUIRED');
    var binding = scope.memory_release;
    if (binding !== null && (!record(binding) ||
        Object.keys(binding).sort().join(',') !== 'card_revisions,release_id,release_revision,source_sha256' ||
        typeof binding.release_id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(binding.release_id) || !hashString(binding.release_revision) || !hashString(binding.source_sha256) ||
        !record(binding.card_revisions) ||
        !Object.keys(binding.card_revisions).length || Object.keys(binding.card_revisions).some(function(k) { return !/^[A-Za-z0-9_-]{1,100}$/.test(k) || !hashString(binding.card_revisions[k]); }))) throw authority('ARCHIVE_REFRESH_REQUIRED');
    if (m.schema_version !== 1 || !hashString(m.scope_revision) ||
        m.scope_revision !== await this.hash(new TextEncoder().encode(stable(scope))) ||
        typeof m.context_path !== 'string' || !/^data\/chat_context[A-Za-z0-9_.-]*\.json$/.test(m.context_path) ||
        !Array.isArray(m.files) || m.files.length < 4 || !hashString(m.revision)) throw authority('ARCHIVE_REFRESH_REQUIRED');
    var base = Object.assign({}, m); delete base.revision;
    if (m.revision !== await this.hash(new TextEncoder().encode(stable(base)))) throw authority('ARCHIVE_REFRESH_REQUIRED');
    var memory = 'data/memories' + (scope.memory_release ? '-' + scope.memory_release.release_revision : '') + '.json', seen = new Set();
    for (var f of m.files) {
      if (!record(f) || typeof f.path !== 'string' || seen.has(f.path) || !Number.isSafeInteger(f.bytes) || f.bytes < 1 ||
          !hashString(f.sha256) || (f.path !== m.context_path && f.path !== memory && f.path !== 'data/transcripts.json' && !/^data\/messages-\d{4}\.json$/.test(f.path))) throw authority('ARCHIVE_REFRESH_REQUIRED');
      seen.add(f.path);
    }
    if (![m.context_path,memory,'data/transcripts.json'].every(function(p) { return seen.has(p); })) throw authority('ARCHIVE_REFRESH_REQUIRED');
    return m;
  };
  ArchiveDeviceCache.prototype.gate = async function(epoch, owner) {
    var a = await this.readIdentity(); this.check(epoch, owner);
    var manifest = await this.validateManifest(await this.jsonOnline(this.o.manifestPath)); this.check(epoch, owner);
    var b = await this.readIdentity(); this.check(epoch, owner);
    if (a !== b || (this.identity && a !== this.identity)) { this.identity = null; throw authority(); }
    this.identity = a;
    var result = {manifest:manifest, namespace:await this.hash(new TextEncoder().encode(a + ':' + stable(relationship(manifest.scope))))};
    this.check(epoch, owner);
    if (stable(manifest.scope) !== stable(this.o.scope) || manifest.context_path !== this.o.contextPath) throw refreshRequired(result);
    return result;
  };
  // Automatic failure cleanup may revoke only the generation this transaction saw.
  // User clear/disable remains a separate explicit whole-store operation.
  ArchiveDeviceCache.prototype.cleanupFailure = async function(generation) {
    var self=this;
    self.forget(false);
    var epoch=self.epoch, owner=self.operationOwner, policy=self.readPolicy(), cleared=false;
    self.disabled=policy.disabled;
    function guard(){self.check(epoch,owner);if(stable(policy)!==stable(self.readPolicy()))throw policyChanged();}
    if(generation!==null&&generation!==undefined){
      self.barrier=self.barrier.catch(function(){}).then(function(){guard();return self.store.clear(policy.disabled,guard,generation);});
      try{var clearedMeta=await self.barrier;guard();cleared=true;}catch(e){self.check(epoch,owner);}
    }
    self.check(epoch,owner);
    if(cleared&&self.o.notify){
      // A different client may have rebound after our clear committed. Never send
      // a delayed invalidation for that newer generation; this is not global atomicity.
      try{await self.store.current(clearedMeta.generation,guard);guard();self.o.notify();}
      catch(e){self.check(epoch,owner);}
    }
    return {epoch:epoch,owner:owner,cleared:cleared};
  };
  ArchiveDeviceCache.prototype.failureProof = function(error, epoch, owner) {
    if(epoch!==this.epoch||owner!==this.operationOwner)throw stale();
    error.failureProof=Object.freeze({epoch:epoch,owner:owner});return error;
  };
  ArchiveDeviceCache.prototype.failPreparation = async function(e, epoch, owner, transaction) {
    var self=this;
    if(epoch!==self.epoch||owner!==self.operationOwner)throw e;
    if(e&&/^(HTTP_401|HTTP_403|REDIRECT)$/.test(e.dataCode||''))e.authority=true;
    if(e.policy||e.authority){
      var cleanup=await self.cleanupFailure(transaction&&transaction.generation);
      self.check(cleanup.epoch,cleanup.owner);
      self.o.status((e.policy?'设备资料设置已改变，请重新验证。':e.message==='ARCHIVE_REFRESH_REQUIRED'?'档案范围已改变，请刷新本页。':'无法验证当前访问权限或资料，请联网并重新验证。')+
        (cleanup.cleared?'已清除本次事务的设备副本。':'已停止使用本页资料；未确认清除设备副本。'));
      throw self.failureProof(e,cleanup.epoch,cleanup.owner);
    }
    if(e.refresh){
      var policy=self.preparationPolicy;
      self.forget(false);var refreshEpoch=self.epoch,refreshOwner=self.operationOwner;
      function guard(){self.check(refreshEpoch,refreshOwner);if(stable(policy)!==stable(self.readPolicy()))throw policyChanged();}
      try{
        guard();if(!e.snapshot)throw stale();
        await self.store.bind(e.refresh.namespace,e.refresh.manifest.revision,e.refresh.manifest.files,e.snapshot.generation,policy.disabled,guard);guard();
        self.o.status('档案版本已更新，请刷新本页；未变化且已缓存的设备文件会在刷新后重新校验。');
      }catch(cleanupError){
        self.check(refreshEpoch,refreshOwner);
        if(!cleanupError.stale&&!cleanupError.policy&&e.snapshot){
          try{self.barrier=self.barrier.catch(function(){}).then(function(){guard();return self.store.clear(policy.disabled,guard,e.snapshot.generation);});await self.barrier;guard();}
          catch(clearError){self.check(refreshEpoch,refreshOwner);}
        }
        self.o.status('档案版本已更新，请刷新本页；未确认清除本次事务的设备副本。');
      }
      throw self.failureProof(e,refreshEpoch,refreshOwner);
    }
    if(e.stale){self.forget(false);epoch=self.epoch;owner=self.operationOwner;}
    self.o.status('档案下载或校验未完成，请重试；本次发送已停止。');
    throw self.failureProof(e,epoch,owner);
  };
  ArchiveDeviceCache.prototype.prepare = function() {
    var self = this;
    if (self.deferred) {
      if (self.deferred.completion) return self.deferred.completion;
      self.forget(false);
    }
    if (self.pending) return self.pending;
    if (self.deferredRepair) {
      self.memory.clear(); self.retained=false; self.lastManifest=null; self.deferredRepair=false;
    }
    var epoch = self.epoch, owner = ++self.operationOwner;
    self.preparationPolicy = self.readPolicy();
    var transaction={generation:null};
    var p = self.prepareOnce(epoch, owner, transaction).catch(function(e) { return self.failPreparation(e, epoch, owner, transaction); })    .finally(function() { if (self.pending === p) self.pending = null; });
    self.pending = p; return p;
  };
  // A single deferred transaction; no text, send intent or old terminal approval.
  ArchiveDeviceCache.prototype.stageForSend = function() {
    var self = this;
    if (self.deferred) return self.deferred;
    if (self.pending || !self.retained || !self.lastManifest || !self.memoryGeneration || self.readPolicy().disabled || stable(self.lastSuccessfulPolicy)!==stable(self.readPolicy()) || self.stageAttemptEpoch === self.epoch) return null;
    var op = {epoch:self.epoch, owner:++self.operationOwner, policy:self.readPolicy(), phase:'preparing', claimed:false, raw:new Map(), generation:null, expected:immutable(self.lastManifest)};
    self.stageAttemptEpoch = self.epoch; self.deferred = op; self.preparationPolicy = op.policy;
    op.guard = function() { self.check(op.epoch,op.owner); if (self.deferred !== op || stable(op.policy) !== stable(self.readPolicy())) throw stale(); };
    op.localReady = (async function() {
      await self.barrier; op.guard();
      try { op.meta = await self.store.snapshot(op.guard); } catch(e) { if(e.stale)throw e; throw warmMiss(); }
      op.guard(); op.generation=op.meta.generation;
      if (op.meta.generation !== self.memoryGeneration) throw stale();
      if (op.meta.disabled || op.meta.namespace !== op.expected.namespace || op.meta.revision !== op.expected.manifest.revision) throw warmMiss();
      try { Object.defineProperty(op,'first',{value:immutable(await self.gate(op.epoch,op.owner))}); } catch(e) { if(e.refresh)e.snapshot=op.meta; throw e; }
      op.guard();
      if (op.first.namespace !== op.expected.namespace || op.first.manifest.revision !== op.expected.manifest.revision) { var e=refreshRequired(op.first);e.snapshot=op.meta;throw e; }
      await self.validateDeferred(op, false); op.guard(); op.phase='staged';
      return op;
    })().catch(async function(e) {
      if (self.deferred === op) {
        try { op.guard(); } catch(invalid) { e=invalid; }
        op.failure=e;
        op.phase='failed';
        if (!op.claimed) {
          self.deferred=null;
          if(e.warmMiss)self.deferredRepair=true;
          else return self.failPreparation(e,op.epoch,op.owner,op).catch(function(error) {
            var proof=error&&error.failureProof;
            // Only unclaimed work needs an out-of-band page failure. A claimed
            // Send already owns its catch; late A must never publish against B.
            if(proof&&proof.epoch===self.epoch&&proof.owner===self.operationOwner&&self.o.failed)self.o.failed(error,proof);
            throw error;
          });
        }
      }
      throw e;
    });
    op.localReady.catch(function() {});
    return op;
  };
  ArchiveDeviceCache.prototype.deferredMembership = async function(op) {
    var self=this;
    await Promise.all(op.first.manifest.files.map(async function(f) {
      op.guard(); var state;
      try { state=await self.store.current(op.meta.generation,op.guard,f.path); } catch(e) { if(e.stale)throw e; throw warmMiss(); }
      op.guard(); if(state.disabled || !state.recordPresent) throw warmMiss();
    }));
    op.guard();
  };
  ArchiveDeviceCache.prototype.validateDeferred = async function(op, resume) {
    var self=this,manifest=op.first.manifest,values=new Map(),validations=new Map();
    async function load(f) {
      op.guard(); var saved;
      try { saved=await self.store.get(f.path,op.meta.generation,op.guard); } catch(e) { if(e.stale)throw e; throw warmMiss(); }
      op.guard();
      if (!saved || saved.namespace!==op.first.namespace || saved.sha256!==f.sha256 || !(saved.raw instanceof ArrayBuffer) || saved.raw.byteLength!==f.bytes) throw warmMiss();
      if (await self.hash(saved.raw)!==f.sha256) throw warmMiss(); op.guard();
      var raw=resume?op.raw.get(f.path):saved.raw.slice(0);
      if (!(raw instanceof ArrayBuffer) || raw.byteLength!==f.bytes || await self.hash(raw)!==f.sha256) throw warmMiss(); op.guard();
      var data;try{data=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(raw));}catch(_){throw warmMiss();}
      if(f.path===self.o.contextPath){var shards=data.message_shards;
        if(!Array.isArray(shards)||!shards.length||new Set(shards).size!==shards.length||shards.some(function(n){return typeof n!=='string'||!/^messages-\d{4}\.json$/.test(n);})||
          stable(shards.map(function(n){return 'data/'+n;}).sort())!==stable(manifest.files.map(function(x){return x.path;}).filter(function(p){return /^data\/messages-/.test(p);}).sort())) throw authority('ARCHIVE_REFRESH_REQUIRED');
      }
      var validation=await self.o.validate(f.path,data);op.guard();
      if(!resume)op.raw.set(f.path,raw);
      values.set(f.path,data);validations.set(f.path,validation);
    }
    var context=manifest.files.find(function(f){return f.path===self.o.contextPath;});await load(context);
    var rest=await Promise.allSettled(manifest.files.filter(function(f){return f!==context;}).map(load));op.guard();
    var failed=rest.find(function(r){return r.status==='rejected';});if(failed)throw failed.reason;
    await self.deferredMembership(op);
    return {files:values,validations:validations,epoch:op.epoch,revision:manifest.revision,generation:op.meta.generation};
  };
  ArchiveDeviceCache.prototype.finishForSend = function() {
    var self=this,op=self.deferred;
    if(!op){
      if(self.pending){var epoch=self.epoch;return self.pending.then(function(){self.check(epoch);return self.prepare();});}
      return self.prepare();
    }
    if(op.completion)return op.completion;
    op.claimed=true;
    op.completion=(async function(){
      await op.localReady;op.guard();op.phase='finalizing';
      // Revalidate private AND persisted bytes after arbitrary idle; no mutable map reuse.
      var result=await self.validateDeferred(op,true);op.guard();
      var last;try{last=await self.gate(op.epoch,op.owner);}catch(e){if(e.refresh)e.snapshot=op.meta;throw e;}op.guard();
      if(last.namespace!==op.first.namespace)throw authority('ARCHIVE_REFRESH_REQUIRED');
      if(stable(last)!==stable(op.first)){var changed=refreshRequired(last);changed.snapshot=op.meta;throw changed;}
      await self.deferredMembership(op);op.guard();
      self.retained=true;self.lastSuccessfulPolicy=immutable(op.policy);self.manifestRevision=last.manifest.revision;
      op.phase='consumed';self.stageAttemptEpoch=null;return result;
    })().catch(async function(e){
      if(self.deferred!==op)throw e;
      try { op.guard(); } catch(invalid) { e=invalid; }
      op.phase='failed';
      if(e.warmMiss){
        op.guard();self.deferred=null;self.memory.clear();self.retained=false;self.lastManifest=null;
        return self.prepare();
      }
      return self.failPreparation(e,op.epoch,op.owner,op);
    }).finally(function(){if(self.deferred===op)self.deferred=null;});
    return op.completion;
  };
  ArchiveDeviceCache.prototype.prepareOnce = async function(epoch, owner, transaction) {
    var self = this, snapshot = null;
    try { await self.barrier; } catch (_) { self.check(epoch, owner); self.memory.clear(); }
    self.check(epoch, owner);
    try { snapshot = await self.store.snapshot(function() { self.check(epoch, owner); }); } catch (e) { if (e.policy || e.stale) throw e; self.check(epoch, owner); self.memory.clear(); }
    self.check(epoch, owner);
    if (snapshot) transaction.generation=snapshot.generation;
    if (snapshot && self.memoryGeneration && snapshot.generation !== self.memoryGeneration) throw stale();
    var first;
    try { first = await self.gate(epoch, owner); } catch (e) { if (e.refresh) e.snapshot = snapshot; throw e; }
    self.check(epoch, owner);
    var manifest = first.manifest, meta = null;
    // Scope/identity migrations are never allowed to carry memory into a new gate.
    for (var pair of self.memory) if (!manifest.files.some(function(f) { return f.path === pair[0] && f.sha256 === pair[1].sha256 && pair[1].namespace === first.namespace; })) self.memory.delete(pair[0]);
    self.storageOK = true; self.retained = false;
    var preferDisabled = self.preparationPolicy.disabled;
    if (snapshot) {
      try { meta = await self.store.bind(first.namespace, manifest.revision, manifest.files, snapshot.generation, preferDisabled, function() { self.check(epoch, owner); }); self.check(epoch, owner); transaction.generation=meta.generation; self.disabled = preferDisabled || meta.disabled; }
      catch (e) { if (e.stale) throw e; self.check(epoch, owner); self.storageOK = false; meta = snapshot; self.memory.clear(); }
    } else { self.storageOK = false; self.memory.clear(); }
    if (preferDisabled) self.disabled = true;
    self.memoryGeneration = meta ? meta.generation : null;
    var local = 0, downloaded = 0, verified = 0, validations = new Map();
    function status() { self.check(epoch, owner);
      if (self.o.progress) self.o.progress({total:manifest.files.length,downloaded:local+downloaded,verified:verified},epoch,owner);
      self.o.status('本地读取 ' + local + '，下载 ' + downloaded + '，已校验 ' + verified + '/' + manifest.files.length + '。' +
      (!self.storageOK ? '浏览器未能保留副本，本次仅在线使用。' : self.disabled ? '设备缓存已停用。' : '设备档案副本已启用。')); }
    status();
    async function current(path) {
      self.check(epoch, owner);
      var state = null;
      if (meta) { try { state = await self.store.current(meta.generation, function() { self.check(epoch, owner); }, path); } catch(e) { self.check(epoch, owner); self.storageOK=false; throw e.stale ? e : stale(); } }
      self.check(epoch, owner);
      return state;
    }
    async function load(f) {
      await current();
      var saved = self.memory.get(f.path), data, raw, hit = false, storedHit = false;
      if (!saved && meta && self.storageOK && !self.disabled) {
        try { saved = await self.store.get(f.path, meta.generation, function() { self.check(epoch, owner); }); storedHit = !!saved; } catch(e) { if(e.stale)throw e; self.check(epoch, owner); self.storageOK=false; }
      }
      self.check(epoch, owner);
      if (saved && saved.namespace === first.namespace && saved.sha256 === f.sha256) {
        raw = saved.raw;
        if (raw instanceof ArrayBuffer && raw.byteLength === f.bytes && await self.hash(raw) === f.sha256) hit = true;
      }
      self.check(epoch, owner);
      if (saved && !hit) {
        self.memory.delete(f.path);
        if (meta) await self.store.remove(f.path, meta.generation, function() { self.check(epoch, owner); });
        self.check(epoch, owner);
      }
      if (!hit) { raw = await self.o.transport(f.path); self.check(epoch, owner); downloaded++;
        if (!(raw instanceof ArrayBuffer) || raw.byteLength !== f.bytes || await self.hash(raw) !== f.sha256) throw new Error('ARCHIVE_HASH');
      } else local++;
      self.check(epoch, owner);
      try { data = JSON.parse(new TextDecoder('utf-8', {fatal:true}).decode(raw)); }
      catch (_) { self.check(epoch, owner); self.memory.delete(f.path); if (meta) await self.store.remove(f.path, meta.generation, function() { self.check(epoch, owner); }); throw new Error('ARCHIVE_JSON'); }
      if (f.path === self.o.contextPath) {
        var shards = data.message_shards;
        if (!Array.isArray(shards) || !shards.length || new Set(shards).size !== shards.length ||
            shards.some(function(n) { return typeof n !== 'string' || !/^messages-\d{4}\.json$/.test(n); }) ||
            stable(shards.map(function(n) { return 'data/' + n; }).sort()) !== stable(manifest.files.map(function(x) { return x.path; }).filter(function(p) { return /^data\/messages-/.test(p); }).sort())) throw authority('ARCHIVE_REFRESH_REQUIRED');
      }
      var validation;
      try { validation = await self.o.validate(f.path, data); }
      catch (e) { self.check(epoch, owner); self.memory.delete(f.path); if (meta) await self.store.remove(f.path, meta.generation, function() { self.check(epoch, owner); }); throw e; }
      var currentState = await current(f.path);
      validations.set(f.path, validation);
      var record = {path:f.path, sha256:f.sha256, namespace:first.namespace, raw:raw};
      // Only bytes already persisted in THIS generation may omit a redundant put.
      // Hash, semantic validation, both current() checks and both gates still run.
      var persisted = hit && meta && currentState.recordPresent && (storedHit || saved.persistedGeneration === meta.generation);
      if (persisted) record.persistedGeneration = meta.generation;
      self.memory.set(f.path, record);
      if (meta && self.storageOK && !self.disabled && !persisted) {
        try { await self.store.put(record, meta.generation, function() { self.check(epoch, owner); }); record.persistedGeneration = meta.generation; } catch(e) { if(e.stale)throw e; self.check(epoch, owner); self.storageOK=false; }
      }
      self.check(epoch, owner); verified++; status(); return [f.path, data];
    }
    // Validate context first: no shard may be retained before its membership is known.
    var contextFile = manifest.files.find(function(f) { return f.path === self.o.contextPath; });
    var values = [await load(contextFile)];
    var rest = await Promise.allSettled(manifest.files.filter(function(f) { return f !== contextFile; }).map(load));
    var failed = rest.find(function(r) { return r.status === 'rejected'; });
    if (failed) throw failed.reason;
    values = values.concat(rest.map(function(r) { return r.value; }));
    var last;
    try { last = await self.gate(epoch, owner); } catch (e) { if (e.refresh) e.snapshot = meta; throw e; }
    await current();
    if (last.namespace !== first.namespace) throw authority('ARCHIVE_REFRESH_REQUIRED');
    if (last.manifest.revision !== manifest.revision) { var changed = refreshRequired(last); changed.snapshot = meta; throw changed; }
    // A record may have been removed in this same generation during the final gate.
    // Report retention truthfully without repairing anything after authorization.
    if (meta && self.storageOK && !self.disabled) {
      var membership = await Promise.all(manifest.files.map(function(f) { return current(f.path); }));
      self.check(epoch, owner);
      if (membership.some(function(state) { return !state || state.disabled || !state.recordPresent; })) self.storageOK = false;
    }
    self.retained = !!meta && self.storageOK && !self.disabled;
    self.lastSuccessfulPolicy=immutable(self.preparationPolicy);
    self.lastManifest = self.retained ? immutable({manifest:manifest, namespace:first.namespace}) : null;
    self.manifestRevision = manifest.revision; self.stageAttemptEpoch=null; status();
    return {files:new Map(values), validations:validations, epoch:epoch, revision:manifest.revision,generation:meta?meta.generation:null};
  };
  var api = {ArchiveDeviceCache:ArchiveDeviceCache, IndexedArchiveStore:IndexedArchiveStore, stable:stable};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ArchiveDeviceCache = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
