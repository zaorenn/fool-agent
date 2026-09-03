import { contextBridge, ipcRenderer, webUtils } from 'electron'

/**
 * Ana surecten iletilen bas-konus tusu.
 *
 * Degistiriciler kombo baglamalar icin SART: ``Shift+ControlRight`` bagliyken
 * bayraklar tasinmazsa centik, odak disinda hic eslesme goremezdi.
 */
interface ForwardedPtt {
  altKey?: boolean
  ctrlKey?: boolean
  metaKey?: boolean
  repeat: boolean
  shiftKey?: boolean
  type: 'down' | 'up'
}


contextBridge.exposeInMainWorld('foolDesktop', {
  getConnection: profile => ipcRenderer.invoke('fool:connection', profile),
  // Registry-scoped backend resolution: { connectionId, profile } → descriptor.
  getConnectionFor: payload => ipcRenderer.invoke('fool:connection:for', payload),
  getProfileRoutes: profiles => ipcRenderer.invoke('fool:plugin-profile-routes', profiles),
  revalidateConnection: () => ipcRenderer.invoke('fool:connection:revalidate'),
  touchBackend: profile => ipcRenderer.invoke('fool:backend:touch', profile),
  getGatewayWsUrl: profile => ipcRenderer.invoke('fool:gateway:ws-url', profile),
  // Registry-scoped fresh WS URL: { connectionId, profile } → result shape of
  // getGatewayWsUrl, minted against that connection's backend.
  getGatewayWsUrlFor: payload => ipcRenderer.invoke('fool:gateway:ws-url-for', payload),
  // Union agent roster across every registered connection.
  getAgentRoster: () => ipcRenderer.invoke('fool:agents:roster'),
  openSessionWindow: (sessionId, opts) => ipcRenderer.invoke('fool:window:openSession', sessionId, opts),
  openSessionInTerminal: (sessionId, opts) => ipcRenderer.invoke('fool:window:openInTerminal', sessionId, opts),
  openWindow: () => ipcRenderer.invoke('fool:window:openInstance'),
  claimAmbientCue: (key, ttlMs) => ipcRenderer.invoke('fool:ambient:claim', key, ttlMs),
  wakeIndicator: {
    getState: () => ipcRenderer.invoke('fool:wake-indicator:get'),
    setState: state => ipcRenderer.send('fool:wake-indicator:set', state),
    onState: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('fool:wake-indicator:state', listener)

      return () => ipcRenderer.removeListener('fool:wake-indicator:state', listener)
    }
  },
  petOverlay: {
    // Main renderer → main process: window lifecycle + drag. `request` is
    // `{ bounds, screen }`; resolves with the screen bounds it actually used.
    open: request => ipcRenderer.invoke('fool:pet-overlay:open', request),
    close: () => ipcRenderer.invoke('fool:pet-overlay:close'),
    setBounds: bounds => ipcRenderer.send('fool:pet-overlay:set-bounds', bounds),
    setIgnoreMouse: ignore => ipcRenderer.send('fool:pet-overlay:ignore-mouse', ignore),
    // Flip the overlay focusable (and focus it) while the composer needs keys.
    setFocusable: focusable => ipcRenderer.send('fool:pet-overlay:set-focusable', focusable),
    // Main renderer → overlay (forwarded by main): push the latest pet state.
    pushState: payload => ipcRenderer.send('fool:pet-overlay:state', payload),
    // Overlay → main renderer (forwarded by main): pop back in / composer submit.
    control: payload => ipcRenderer.send('fool:pet-overlay:control', payload),
    // Overlay subscribes to state pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('fool:pet-overlay:state', listener)

      return () => ipcRenderer.removeListener('fool:pet-overlay:state', listener)
    },
    // Main renderer subscribes to overlay control messages.
    onControl: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('fool:pet-overlay:control', listener)

      return () => ipcRenderer.removeListener('fool:pet-overlay:control', listener)
    }
  },
  // HUD mode: the chrome-free floating chat. A full app renderer (own gateway)
  // sized as a floating bar, so it mounts the real composer. Main owns the
  // window; `onChanged` keeps every window's toggle truthful.
  // FOOL-SEAM: shared-window-values
  //
  // Pencereler arasi kucuk degerler (sesin gidecegi oturum, bas-konus tusu,
  // dinleme kipi) ANA SURECTEN geciyor.
  //
  // Once ``localStorage`` + ``storage`` olayi kullaniliyordu ve gelistirmede
  // calisiyordu: orada iki pencere de ``http://127.0.0.1:5174`` yukluyor, yani
  // AYNI kokende. Paketlenmis surumde ikisi de ``file://`` yukluyor ve
  // Chromium ``file:`` belgelerine ayri depolar veriyor -- yani kopru
  // yayinlanan uygulamada HIC calismiyordu. Kullanicinin gordugu sey: centik
  // acik sohbeti bulamiyor, ayarlardan degistirilen tus centige ulasmiyor.
  //
  // Ana surec her iki pencereyi de goruyor; dogru tasiyici o.
  shared: {
    get: (key: string) => ipcRenderer.invoke('fool:shared:get', key),
    set: (key: string, value: string) => ipcRenderer.invoke('fool:shared:set', { key, value }),
    onChange: (callback: (payload: { key: string; value: string }) => void) => {
      const listener = (_e: unknown, payload: { key: string; value: string }) => callback(payload)

      ipcRenderer.on('fool:shared:changed', listener)

      return () => ipcRenderer.removeListener('fool:shared:changed', listener)
    }
  },
  // FOOL-SEAM: notch-ipc
  notch: {
    open: () => ipcRenderer.invoke('fool:notch:open'),
    close: () => ipcRenderer.invoke('fool:notch:close'),
    toggle: () => ipcRenderer.invoke('fool:notch:toggle'),
    shortcut: () => ipcRenderer.invoke('fool:notch:shortcut'),
    setShortcut: (accelerator: string) =>
      ipcRenderer.invoke('fool:notch:set-shortcut', accelerator),
    // Istek KIPI de tasiniyor: kisayol yalnizca centigi acmiyor, arkadas
    // turunu de basliyor ve notch oturumu o kapsamla aciyor.
    // Montajda BEKLEYEN niyeti al (ve tuket). Yeni acilan pencerede
    // ``send`` renderer dinleyiciyi kurmadan geliyor ve mesaj dusuyor.
    takeListenRequest: () => ipcRenderer.invoke('fool:notch:take-intent'),
    // Kullanicinin sectigi bas-konus tusunun FIZIKSEL kodu. Ana surec
    // iletmeyi buna gore suzuyor; sabit ``ControlRight`` ile kullanicinin
    // yeniden bagladigi tus odak disinda hic ulasmiyordu.
    setPushToTalk: (code: string) => ipcRenderer.invoke('fool:notch:set-ptt', code),
    // Uyandirma sozcugu duyuldu: centigi ac ve "wake" niyetini ilet.
    wake: () => ipcRenderer.invoke('fool:notch:wake'),
    // Tikla-gecir kapisi. Centik VARSAYILAN olarak gecirgen (ekranin ust
    // kenarini yutmamali) ve yalnizca imlec tiklanabilir bir parcanin
    // uzerindeyken katilasiyor.
    setIgnoreMouse: (ignore: boolean) => ipcRenderer.send('fool:notch:ignore-mouse', ignore),
    // Bas-konus tusu BASKA penceremizden iletildi: centik odakta olmasa da
    // calissin (bkz. ``installPushToTalkForwarding``).
    onPushToTalk: (callback: (event: ForwardedPtt) => void) => {
      const listener = (_e: unknown, payload: ForwardedPtt) =>
        callback(payload)

      ipcRenderer.on('fool:notch:ptt', listener)

      return () => ipcRenderer.removeListener('fool:notch:ptt', listener)
    },
    onListenRequest: (callback: (request?: { mode?: string }) => void) => {
      const listener = (_event: unknown, request?: { mode?: string }) => callback(request)

      ipcRenderer.on('fool:notch:listen', listener)

      return () => ipcRenderer.removeListener('fool:notch:listen', listener)
    }
  },
  hud: {
    open: request => ipcRenderer.invoke('fool:hud:open', request),
    close: () => ipcRenderer.invoke('fool:hud:close'),
    setIgnoreMouse: ignore => ipcRenderer.send('fool:hud:ignore-mouse', ignore),
    moveBy: delta => ipcRenderer.send('fool:hud:move-by', delta),
    setBounds: bounds => ipcRenderer.send('fool:hud:set-bounds', bounds),
    setVibrancy: on => ipcRenderer.invoke('fool:hud:vibrancy', on),
    // The HUD tells main which session it is on; main hands that back to the
    // app window when the HUD closes, so the app can re-home onto it.
    setSession: sessionId => ipcRenderer.send('fool:hud:session', sessionId),
    onGoto: callback => {
      const listener = (_event, sessionId) => callback(sessionId)
      ipcRenderer.on('fool:hud:goto', listener)

      return () => ipcRenderer.removeListener('fool:hud:goto', listener)
    },
    onChanged: callback => {
      const listener = (_event, state) => callback(state)
      ipcRenderer.on('fool:hud:changed', listener)

      return () => ipcRenderer.removeListener('fool:hud:changed', listener)
    },
    // Linux only, and silent elsewhere: where the cursor is, in page
    // coordinates, or null when it has left the window. Stands in for the
    // mousemove that `setIgnoreMouseEvents(true, { forward: true })` delivers on
    // macOS and Windows but not here.
    onCursor: callback => {
      const listener = (_event, point) => callback(point)
      ipcRenderer.on('fool:hud:cursor', listener)

      return () => ipcRenderer.removeListener('fool:hud:cursor', listener)
    }
  },
  // Quick Entry: the global-hotkey mini composer window. Main owns the OS
  // shortcut + the persisted preference; the quick window only captures text
  // and hands it back, and the primary renderer submits it through the normal
  // prompt path.
  quickEntry: {
    getSettings: () => ipcRenderer.invoke('fool:quick-entry:settings:get'),
    setSettings: patch => ipcRenderer.invoke('fool:quick-entry:settings:set', patch),
    submit: payload => ipcRenderer.send('fool:quick-entry:submit', payload),
    dismiss: () => ipcRenderer.send('fool:quick-entry:dismiss'),
    // Primary renderer → main → quick window: gateway connection state + the
    // recent-session options the target picker offers. Main caches the latest
    // payload so a freshly spawned quick window starts from truth.
    pushState: payload => ipcRenderer.send('fool:quick-entry:state', payload),
    // Quick window subscribes to those pushes.
    onState: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('fool:quick-entry:state', listener)

      return () => ipcRenderer.removeListener('fool:quick-entry:state', listener)
    },
    // Main → primary renderer: a submit captured by the quick window.
    onSubmit: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('fool:quick-entry:submit', listener)

      return () => ipcRenderer.removeListener('fool:quick-entry:submit', listener)
    },
    // Main → quick window: you were just summoned (reset draft + refocus).
    onShown: callback => {
      const listener = () => callback()
      ipcRenderer.on('fool:quick-entry:shown', listener)

      return () => ipcRenderer.removeListener('fool:quick-entry:shown', listener)
    }
  },
  getBootProgress: () => ipcRenderer.invoke('fool:boot-progress:get'),
  getConnectionConfig: profile => ipcRenderer.invoke('fool:connection-config:get', profile),
  saveConnectionConfig: payload => ipcRenderer.invoke('fool:connection-config:save', payload),
  applyConnectionConfig: payload => ipcRenderer.invoke('fool:connection-config:apply', payload),
  testConnectionConfig: payload => ipcRenderer.invoke('fool:connection-config:test', payload),
  // v2 multi-connection registry: named agent sources (local / remote / cloud / ssh).
  connections: {
    list: () => ipcRenderer.invoke('fool:connections:list'),
    save: payload => ipcRenderer.invoke('fool:connections:save', payload),
    remove: id => ipcRenderer.invoke('fool:connections:remove', id),
    setPrimary: id => ipcRenderer.invoke('fool:connections:set-primary', id),
    test: id => ipcRenderer.invoke('fool:connections:test', id),
    // Fan out `fool update` to every eligible registered connection.
    updateAll: () => ipcRenderer.invoke('fool:connections:update-all'),
    // Registry lifecycle push (main → renderer): a connection was removed or
    // materially edited, so secondaries scoped to it must be disposed (and,
    // for edits, re-dialed at the new target).
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('fool:connections:changed', listener)

      return () => ipcRenderer.removeListener('fool:connections:changed', listener)
    }
  },
  sshConfigHosts: () => ipcRenderer.invoke('fool:ssh-config:hosts'),
  sshResolveHost: host => ipcRenderer.invoke('fool:ssh-config:resolve', host),
  probeConnectionConfig: remoteUrl => ipcRenderer.invoke('fool:connection-config:probe', remoteUrl),
  oauthLoginConnectionConfig: remoteUrl => ipcRenderer.invoke('fool:connection-config:oauth-login', remoteUrl),
  oauthLogoutConnectionConfig: remoteUrl => ipcRenderer.invoke('fool:connection-config:oauth-logout', remoteUrl),
  // The Fool Cloud: one portal login powers discovery + silent per-agent sign-in
  // (cloud-auto-discovery Phase 3).
  cloud: {
    status: () => ipcRenderer.invoke('fool:cloud:status'),
    login: () => ipcRenderer.invoke('fool:cloud:login'),
    logout: () => ipcRenderer.invoke('fool:cloud:logout'),
    discover: org => ipcRenderer.invoke('fool:cloud:discover', org),
    agentSignIn: dashboardUrl => ipcRenderer.invoke('fool:cloud:agent-sign-in', dashboardUrl)
  },
  profile: {
    get: () => ipcRenderer.invoke('fool:profile:get'),
    set: name => ipcRenderer.invoke('fool:profile:set', name)
  },
  api: request => ipcRenderer.invoke('fool:api', request),
  notify: payload => ipcRenderer.invoke('fool:notify', payload),
  requestMicrophoneAccess: () => ipcRenderer.invoke('fool:requestMicrophoneAccess'),
  readWindowBelow: () => ipcRenderer.invoke('fool:window:readBelow'),
  readFileDataUrl: filePath => ipcRenderer.invoke('fool:readFileDataUrl', filePath),
  readFileDataUrlForAttach: filePath => ipcRenderer.invoke('fool:readFileDataUrlForAttach', filePath),
  dataUrlReadMax: {
    get: () => ipcRenderer.invoke('fool:data-url-read-max:get'),
    set: maxMb => ipcRenderer.invoke('fool:data-url-read-max:set', maxMb)
  },
  readFileText: filePath => ipcRenderer.invoke('fool:readFileText', filePath),
  selectPaths: options => ipcRenderer.invoke('fool:selectPaths', options),
  selectSavePath: options => ipcRenderer.invoke('fool:selectSavePath', options),
  writeClipboard: text => ipcRenderer.invoke('fool:writeClipboard', text),
  readClipboard: () => ipcRenderer.invoke('fool:readClipboard'),
  saveGatewayFile: payload => ipcRenderer.invoke('fool:saveGatewayFile', payload),
  saveImageFromUrl: url => ipcRenderer.invoke('fool:saveImageFromUrl', url),
  saveImageBuffer: (data, ext) => ipcRenderer.invoke('fool:saveImageBuffer', { data, ext }),
  saveClipboardImage: () => ipcRenderer.invoke('fool:saveClipboardImage'),
  getPathForFile: file => {
    try {
      return webUtils.getPathForFile(file) || ''
    } catch {
      return ''
    }
  },
  normalizePreviewTarget: (target, baseDir) => ipcRenderer.invoke('fool:normalizePreviewTarget', target, baseDir),
  watchPreviewFile: url => ipcRenderer.invoke('fool:watchPreviewFile', url),
  watchDirectory: dir => ipcRenderer.invoke('fool:watchDirectory', dir),
  stopPreviewFileWatch: id => ipcRenderer.invoke('fool:stopPreviewFileWatch', id),
  setActiveWork: payload => ipcRenderer.send('fool:active-work', payload),
  setTitleBarTheme: payload => ipcRenderer.send('fool:titlebar-theme', payload),
  setNativeTheme: mode => ipcRenderer.send('fool:native-theme', mode),
  setTranslucency: payload => ipcRenderer.send('fool:translucency', payload),
  setKeepAwake: on => ipcRenderer.send('fool:keep-awake', on),
  setDisableF12: blocked => ipcRenderer.send('fool:devtools:disable-f12', blocked),
  setPreviewShortcutActive: active => ipcRenderer.send('fool:previewShortcutActive', Boolean(active)),
  openExternal: url => ipcRenderer.invoke('fool:openExternal', url),
  openPreviewInBrowser: url => ipcRenderer.invoke('fool:openPreviewInBrowser', url),
  fetchLinkTitle: url => ipcRenderer.invoke('fool:fetchLinkTitle', url),
  sanitizeWorkspaceCwd: cwd => ipcRenderer.invoke('fool:workspace:sanitize', cwd),
  settings: {
    getDefaultProjectDir: () => ipcRenderer.invoke('fool:setting:defaultProjectDir:get'),
    setDefaultProjectDir: dir => ipcRenderer.invoke('fool:setting:defaultProjectDir:set', dir),
    pickDefaultProjectDir: () => ipcRenderer.invoke('fool:setting:defaultProjectDir:pick')
  },
  zoom: {
    // Current zoom of this window, as { level, percent }.
    get: () => ipcRenderer.invoke('fool:zoom:get'),
    setPercent: percent => ipcRenderer.send('fool:zoom:set-percent', percent),
    // Fires on every zoom change, including the Ctrl/Cmd +/-/0 shortcuts,
    // so the settings UI can stay in sync with the keyboard.
    onChanged: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('fool:zoom:changed', listener)

      return () => ipcRenderer.removeListener('fool:zoom:changed', listener)
    }
  },
  revealLogs: () => ipcRenderer.invoke('fool:logs:reveal'),
  getRecentLogs: () => ipcRenderer.invoke('fool:logs:recent'),
  // Fire-and-forget: persists a renderer error-boundary catch (with component
  // stack) to desktop.log so crashes survive the window (#79428).
  reportRendererError: report => ipcRenderer.send('fool:logs:renderer-error', report),
  readDir: dirPath => ipcRenderer.invoke('fool:fs:readDir', dirPath),
  gitRoot: startPath => ipcRenderer.invoke('fool:fs:gitRoot', startPath),
  revealPath: targetPath => ipcRenderer.invoke('fool:fs:reveal', targetPath),
  openDir: dirPath => ipcRenderer.invoke('fool:fs:openDir', dirPath),
  desktopPluginsRoot: () => ipcRenderer.invoke('fool:fs:desktopPluginsRoot'),
  agentPluginsRoot: () => ipcRenderer.invoke('fool:fs:agentPluginsRoot'),
  renamePath: (targetPath, newName) => ipcRenderer.invoke('fool:fs:rename', targetPath, newName),
  writeTextFile: (filePath, content) => ipcRenderer.invoke('fool:fs:writeText', filePath, content),
  trashPath: targetPath => ipcRenderer.invoke('fool:fs:trash', targetPath),
  git: {
    worktreeList: repoPath => ipcRenderer.invoke('fool:git:worktreeList', repoPath),
    worktreeAdd: (repoPath, options) => ipcRenderer.invoke('fool:git:worktreeAdd', repoPath, options),
    worktreeRemove: (repoPath, worktreePath, options) =>
      ipcRenderer.invoke('fool:git:worktreeRemove', repoPath, worktreePath, options),
    branchSwitch: (repoPath, branch) => ipcRenderer.invoke('fool:git:branchSwitch', repoPath, branch),
    branchList: repoPath => ipcRenderer.invoke('fool:git:branchList', repoPath),
    baseBranchList: repoPath => ipcRenderer.invoke('fool:git:baseBranchList', repoPath),
    repoStatus: repoPath => ipcRenderer.invoke('fool:git:repoStatus', repoPath),
    fileDiff: (repoPath, filePath) => ipcRenderer.invoke('fool:git:fileDiff', repoPath, filePath),
    scanRepos: (roots, options) => ipcRenderer.invoke('fool:git:scanRepos', roots, options),
    review: {
      list: (repoPath, scope, baseRef) => ipcRenderer.invoke('fool:git:review:list', repoPath, scope, baseRef),
      diff: (repoPath, filePath, scope, baseRef, staged) =>
        ipcRenderer.invoke('fool:git:review:diff', repoPath, filePath, scope, baseRef, staged),
      stage: (repoPath, filePath) => ipcRenderer.invoke('fool:git:review:stage', repoPath, filePath),
      unstage: (repoPath, filePath) => ipcRenderer.invoke('fool:git:review:unstage', repoPath, filePath),
      revert: (repoPath, filePath) => ipcRenderer.invoke('fool:git:review:revert', repoPath, filePath),
      revParse: (repoPath, ref) => ipcRenderer.invoke('fool:git:review:revParse', repoPath, ref),
      commit: (repoPath, message, push) => ipcRenderer.invoke('fool:git:review:commit', repoPath, message, push),
      commitContext: repoPath => ipcRenderer.invoke('fool:git:review:commitContext', repoPath),
      push: repoPath => ipcRenderer.invoke('fool:git:review:push', repoPath),
      shipInfo: repoPath => ipcRenderer.invoke('fool:git:review:shipInfo', repoPath),
      prList: (repoPath, branches, numbers) =>
        ipcRenderer.invoke('fool:git:review:prList', repoPath, branches, numbers),
      fetchPrComment: (repoPath, url) => ipcRenderer.invoke('fool:git:review:fetchPrComment', repoPath, url),
      createPr: repoPath => ipcRenderer.invoke('fool:git:review:createPr', repoPath)
    }
  },
  terminal: {
    cwd: id => ipcRenderer.invoke('fool:terminal:cwd', id),
    dispose: id => ipcRenderer.invoke('fool:terminal:dispose', id),
    resize: (id, size) => ipcRenderer.invoke('fool:terminal:resize', id, size),
    start: options => ipcRenderer.invoke('fool:terminal:start', options),
    write: (id, data) => ipcRenderer.invoke('fool:terminal:write', id, data),
    onData: (id, callback) => {
      const channel = `fool:terminal:${id}:data`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    },
    onExit: (id, callback) => {
      const channel = `fool:terminal:${id}:exit`
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on(channel, listener)

      return () => ipcRenderer.removeListener(channel, listener)
    }
  },
  onClosePreviewRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('fool:close-preview-requested', listener)

    return () => ipcRenderer.removeListener('fool:close-preview-requested', listener)
  },
  onOpenFolderRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('fool:open-folder-requested', listener)

    return () => ipcRenderer.removeListener('fool:open-folder-requested', listener)
  },
  onOpenUpdatesRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('fool:open-updates', listener)

    return () => ipcRenderer.removeListener('fool:open-updates', listener)
  },
  onDeepLink: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('fool:deep-link', listener)

    return () => ipcRenderer.removeListener('fool:deep-link', listener)
  },
  signalDeepLinkReady: () => ipcRenderer.invoke('fool:deep-link-ready'),
  onWindowStateChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('fool:window-state-changed', listener)

    return () => ipcRenderer.removeListener('fool:window-state-changed', listener)
  },
  onFocusSession: callback => {
    const listener = (_event, sessionId) => callback(sessionId)
    ipcRenderer.on('fool:focus-session', listener)

    return () => ipcRenderer.removeListener('fool:focus-session', listener)
  },
  onNotificationAction: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('fool:notification-action', listener)

    return () => ipcRenderer.removeListener('fool:notification-action', listener)
  },
  onPreviewFileChanged: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('fool:preview-file-changed', listener)

    return () => ipcRenderer.removeListener('fool:preview-file-changed', listener)
  },
  onBackendExit: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('fool:backend-exit', listener)

    return () => ipcRenderer.removeListener('fool:backend-exit', listener)
  },
  // Soft gateway-mode apply finished tearing down the primary backend. Renderer
  // should wipe session lists + re-dial without a window reload.
  onConnectionApplied: callback => {
    const listener = () => callback()
    ipcRenderer.on('fool:connection:applied', listener)

    return () => ipcRenderer.removeListener('fool:connection:applied', listener)
  },
  onPowerResume: callback => {
    const listener = () => callback()
    ipcRenderer.on('fool:power-resume', listener)

    return () => ipcRenderer.removeListener('fool:power-resume', listener)
  },
  // AC ↔ battery transitions; renderers slow their backstop polls on battery.
  getOnBattery: () => ipcRenderer.invoke('fool:power-battery:get'),
  onBatteryChanged: callback => {
    const listener = (_event, onBattery) => callback(Boolean(onBattery))
    ipcRenderer.on('fool:power-battery', listener)

    return () => ipcRenderer.removeListener('fool:power-battery', listener)
  },
  onBootProgress: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('fool:boot-progress', listener)

    return () => ipcRenderer.removeListener('fool:boot-progress', listener)
  },
  // First-launch bootstrap progress -- emitted by the install.ps1 stage
  // runner in main.ts (apps/desktop/electron/bootstrap-runner.ts).
  // Renderer's install overlay subscribes to live events and queries the
  // current snapshot via getBootstrapState() to recover after a devtools
  // reload mid-bootstrap.
  getBootstrapState: () => ipcRenderer.invoke('fool:bootstrap:get'),
  continueBootstrapLocal: () => ipcRenderer.invoke('fool:bootstrap:continue-local'),
  resetBootstrap: () => ipcRenderer.invoke('fool:bootstrap:reset'),
  repairBootstrap: () => ipcRenderer.invoke('fool:bootstrap:repair'),
  cancelBootstrap: () => ipcRenderer.invoke('fool:bootstrap:cancel'),
  onBootstrapEvent: callback => {
    const listener = (_event, payload) => callback(payload)
    ipcRenderer.on('fool:bootstrap:event', listener)

    return () => ipcRenderer.removeListener('fool:bootstrap:event', listener)
  },
  getVersion: () => ipcRenderer.invoke('fool:version'),
  getRemoteDisplayReason: () => ipcRenderer.invoke('fool:get-remote-display-reason'),
  uninstall: {
    summary: () => ipcRenderer.invoke('fool:uninstall:summary'),
    run: mode => ipcRenderer.invoke('fool:uninstall:run', { mode })
  },
  updates: {
    check: () => ipcRenderer.invoke('fool:updates:check'),
    apply: opts => ipcRenderer.invoke('fool:updates:apply', opts),
    getBranch: () => ipcRenderer.invoke('fool:updates:branch:get'),
    setBranch: name => ipcRenderer.invoke('fool:updates:branch:set', name),
    onProgress: callback => {
      const listener = (_event, payload) => callback(payload)
      ipcRenderer.on('fool:updates:progress', listener)

      return () => ipcRenderer.removeListener('fool:updates:progress', listener)
    }
  },
  themes: {
    fetchMarketplace: id => ipcRenderer.invoke('fool:vscode-theme:fetch', id),
    searchMarketplace: query => ipcRenderer.invoke('fool:vscode-theme:search', query)
  },
  // Find-in-page (Ctrl/Cmd+F): delegates to Electron's
  // webContents.findInPage on the IPC sender's window so a Cmd+F pressed
  // in a secondary session window searches THAT window, not the primary.
  // `onFoundInPage` returns the unsubscribe fn; the renderer wires it via
  // `initFindInPageListener` in store/find-in-page.ts and tears it down
  // when the FindBar unmounts.
  findInPage: (query, options) => ipcRenderer.invoke('fool:find-in-page', query, options),
  stopFindInPage: () => ipcRenderer.invoke('fool:stop-find-in-page'),
  onFoundInPage: callback => {
    const listener = (_event, result) => callback(result)
    ipcRenderer.on('fool:found-in-page', listener)

    return () => ipcRenderer.removeListener('fool:found-in-page', listener)
  },
  // Main-process `before-input-event` forwards Ctrl/Cmd+F here so renderer
  // can open the FindBar even when the GTK compositor has already grabbed
  // the chord at the windowing layer (#81727).
  onOpenFindBarRequested: callback => {
    const listener = () => callback()
    ipcRenderer.on('fool:open-find-bar', listener)

    return () => ipcRenderer.removeListener('fool:open-find-bar', listener)
  }
})
