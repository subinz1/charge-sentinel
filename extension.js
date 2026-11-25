import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const HELPER_PATH = '/usr/libexec/charge-sentinel-helper';
const POWER_SUPPLY_ROOT = '/sys/class/power_supply';
const REFRESH_SECONDS = 20;

const PRESETS = [
    {name: 'Desk mode', subtitle: 'Start 75% · stop 80%', start: 75, end: 80},
    {name: 'Balanced mode', subtitle: 'Start 70% · stop 85%', start: 70, end: 85},
    {name: 'Optimal mode', subtitle: 'Start 20% · stop 95%', start: 20, end: 95},
    {name: 'Travel mode', subtitle: 'Start 96% · stop 100%', start: 96, end: 100},
];

function readFile(path) {
    try {
        const [ok, contents] = GLib.file_get_contents(path);
        return ok ? new TextDecoder().decode(contents).trim() : null;
    } catch {
        return null;
    }
}

function findBatteries() {
    let names;
    try {
        const directory = GLib.Dir.open(POWER_SUPPLY_ROOT, 0);
        names = [];
        let name;
        while ((name = directory.read_name()) !== null)
            names.push(name);
        names.sort();
    } catch {
        return [];
    }

    const batteries = [];
    for (const name of names) {
        const base = `${POWER_SUPPLY_ROOT}/${name}`;
        if (readFile(`${base}/type`) !== 'Battery')
            continue;
        if (readFile(`${base}/charge_control_start_threshold`) === null ||
            readFile(`${base}/charge_control_end_threshold`) === null)
            continue;

        batteries.push({
            name,
            base,
            capacity: readFile(`${base}/capacity`) ?? '–',
            status: readFile(`${base}/status`) ?? 'Unknown',
        });
    }

    return batteries;
}

function batteryState(selectedBattery) {
    const batteries = findBatteries();
    const battery = batteries.find(item => item.name === selectedBattery) ?? batteries[0];
    if (!battery)
        return null;

    return {
        ...battery,
        batteries,
        start: readFile(`${battery.base}/charge_control_start_threshold`) ?? '–',
        end: readFile(`${battery.base}/charge_control_end_threshold`) ?? '–',
        behaviour: readFile(`${battery.base}/charge_behaviour`) ?? '',
    };
}

function currentBehaviour(value) {
    const match = value.match(/\[([^\]]+)]/);
    if (match)
        return match[1];

    const knownBehaviours = new Set(['auto', 'inhibit-charge']);
    const values = value.split(/\s+/).filter(item => knownBehaviours.has(item));
    return values.length === 1 ? values[0] : 'unknown';
}

