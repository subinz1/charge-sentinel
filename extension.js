import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import * as QuickSettings from 'resource:///org/gnome/shell/ui/quickSettings.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

const HELPER_PATH = '/usr/local/libexec/charge-sentinel-helper';
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

function findBattery() {
    let names;
    try {
        const directory = GLib.Dir.open(POWER_SUPPLY_ROOT, 0);
        names = [];
        let name;
        while ((name = directory.read_name()) !== null)
            names.push(name);
    } catch {
        return null;
    }

    for (const name of names) {
        const base = `${POWER_SUPPLY_ROOT}/${name}`;
        if (readFile(`${base}/type`) !== 'Battery')
            continue;
        if (readFile(`${base}/charge_control_start_threshold`) === null ||
            readFile(`${base}/charge_control_end_threshold`) === null)
            continue;

        return {name, base};
    }

    return null;
}

function batteryState() {
    const battery = findBattery();
    if (!battery)
        return null;

    return {
        ...battery,
        capacity: readFile(`${battery.base}/capacity`) ?? '–',
        status: readFile(`${battery.base}/status`) ?? 'Unknown',
        start: readFile(`${battery.base}/charge_control_start_threshold`) ?? '–',
        end: readFile(`${battery.base}/charge_control_end_threshold`) ?? '–',
        behaviour: readFile(`${battery.base}/charge_behaviour`) ?? 'auto',
    };
}

function currentBehaviour(value) {
    const match = value.match(/\[([^\]]+)]/);
    return match ? match[1] : 'auto';
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

        this.menu.setHeader(
            'battery-good-symbolic',
            'Charge Sentinel',
            'Protect your battery while plugged in',
        );

        this._statusItem = new PopupMenu.PopupMenuItem('Checking battery support…', {reactive: false});
        this.menu.addMenuItem(this._statusItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._presetItems = [];
        for (const preset of PRESETS) {
            const item = this.menu.addAction(`${preset.name} — ${preset.subtitle}`, () => {
                this._applyThresholds(preset.start, preset.end);
            });
            item.visible = false;
            this._presetItems.push(item);
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

    _setActionVisibility(supported, canControlBehaviour) {
        this._presetItems.forEach(item => item.visible = supported);
        this._customItem.visible = supported;
        this._pauseItem.visible = supported && canControlBehaviour;
        this._resumeItem.visible = supported && canControlBehaviour;
    }

    _refresh() {
        this._state = batteryState();
        if (!this._state) {
            this.subtitle = 'Charge thresholds unavailable';
            this.iconName = 'battery-missing-symbolic';
            this._statusItem.label.text = 'This laptop does not expose safe Linux charge thresholds.';
            this._setActionVisibility(false, false);
            this._syncPanelIcon();
            return;
        }

        const behaviour = currentBehaviour(this._state.behaviour);
        const held = Number(this._state.capacity) >= Number(this._state.end) &&
            this._state.status !== 'Charging';
        const stateText = behaviour === 'inhibit-charge'
            ? 'Charging paused'
            : held
                ? `Holding at ${this._state.end}%`
                : this._state.status;

        this.subtitle = `${this._state.capacity}% · ${stateText}`;
        this.iconName = held || behaviour === 'inhibit-charge'
            ? 'battery-level-80-symbolic'
            : 'battery-good-symbolic';
        this._statusItem.label.text =
            `${this._state.name}: ${this._state.capacity}% · ${this._state.status}\n` +
            `Charge range: ${this._state.start}% → ${this._state.end}%`;
        this._setActionVisibility(true, this._state.behaviour.includes('inhibit-charge'));
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

        const argv = ['pkexec', HELPER_PATH, ...arguments_];
        let process;
        try {
            process = Gio.Subprocess.new(argv, Gio.SubprocessFlags.NONE);
        } catch (error) {
            this._statusItem.label.text = `Could not start Charge Sentinel: ${error.message}`;
            return;
        }

        this._statusItem.label.text = 'Waiting for administrator permission…';
        process.wait_check_async(null, (source, result) => {
            try {
                source.wait_check_finish(result);
                this._statusItem.label.text = successMessage;
                this._refresh();
            } catch {
                this._statusItem.label.text = 'The change was cancelled or could not be applied.';
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
        if (this._refreshId)
            GLib.Source.remove(this._refreshId);
        if (this._settingsChangedId)
            this._settings.disconnect(this._settingsChangedId);
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
