var WakePc = (function (React, _manifest) {
    'use strict';

    const manifest = _manifest;
    const API_VERSION = 2;
    if (!manifest?.name) {
        throw new Error('[@decky/api]: Failed to find plugin manifest.');
    }
    const internalAPIConnection = window.__DECKY_SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED_deckyLoaderAPIInit;
    if (!internalAPIConnection) {
        throw new Error('[@decky/api]: Failed to connect to the loader as as the loader API was not initialized. This is likely a bug in Decky Loader.');
    }
    let api;
    try {
        api = internalAPIConnection.connect(API_VERSION, manifest.name);
    }
    catch {
        api = internalAPIConnection.connect(1, manifest.name);
        console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version 1. Some features may not work.`);
    }
    if (api._version != API_VERSION) {
        console.warn(`[@decky/api] Requested API version ${API_VERSION} but the running loader only supports version ${api._version}. Some features may not work.`);
    }
    api.call;
    api.callable;
    api.addEventListener;
    api.removeEventListener;
    api.routerHook;
    const toaster = api.toaster;
    api.openFilePicker;
    api.executeInTab;
    api.injectCssIntoTab;
    api.removeCssFromTab;
    api.fetchNoCors;
    api.getExternalResourceURL;
    api.useQuickAccessVisible;
    const definePlugin = (fn) => {
        return (...args) => {
            return fn(...args);
        };
    };

    const bgStyle1 = 'background: #16a085; color: black;';
    const log = (name, ...args) => {
        console.log(`%c @decky/ui %c ${name} %c`, bgStyle1, 'background: #1abc9c; color: black;', 'background: transparent;', ...args);
    };
    const group = (name, ...args) => {
        console.group(`%c @decky/ui %c ${name} %c`, bgStyle1, 'background: #1abc9c; color: black;', 'background: transparent;', ...args);
    };
    const groupEnd = (name, ...args) => {
        console.groupEnd();
        if (args?.length > 0)
            console.log(`^ %c @decky/ui %c ${name} %c`, bgStyle1, 'background: #1abc9c; color: black;', 'background: transparent;', ...args);
    };
    const debug = (name, ...args) => {
        console.debug(`%c @decky/ui %c ${name} %c`, bgStyle1, 'background: #1abc9c; color: black;', 'color: blue;', ...args);
    };
    const warn = (name, ...args) => {
        console.warn(`%c @decky/ui %c ${name} %c`, bgStyle1, 'background: #ffbb00; color: black;', 'color: blue;', ...args);
    };
    const error = (name, ...args) => {
        console.error(`%c @decky/ui %c ${name} %c`, bgStyle1, 'background: #FF0000;', 'background: transparent;', ...args);
    };
    class Logger {
        constructor(name) {
            this.name = name;
            this.name = name;
        }
        log(...args) {
            log(this.name, ...args);
        }
        debug(...args) {
            debug(this.name, ...args);
        }
        warn(...args) {
            warn(this.name, ...args);
        }
        error(...args) {
            error(this.name, ...args);
        }
        group(...args) {
            group(this.name, ...args);
        }
        groupEnd(...args) {
            groupEnd(this.name, ...args);
        }
    }

    const logger = new Logger('Webpack');
    let modules = new Map();
    function initModuleCache() {
        const startTime = performance.now();
        logger.group('Webpack Module Init');
        const id = Symbol("@decky/ui");
        let webpackRequire;
        window.webpackChunksteamui.push([
            [id],
            {},
            (r) => {
                webpackRequire = r;
            },
        ]);
        logger.log('Initializing all modules. Errors here likely do not matter, as they are usually just failing module side effects.');
        for (let id of Object.keys(webpackRequire.m)) {
            try {
                const module = webpackRequire(id);
                if (module) {
                    modules.set(id, module);
                }
            }
            catch (e) {
                logger.debug('Ignoring require error for module', id, e);
            }
        }
        logger.groupEnd(`Modules initialized in ${performance.now() - startTime}ms...`);
    }
    initModuleCache();
    const findModule = (filter) => {
        for (const m of modules.values()) {
            if (m.default && filter(m.default))
                return m.default;
            if (filter(m))
                return m;
        }
    };
    const findModuleDetailsByExport = (filter, minExports) => {
        for (const [id, m] of modules) {
            if (!m)
                continue;
            for (const mod of [m.default, m]) {
                if (typeof mod !== 'object')
                    continue;
                if (mod == window)
                    continue;
                for (let exportName in mod) {
                    if (mod?.[exportName]) {
                        try {
                            const filterRes = filter(mod[exportName], exportName);
                            if (filterRes) {
                                return [mod, mod[exportName], exportName, id];
                            }
                            else {
                                continue;
                            }
                        }
                        catch (e) {
                            logger.warn("Webpack filter threw exception: ", e, "Filter: ", filter);
                        }
                    }
                }
            }
        }
        return [undefined, undefined, undefined, undefined];
    };
    const findModuleByExport = (filter, minExports) => {
        return findModuleDetailsByExport(filter)?.[0];
    };
    const createModuleMapping = (filter) => {
        const mapping = new Map();
        for (const [id, m] of modules) {
            if (m.default && filter(m.default))
                mapping.set(id, m.default);
            if (filter(m))
                mapping.set(id, m);
        }
        return mapping;
    };
    const CommonUIModule = findModule((m) => {
        if (typeof m !== 'object')
            return false;
        for (let prop in m) {
            if (m[prop]?.contextType?._currentValue && Object.keys(m).length > 60)
                return true;
        }
        return false;
    });
    findModuleByExport((e) => e?.toString && /Spinner\),children:\[\(0,\w+\.jsx\)\("path",\{d:"M18 /.test(e.toString?.()) || /Spinner\)}\)?,.\.createElement\(\"path\",{d:\"M18 /.test(e.toString?.()));
    findModuleByExport((e) => e.computeRootMatch);

    const classModuleMap = createModuleMapping((m) => {
        if (typeof m == 'object' && !m.__esModule) {
            const keys = Object.keys(m);
            if (keys.length == 1 && m.version)
                return false;
            if (keys.length > 1000 && m.AboutSettings)
                return false;
            return keys.length > 0 && keys.every((k) => !Object.getOwnPropertyDescriptor(m, k)?.get && typeof m[k] == 'string');
        }
        return false;
    });
    const classMap = [...classModuleMap.values()];
    function findClassModule(filter) {
        return classMap.find((m) => filter(m));
    }

    const quickAccessMenuClasses = findClassModule((m) => m.Title && m.QuickAccessMenu);
    findClassModule((m) => m.ScrollPanel);
    findClassModule((m) => m.GamepadDialogContent && !m.BindingButtons);
    findClassModule((m) => m.BatteryPercentageLabel && m.PanelSection && !m['vr-dashboard-bar-height'] && !m.QuickAccessMenu && !m.QuickAccess && !m.PerfProfileInfo);
    findClassModule((m) => m.OOBEUpdateStatusContainer);
    findClassModule((m) => m.PlayBarDetailLabel);
    findClassModule((m) => m.SliderControlPanelGroup);
    findClassModule((m) => m.TopCapsule);
    findClassModule((m) => m.HeaderLoaded);
    findClassModule((m) => m.BasicUiRoot);
    findClassModule((m) => m.GamepadTabbedPage);
    findClassModule((m) => m.BasicContextMenuModal);
    findClassModule((m) => m.AchievementListItemBase && !m.Page);
    findClassModule((m) => m.AchievementListItemBase && m.Page);
    findClassModule((m) => m.AppRunningControls && m.OverlayAchievements);
    findClassModule((m) => m.AppDetailsRoot);
    findClassModule(m => m.SpinnerLoaderContainer);
    findClassModule(m => m.QuickAccessFooter);
    findClassModule(m => m.PlayButtonContainer);
    findClassModule(m => m.LongTitles && m.GreyBackground);
    findClassModule(m => m.GamepadLibrary);
    findClassModule(m => m.FocusRingRoot);
    findClassModule(m => m.SearchAndTitleContainer);
    findClassModule(m => m.MainBrowserContainer);
    findClassModule(m => m.DashboardBarPopupContents && m.DashboardBar);
    const staticClasses = quickAccessMenuClasses;

    (undefined && undefined.__setFunctionName) || function (f, name, prefix) {
        if (typeof name === "symbol") name = name.description ? "[".concat(name.description, "]") : "";
        return Object.defineProperty(f, "name", { configurable: true, value: prefix ? "".concat(prefix, " ", name) : name });
    };
    function createPropListRegex(propList, fromStart = true) {
        let regexString = fromStart ? "const\{" : "";
        propList.forEach((prop, propIdx) => {
            regexString += `"?${prop}"?:[a-zA-Z_$]{1,2}`;
            if (propIdx < propList.length - 1) {
                regexString += ",";
            }
        });
        return new RegExp(regexString);
    }
    window.SP_REACT?.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED?.ReactCurrentDispatcher
        .current || Object.values(window.SP_REACT?.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE).find((p) => p?.useEffect);

    const buttonItemRegex = createPropListRegex(["highlightOnFocus", "childrenContainerWidth"], false);
    const ButtonItem = Object.values(CommonUIModule).find((mod) => (mod?.render?.toString && buttonItemRegex.test(mod.render.toString())) ||
        mod?.render?.toString?.().includes('childrenContainerWidth:"min"'));

    const [mod, panelSection] = findModuleDetailsByExport((e) => e.toString?.()?.includes('.PanelSection'));
    const PanelSection = panelSection;
    const PanelSectionRow = Object.values(mod).filter((exp) => !exp?.toString?.()?.includes('.PanelSection'))[0];

    function useWakeState(serverApi) {
        const [state, setState] = React.useState("checking");
        const [config, setConfig] = React.useState(null);
        const [status, setStatus] = React.useState(null);
        const [lastChecked, setLastChecked] = React.useState(Date.now());
        const [canWake, setCanWake] = React.useState(true);
        const wakingRef = React.useRef(false);
        const rateUntil = React.useRef(0);
        const wakeCleanupRef = React.useRef(null);
        const refresh = React.useCallback(async () => {
            try {
                const cfg = await serverApi.callPluginMethod("get_config", {});
                setConfig(cfg);
                if (!cfg || !cfg.mac) {
                    setState("needs_setup");
                    return;
                }
                setState("checking");
                const st = await serverApi.callPluginMethod("status", {});
                setStatus(st);
                setLastChecked(Date.now());
                setState(st?.online ? "online" : "offline");
            }
            catch (e) {
                setState("error");
            }
        }, [serverApi]);
        React.useEffect(() => { refresh(); }, [refresh]);
        React.useEffect(() => () => { wakeCleanupRef.current?.(); }, []);
        React.useEffect(() => {
            const interval = state === "waking" ? 2000 : 5000;
            const id = setInterval(() => { refresh(); }, interval);
            return () => clearInterval(id);
        }, [state, refresh]);
        const wake = React.useCallback(async () => {
            if (Date.now() < rateUntil.current)
                return;
            rateUntil.current = Date.now() + 3000;
            setCanWake(false);
            setTimeout(() => setCanWake(true), 3000);
            wakingRef.current = true;
            setState("waking");
            let cancelled = false;
            try {
                await serverApi.callPluginMethod("wake", {});
                const start = Date.now();
                const iv = setInterval(async () => {
                    if (cancelled) {
                        clearInterval(iv);
                        return;
                    }
                    const st = await serverApi.callPluginMethod("status", {});
                    if (cancelled) {
                        clearInterval(iv);
                        return;
                    }
                    setStatus(st);
                    setLastChecked(Date.now());
                    if (st?.online) {
                        clearInterval(iv);
                        wakingRef.current = false;
                        setState("online");
                        toaster.toast({ title: `${config?.mac ?? "PC"} is online` });
                    }
                    else if (Date.now() - start > (config?.timeout ?? 30) * 1000) {
                        clearInterval(iv);
                        wakingRef.current = false;
                        setState("timed_out");
                        toaster.toast({ title: "No response after 2 min..." });
                    }
                }, 2000);
                // unmount guard
                const cleanup = () => { cancelled = true; clearInterval(iv); };
                wakeCleanupRef.current = cleanup;
            }
            catch (e) {
                wakingRef.current = false;
                setState("error");
            }
        }, [serverApi, config]);
        return { state, config, status, lastChecked, wake, refresh, canWake, rateUntil };
    }

    function SettingsView({ serverApi, onBack }) {
        const [form, setForm] = React.useState({ alias: "", mac: "", ip: "", broadcast: "", probe_port: 9 });
        const [errors, setErrors] = React.useState({});
        const [msg, setMsg] = React.useState("");
        const [testRes, setTestRes] = React.useState("");
        React.useEffect(() => {
            (async () => {
                const r = await serverApi.callPluginMethod("get_config", {});
                if (r?.config)
                    setForm(r.config);
            })();
        }, [serverApi]);
        const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
        const validate = () => {
            const e = {};
            if (!form.mac)
                e.mac = "required";
            if (!form.ip)
                e.ip = "required";
            if (!form.broadcast)
                e.broadcast = "required";
            setErrors(e);
            return Object.keys(e).length === 0;
        };
        const save = async () => {
            if (!validate())
                return;
            const r = await serverApi.callPluginMethod("save_config", form);
            if (r?.error) {
                setMsg(r.error);
                return;
            }
            if (r?.config)
                setForm(r.config);
            setMsg("Saved");
        };
        const testWake = async () => {
            const r = await serverApi.callPluginMethod("test_wake", {});
            if (r?.error) {
                setTestRes(r.error);
                return;
            }
            setTestRes(`wake: dest=${JSON.stringify(r.destinations)} failed=${JSON.stringify(r.failed)}`);
        };
        const testProbe = async () => {
            const r = await serverApi.callPluginMethod("test_probe", {});
            if (r?.error) {
                setTestRes(r.error);
                return;
            }
            setTestRes(`probe: method=${r.method} latency=${r.latency_ms}ms online=${r.online}`);
        };
        const field = (k, label) => React.createElement(PanelSectionRow, null, React.createElement("div", null, React.createElement("label", null, label), React.createElement("input", { value: form[k], onChange: (e) => set(k, k === "probe_port" ? Number(e.target.value) : e.target.value), onBlur: validate }), errors[k] ? React.createElement("span", { style: { color: "red" } }, errors[k]) : null));
        return React.createElement(PanelSection, { title: "Settings" }, field("alias", "Alias"), field("mac", "MAC"), field("ip", "IP"), field("broadcast", "Broadcast"), field("probe_port", "Probe port"), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: save }, "Save")), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: () => onBack() }, "Cancel")), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: testWake }, "Send test packet")), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: testProbe }, "Test status probe")), msg ? React.createElement(PanelSectionRow, null, React.createElement("div", null, msg)) : null, testRes ? React.createElement(PanelSectionRow, null, React.createElement("div", null, testRes)) : null);
    }

    function Diagnostics({ serverApi, onBack }) {
        const [data, setData] = React.useState(null);
        const [open, setOpen] = React.useState(false);
        const [copied, setCopied] = React.useState("");
        const load = React.useCallback(async () => {
            try {
                const r = await serverApi.callPluginMethod("get_diagnostics", {});
                setData(r);
            }
            catch (e) {
                setData({ error: String(e) });
            }
        }, [serverApi]);
        React.useEffect(() => { load(); }, [load]);
        const copy = async () => {
            const block = JSON.stringify(data, null, 2);
            try {
                await navigator.clipboard.writeText(block);
                setCopied("Copied");
            }
            catch {
                setCopied("Copy failed");
            }
            setTimeout(() => setCopied(""), 2000);
        };
        const last = data?.last_attempt ?? data?.lastAttempt ?? null;
        return React.createElement(PanelSection, { title: "Diagnostics" }, React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: load }, "Refresh")), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: () => setOpen(!open) }, `Last attempt ${open ? "▲" : "▼"}`)), open ? React.createElement(PanelSectionRow, null, React.createElement("div", { style: { fontSize: 12 } }, React.createElement("div", null, `timestamp: ${last?.timestamp ?? "-"}`), React.createElement("div", null, `outcome: ${last?.outcome ?? "-"}`), React.createElement("div", null, `destinations: ${JSON.stringify(last?.destinations ?? last?.dests ?? [])}`))) : null, React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: copy }, "Copy diagnostics")), copied ? React.createElement(PanelSectionRow, null, React.createElement("div", null, copied)) : null, React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: onBack }, "Back")));
    }

    const DOT = {
        needs_setup: "#f59e0b", ready: "#94a3b8", checking: "#94a3b8", online: "#22c55e",
        offline: "#ef4444", waking: "#3b82f6", timed_out: "#f59e0b", error: "#ef4444",
    };
    function Panel({ serverApi }) {
        const w = useWakeState(serverApi);
        const [showSettings, setShowSettings] = React.useState(false);
        const [showDiagnostics, setShowDiagnostics] = React.useState(false);
        const [now, setNow] = React.useState(Date.now());
        React.useEffect(() => { const id = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(id); }, []);
        const secs = Math.max(0, Math.ceil((w.rateUntil.current - now) / 1000));
        if (showSettings)
            return React.createElement(SettingsView, { serverApi, onBack: () => { setShowSettings(false); w.refresh(); } });
        if (showDiagnostics)
            return React.createElement(Diagnostics, { serverApi, onBack: () => { setShowDiagnostics(false); w.refresh(); } });
        return React.createElement(PanelSection, { title: "Wake PC" }, React.createElement(PanelSectionRow, null, React.createElement("div", { style: { display: "flex", alignItems: "center", gap: 8 } }, React.createElement("span", { style: { width: 10, height: 10, borderRadius: "50%", background: DOT[w.state] } }), React.createElement("span", null, w.state), React.createElement("span", { style: { marginLeft: "auto", fontSize: 12, opacity: 0.7 } }, `checked ${Math.round((now - w.lastChecked) / 1000)}s ago`))), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: async () => { await w.wake(); }, disabled: !w.canWake || ["needs_setup", "error", "waking", "timed_out"].includes(w.state) }, (["needs_setup", "error", "waking", "timed_out"].includes(w.state)) ? `Wake (${w.state})` : (w.canWake ? "Wake" : `Wake (${secs}s)`))), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: () => w.refresh() }, "Refresh")), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: () => setShowSettings(true) }, "Settings")), React.createElement(PanelSectionRow, null, React.createElement(ButtonItem, { layout: "below", onClick: () => setShowDiagnostics(true) }, "Diagnostics")));
    }
    var index = definePlugin((serverApi) => ({
        name: "Wake PC",
        title: React.createElement("div", { className: staticClasses.Title }, "Wake PC"),
        content: React.createElement(Panel, { serverApi: serverApi }),
        icon: React.createElement("div", null),
        onDismount() { },
    }));

    return index;

})(React, _manifest);