const ChargeSentinelToggle = GObject.registerClass(
class ChargeSentinelToggle extends QuickSettings.QuickMenuToggle {
    _init(extension) {
        super._init({
            title: 'Charge Sentinel',
            subtitle: 'Checking battery support…',
            iconName: 'battery-good-symbolic',
            toggleMode: false,
        });

        this._extension = extension;
        this._settings = extension.getSettings();
        this._state = null;
        this._destroyed = false;
        this._helperRunning = false;

        this.menu.setHeader(
            'battery-good-symbolic',
            'Charge Sentinel',
            'Protect your battery while plugged in',
        );

        this._statusItem = new PopupMenu.PopupMenuItem('Checking battery support…', {reactive: false});
        this.menu.addMenuItem(this._statusItem);
        this._refreshItem = this.menu.addAction('Refresh battery status', () => this._refresh());
        this._batteryMenu = new PopupMenu.PopupSubMenuMenuItem('Battery');
        this._batteryMenu.visible = false;
        this.menu.addMenuItem(this._batteryMenu);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._presetItems = [];
        for (const preset of PRESETS) {
            const item = this.menu.addAction(`${preset.name} — ${preset.subtitle}`, () => {
                this._applyThresholds(preset.start, preset.end);
            });
            item.visible = false;
            this._presetItems.push({item, preset});
        }

        this._customItem = this.menu.addAction('Apply custom limits', () => {
            this._applyThresholds(
                this._settings.get_uint('custom-start'),
                this._settings.get_uint('custom-end'),
            );
        });
        this._customItem.visible = false;

        this._pauseItem = this.menu.addAction('Pause charging now', () => {
            this._setBehaviour('inhibit-charge');
        });
        this._pauseItem.visible = false;

        this._resumeItem = this.menu.addAction('Resume automatic charging', () => {
            this._setBehaviour('auto');
        });
        this._resumeItem.visible = false;

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
        const preferencesItem = this.menu.addAction('Open Charge Sentinel settings', () => {
            extension.openPreferences();
        });
        preferencesItem.visible = Main.sessionMode.allowSettings;
        this.menu._settingsActions[extension.uuid] = preferencesItem;

        this._settingsChangedId = this._settings.connect('changed::show-panel-icon', () => this._syncPanelIcon());
        this._selectedBatteryChangedId = this._settings.connect('changed::selected-battery', () => this._refresh());
        this._customThresholdChangedIds = [
            this._settings.connect('changed::custom-start', () => this._refresh()),
            this._settings.connect('changed::custom-end', () => this._refresh()),
        ];
        this._refresh();
        this._refreshId = GLib.timeout_add_seconds(
            GLib.PRIORITY_DEFAULT,
            REFRESH_SECONDS,
            () => {
                this._refresh();
                return GLib.SOURCE_CONTINUE;
            },
        );
    }

    _setActionVisibility(supported, canControlBehaviour, activeBehaviour) {
        this._presetItems.forEach(({item}) => item.visible = supported);
        this._customItem.visible = supported;
        this._pauseItem.visible = supported && canControlBehaviour && activeBehaviour !== 'inhibit-charge';
        this._resumeItem.visible = supported && canControlBehaviour && activeBehaviour !== 'auto';
    }

    _syncBatteryMenu(batteries) {
        this._batteryMenu.visible = batteries.length > 1;
        this._batteryMenu.menu.removeAll();

        if (batteries.length <= 1)
            return;

        const selectedBattery = this._settings.get_string('selected-battery');
        const automatic = !batteries.some(battery => battery.name === selectedBattery);
        const automaticItem = this._batteryMenu.menu.addAction(
            `Automatic (${this._state.name})`,
            () => this._settings.set_string('selected-battery', ''),
        );
        automaticItem.setOrnament(PopupMenu.Ornament.CHECK, automatic);
        this._batteryMenu.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        for (const battery of batteries) {
            const item = this._batteryMenu.menu.addAction(
                `${battery.name} · ${battery.capacity}% · ${battery.status}`,
                () => {
                    this._settings.set_string('selected-battery', battery.name);
                },
            );
            item.setOrnament(
                PopupMenu.Ornament.CHECK,
                battery.name === selectedBattery,
            );
        }
    }

    _syncProfileSelection() {
        const start = Number(this._state.start);
        const end = Number(this._state.end);
        let presetSelected = false;

        for (const {item, preset} of this._presetItems) {
            const selected = start === preset.start && end === preset.end;
            item.setOrnament(PopupMenu.Ornament.CHECK, selected);
            presetSelected = presetSelected || selected;
        }

        const customStart = this._settings.get_uint('custom-start');
        const customEnd = this._settings.get_uint('custom-end');
        const customValid = customStart < customEnd;
        this._customItem.label.text = customValid
            ? `Apply custom limits (${customStart}% → ${customEnd}%)`
            : 'Custom limits need a lower start value';
        this._customItem.reactive = customValid;
        this._customItem.setOrnament(
            PopupMenu.Ornament.CHECK,
            customValid && !presetSelected && start === customStart && end === customEnd,
        );
    }

    _refresh() {
        if (this._destroyed)
            return;

        this._state = batteryState(this._settings.get_string('selected-battery'));
        if (!this._state) {
            this._syncBatteryMenu([]);
            this.subtitle = 'Charge thresholds unavailable';
            this.iconName = 'battery-missing-symbolic';
            this._statusItem.label.text = 'This laptop does not expose safe Linux charge thresholds.';
            this._setActionVisibility(false, false);
            this._syncPanelIcon();
            return;
        }

        this._syncBatteryMenu(this._state.batteries);
        this._syncProfileSelection();
        const behaviour = currentBehaviour(this._state.behaviour);
        const held = Number(this._state.capacity) >= Number(this._state.end) &&
            this._state.status !== 'Charging';
        const stateText = behaviour === 'inhibit-charge'
            ? 'Charging paused'
            : held
                ? `Holding at ${this._state.end}%`
                : this._state.status;

        this.subtitle = this._state.batteries.length > 1
            ? `${this._state.name}: ${this._state.capacity}% · ${stateText}`
            : `${this._state.capacity}% · ${stateText}`;
        this.iconName = held || behaviour === 'inhibit-charge'
            ? 'battery-level-80-symbolic'
            : 'battery-good-symbolic';
        this._statusItem.label.text =
            `${this._state.name}: ${this._state.capacity}% · ${this._state.status}\n` +
            `Charge range: ${this._state.start}% → ${this._state.end}%`;
        this._setActionVisibility(
            true,
            this._state.behaviour.includes('inhibit-charge'),
            behaviour,
        );
        this._syncPanelIcon();
    }

    _syncPanelIcon() {
        if (this._indicator) {
            this._indicator.icon_name = this.iconName;
            this._indicator.visible = this._settings.get_boolean('show-panel-icon') && Boolean(this._state);
        }
    }

    _runHelper(arguments_, successMessage) {
        if (!this._state)
            return;
        if (this._helperRunning) {
            this._statusItem.label.text = 'A charge change is already in progress.';
            return;
        }

        const argv = ['pkexec', HELPER_PATH, ...arguments_];
        let process;
        try {
            process = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
            );
        } catch (error) {
            this._statusItem.label.text = `Could not start Charge Sentinel: ${error.message}`;
            return;
        }

        this._helperRunning = true;
        this._statusItem.label.text = 'Waiting for administrator permission…';
        process.communicate_utf8_async(null, null, (source, result) => {
            if (this._destroyed)
                return;

            this._helperRunning = false;
            try {
                const [, stdout, stderr] = source.communicate_utf8_finish(result);
                if (!source.get_successful()) {
                    const detail = (stderr || stdout || 'The helper returned no diagnostic.').trim();
                    throw new Error(detail);
                }
                this._statusItem.label.text = successMessage;
                this._refresh();
            } catch (error) {
                const detail = String(error.message || 'The change was cancelled or could not be applied.')
                    .replace(/^Charge Sentinel:\\s*/, '');
                this._statusItem.label.text = `Could not apply change: ${detail}`;
            }
        });
    }

    _applyThresholds(start, end) {
        if (start >= end) {
            this._statusItem.label.text = 'The start limit must be lower than the stop limit.';
            return;
        }
        this._runHelper(['set-thresholds', this._state.name, String(start), String(end)],
            `Applied charge range: ${start}% → ${end}%`);
    }

    _setBehaviour(behaviour) {
        this._runHelper(['set-behaviour', this._state.name, behaviour],
            behaviour === 'auto' ? 'Automatic charging restored.' : 'Charging paused while the charger remains connected.');
    }

    addPanelIndicator() {
        this._indicator = this._addIndicator();
        this._indicator.icon_name = 'battery-good-symbolic';
        this._syncPanelIcon();
    }

    destroy() {
        this._destroyed = true;
        this._helperRunning = false;
        if (this._refreshId)
            GLib.Source.remove(this._refreshId);
        if (this._settingsChangedId)
            this._settings.disconnect(this._settingsChangedId);
        if (this._selectedBatteryChangedId)
            this._settings.disconnect(this._selectedBatteryChangedId);
        for (const id of this._customThresholdChangedIds)
            this._settings.disconnect(id);
        super.destroy();
    }
});

const ChargeSentinelIndicator = GObject.registerClass(
class ChargeSentinelIndicator extends QuickSettings.SystemIndicator {
    _init(extension) {
        super._init();
        this._toggle = new ChargeSentinelToggle(extension);
        this._toggle.addPanelIndicator();
        this.quickSettingsItems.push(this._toggle);
    }

    destroy() {
        this._toggle.destroy();
        super.destroy();
    }
});

export default class ChargeSentinelExtension extends Extension {
    enable() {
        this._indicator = new ChargeSentinelIndicator(this);
        Main.panel.statusArea.quickSettings.addExternalIndicator(this._indicator);
    }

    disable() {
        this._indicator.destroy();
        this._indicator = null;
    }
}
